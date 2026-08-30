"""Hashemwise — currency table.

Every currency the bot can be configured with lives here. Adding one is a
single entry; nothing else in the codebase hardcodes a currency.

`decimals` is the number of fractional digits the currency has, which is also
the power of ten separating a *minor unit* (how we store money, always as an
`int`) from a *major unit* (what the user types and reads). Toman has 0, so a
minor unit is a Toman. USD has 2, so a minor unit is a cent.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Currency:
    code: str
    decimals: int
    symbol_en: str
    symbol_fa: str
    name_en: str
    name_fa: str
    # In English, symbols like "$" lead the number while "T" trails it.
    # Persian always trails.
    prefix_en: bool


CURRENCIES: dict[str, Currency] = {
    c.code: c
    for c in (
        Currency("IRT", 0, "T", "تومان", "Toman", "تومان", prefix_en=False),
        Currency("USD", 2, "$", "دلار", "US Dollar", "دلار", prefix_en=True),
        Currency("EUR", 2, "€", "یورو", "Euro", "یورو", prefix_en=True),
        Currency("GBP", 2, "£", "پوند", "Pound", "پوند", prefix_en=True),
    )
}

DEFAULT_CURRENCY = "IRT"


def get_currency(code: str) -> Currency:
    """Look up a currency, case-insensitively.

    Raises KeyError with the offending code rather than returning a default —
    a silent fallback here would mean storing minor units under the wrong
    scale, which is exactly the class of bug this module exists to prevent.
    """
    try:
        return CURRENCIES[code.upper()]
    except KeyError:
        raise KeyError(f"unknown currency code: {code!r}") from None
