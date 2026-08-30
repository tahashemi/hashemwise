"""Hashemwise - all monetary arithmetic.

Two rules govern this module, and they are the reason it is pure (no Telegram,
no database, no I/O):

1. **Money is an `int` of minor units.** A float never touches an amount at any
   point. `0.1 + 0.2 != 0.3` in binary floating point, and a ledger built on
   that will drift until `sum(splits) == total` fails at random.
2. **Splitting is exact.** `divmod` distributes the remainder deliberately
   instead of letting division discard it.

Parsing goes through `decimal.Decimal`, and decimal places are checked against
the string the user typed *before* any scaling, so over-precision is rejected
rather than silently rounded away.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Iterable, Mapping

from src.currencies import get_currency

# Sanity ceiling. SQLite INTEGER is 64-bit so it could hold far more, but an
# amount past this is a typo (a stuck key), not a real expense.
MAX_AMOUNT_MINOR = 10**15

# Digit systems users actually type on Persian keyboards.
_EASTERN_ARABIC = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"

_DIGIT_MAP = {
    **{ord(c): str(i) for i, c in enumerate(_EASTERN_ARABIC)},
    **{ord(c): str(i) for i, c in enumerate(_ARABIC_INDIC)},
    0x066B: ".",  # arabic decimal separator
    0x066C: ",",  # arabic thousands separator
    0x060C: ",",  # arabic comma
}

# Grouping marks, plus the bidi/format characters that arrive invisibly when
# text is pasted out of an RTL context.
_STRIP_CHARS = (
    ", \t"
    " "  # no-break space
    " "  # narrow no-break space
    "‏‎"  # RLM / LRM
    "‪‫‬⁦⁧⁨⁩"  # bidi embedding / isolates
    "_"
)
_STRIP = str.maketrans("", "", _STRIP_CHARS)


# --------------------------------------------------------------------------
# Errors. Each carries a stable `key` so handlers can translate it without
# pattern-matching on English prose.
# --------------------------------------------------------------------------


class MoneyError(ValueError):
    key = "err_money"


class InvalidAmount(MoneyError):
    key = "err_amount_invalid"


class NonPositiveAmount(MoneyError):
    key = "err_amount_non_positive"


class TooManyDecimals(MoneyError):
    key = "err_amount_too_precise"

    def __init__(self, message: str, allowed: int) -> None:
        super().__init__(message)
        self.allowed = allowed


class AmountTooLarge(MoneyError):
    key = "err_amount_too_large"


class EmptyParticipants(MoneyError):
    key = "err_no_participants"


class NegativeShare(MoneyError):
    key = "err_negative_share"


class SplitMismatch(MoneyError):
    """Custom shares do not add up to the total.

    `delta` is signed: positive means the shares overshoot the total, negative
    means they fall short. The UI reports it verbatim rather than adjusting
    anything on the user's behalf.
    """

    key = "err_split_mismatch"

    def __init__(self, total_minor: int, sum_minor: int) -> None:
        self.total_minor = total_minor
        self.sum_minor = sum_minor
        self.delta = sum_minor - total_minor
        super().__init__(
            f"shares sum to {sum_minor}, expected {total_minor} (delta {self.delta:+d})"
        )


# --------------------------------------------------------------------------
# Parsing and formatting
# --------------------------------------------------------------------------


def normalize_digits(text: str) -> str:
    """Fold Persian/Arabic digits and separators onto their ASCII equivalents."""
    return text.translate(_DIGIT_MAP)


def parse_amount(text: str, currency_code: str) -> int:
    """Parse user input into a positive integer count of minor units.

    Accepts Persian and Arabic-Indic digits, `,`/separator grouping, and an
    optional fraction no longer than the currency allows. Raises on anything
    else - this function never rounds and never guesses.
    """
    if not isinstance(text, str):
        raise InvalidAmount("amount must be text")

    decimals = get_currency(currency_code).decimals
    cleaned = normalize_digits(text).translate(_STRIP)

    if not cleaned:
        raise InvalidAmount("empty amount")

    # A leading sign is not a parse failure, it is a negative amount, and the
    # caller deserves the more specific error.
    negative = cleaned.startswith("-")
    if negative:
        cleaned = cleaned[1:]

    if not _is_plain_decimal(cleaned):
        raise InvalidAmount(f"not a number: {text!r}")

    if "." in cleaned:
        fraction = cleaned.split(".", 1)[1]
        # Trailing zeros are exactly representable, so "1250.0" is fine for a
        # 0-decimal currency while "12.5" is not.
        if len(fraction.rstrip("0")) > decimals:
            raise TooManyDecimals(
                f"{currency_code.upper()} allows at most {decimals} decimal place(s)",
                allowed=decimals,
            )

    # prec well above our 16-digit ceiling, so scaleb is never lossy.
    with localcontext() as ctx:
        ctx.prec = 40
        scaled = Decimal(cleaned).scaleb(decimals)

    minor = int(scaled)
    if Decimal(minor) != scaled:  # defensive; the decimals check makes this unreachable
        raise TooManyDecimals(
            f"{text!r} is not exact in {currency_code.upper()}", allowed=decimals
        )

    if negative or minor <= 0:
        raise NonPositiveAmount("amount must be greater than zero")
    if minor > MAX_AMOUNT_MINOR:
        raise AmountTooLarge("amount is implausibly large")

    return minor


def _is_plain_decimal(s: str) -> bool:
    """True for `123`, `1.5`, `.5` - and nothing else.

    Deliberately stricter than `Decimal()`, which happily accepts `1e5`,
    `Infinity`, `NaN`, and `+1`.
    """
    if s.count(".") > 1:
        return False
    digits = s.replace(".", "", 1)
    # `str.isdigit()` is True for Persian numerals too, but those are already
    # folded to ASCII above; anything left that is non-ASCII is not a number
    # we are willing to guess at.
    return bool(digits) and digits.isascii() and digits.isdigit()


def format_amount(minor: int, currency_code: str, lang: str = "en") -> str:
    """Render minor units for display. Handles negatives (balances go both ways)."""
    cur = get_currency(currency_code)
    negative = minor < 0
    magnitude = abs(int(minor))

    if cur.decimals:
        whole, fraction = divmod(magnitude, 10**cur.decimals)
        number = f"{whole:,}.{fraction:0{cur.decimals}d}"
    else:
        number = f"{magnitude:,}"

    # Western digits even in Persian: mixing Persian numerals into RTL text
    # makes long amounts genuinely hard to read back.
    if lang == "fa":
        body = f"{number} {cur.symbol_fa}"
    elif cur.prefix_en:
        body = f"{cur.symbol_en}{number}"
    else:
        body = f"{number} {cur.symbol_en}"

    return f"-{body}" if negative else body


# --------------------------------------------------------------------------
# Splitting
# --------------------------------------------------------------------------


def split_equal(
    total_minor: int, participant_ids: Iterable[int], payer_id: int
) -> dict[int, int]:
    """Divide `total_minor` as evenly as integers allow.

    Guarantees `sum(result.values()) == total_minor` for every input, and that
    no two shares differ by more than one minor unit.

    The `total_minor % n` leftover units are handed out starting at the payer
    and wrapping through the remaining participants in ascending id order. The
    rule is deterministic and easy to explain - "the payer covers the odd
    Toman" - and the confirmation screen shows the resulting shares before
    anything is written, so it is never a surprise. Worst case it is `n-1`
    minor units.
    """
    ids = sorted(set(participant_ids))
    if not ids:
        raise EmptyParticipants("an expense needs at least one participant")
    if total_minor <= 0:
        raise NonPositiveAmount("total must be greater than zero")

    n = len(ids)
    base, remainder = divmod(total_minor, n)
    shares = {uid: base for uid in ids}

    start = ids.index(payer_id) if payer_id in shares else 0
    for offset in range(remainder):
        shares[ids[(start + offset) % n]] += 1

    assert sum(shares.values()) == total_minor  # the whole point of this function
    return shares


def validate_custom_split(total_minor: int, shares: Mapping[int, int]) -> None:
    """Assert hand-entered shares add up exactly. Raises `SplitMismatch` if not.

    Because the values are integers there is no tolerance and no epsilon: the
    sum either equals the total or it does not.
    """
    if not shares:
        raise EmptyParticipants("an expense needs at least one participant")

    for uid, amount in shares.items():
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise NegativeShare(f"share for user {uid} is not an integer")
        if amount < 0:
            raise NegativeShare(f"share for user {uid} is negative")

    total = sum(shares.values())
    if total != total_minor:
        raise SplitMismatch(total_minor, total)
