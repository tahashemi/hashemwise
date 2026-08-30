"""Hashemwise - turning ledger data into message text.

Pure functions over plain data: no Telegram objects, no database. That keeps
the wording and the money formatting testable without a bot, which matters
because a display bug looks exactly like a calculation bug to whoever is
reading the message.

Balances and suggested payments are prose, one line per person, because
Western digits inside RTL prose get reordered unpredictably by the bidi
algorithm. The per-person split tables are the exception: they go inside a
<pre> block whose every line starts with a left-to-right mark, which pins the
line direction and keeps the columns aligned in both languages.
"""

from __future__ import annotations

import html
from typing import Iterable, Mapping, Sequence

from src.currencies import get_currency
from src.debt_engine import Transfer
from src.i18n import t
from src.money import format_amount


def esc(text: str) -> str:
    """Escape user-supplied text for Telegram's HTML parse mode.

    Member names and descriptions come from users; an unescaped `<` breaks the
    message and a crafted one could inject formatting.
    """
    return html.escape(str(text), quote=False)


def name_of(members: Iterable, user_id: int) -> str:
    for m in members:
        if m.user_id == user_id:
            return esc(m.display_name)
    return f"#{user_id}"


def money(minor: int, currency: str, lang: str) -> str:
    return format_amount(minor, currency, lang)


def shares_block(
    shares: Mapping[int, int], members, payer_id: int, currency: str, lang: str
) -> str:
    """Every participant's share, payer marked.

    Shown before anything is written. The equal-split remainder rule means one
    person can be a single minor unit above the rest, and the only acceptable
    way to handle that is to show it rather than hide it.
    """
    lines = []
    for uid in sorted(shares, key=lambda u: (u != payer_id, u)):
        key = "expense_share_row_payer" if uid == payer_id else "expense_share_row"
        lines.append(
            t(key, lang, name=name_of(members, uid), amount=money(shares[uid], currency, lang))
        )
    return "\n".join(lines)


def remainder_note(total_minor: int, shares: Mapping[int, int], currency: str, lang: str) -> str:
    """Explain an uneven split, or return "" when it divided cleanly."""
    if not shares or len(set(shares.values())) <= 1:
        return ""
    cur = get_currency(currency)
    unit = cur.symbol_fa if lang == "fa" else cur.symbol_en
    return t("expense_remainder_note", lang, amount=money(total_minor, currency, lang), unit=unit)


def balances_block(balances: Mapping[int, int], members, currency: str, lang: str) -> str:
    """Net position per person, creditors first, then debtors, then the settled."""
    if all(v == 0 for v in balances.values()):
        return t("balances_all_settled", lang)

    def rank(item):
        uid, value = item
        # Creditors (0) before debtors (1) before settled (2); largest first.
        bucket = 0 if value > 0 else (1 if value < 0 else 2)
        return (bucket, -abs(value), uid)

    lines = [t("balances_header", lang)]
    for uid, value in sorted(balances.items(), key=rank):
        name = name_of(members, uid)
        if value > 0:
            lines.append(t("balances_is_owed", lang, name=name, amount=money(value, currency, lang)))
        elif value < 0:
            lines.append(t("balances_owes", lang, name=name, amount=money(-value, currency, lang)))
        else:
            lines.append(t("balances_settled", lang, name=name))
    return "\n".join(lines)


def plan_block(plan: Sequence[Transfer], members, currency: str, lang: str) -> str:
    """The suggested payments, or "" when nobody owes anything."""
    if not plan:
        return ""
    lines = [t("plan_header", lang)]
    for transfer in plan:
        lines.append(
            t(
                "plan_row",
                lang,
                payer=name_of(members, transfer.from_user),
                payee=name_of(members, transfer.to_user),
                amount=money(transfer.amount_minor, currency, lang),
            )
        )
    lines.append(t("plan_note", lang, count=len(plan)))
    return "\n".join(lines)


def members_block(members, lang: str) -> str:
    if not members:
        return t("members_empty", lang)
    lines = [t("members_header", lang)]
    for m in members:
        name = esc(m.display_name)
        if not m.is_active:
            lines.append(t("member_row_inactive", lang, name=name))
        elif m.tg_user_id is None:
            lines.append(t("member_row_ghost", lang, name=name))
        else:
            lines.append(t("member_row_linked", lang, name=name))
    return "\n".join(lines)


# Left-to-right mark. Prefixing each line of a <pre> block with this pins the
# line's base direction to LTR, so the name/amount columns stay in the same
# place in a Persian group instead of being reordered by the bidi algorithm.
LRM = "‎"

# Names longer than this are truncated so the columns cannot wrap on a phone.
MAX_TABLE_NAME = 16


def raw_name_of(members, user_id: int) -> str:
    """Unescaped name, for measuring column widths before escaping."""
    for m in members:
        if m.user_id == user_id:
            return m.display_name
    return f"#{user_id}"


def _ellipsise(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def split_table(
    shares: Mapping[int, int], members, currency: str, lang: str, payer_id: int | None = None
) -> str:
    """A monospace two-column table of what each person was charged.

    Widths are measured on the raw names and the block is escaped afterwards,
    because escaping first would count `&amp;` as five columns instead of one.
    """
    if not shares:
        return ""

    rows = [
        (
            _ellipsise(raw_name_of(members, uid), MAX_TABLE_NAME),
            format_amount(shares[uid], currency, lang),
        )
        # Payer first, then by id, matching the confirmation screen.
        for uid in sorted(shares, key=lambda u: (u != payer_id, u))
    ]

    name_width = max(len(name) for name, _ in rows)
    amount_width = max(len(amount) for _, amount in rows)
    prefix = LRM if lang == "fa" else ""

    body = "\n".join(
        f"{prefix}{name.ljust(name_width)}  {amount.rjust(amount_width)}" for name, amount in rows
    )
    return f"<pre>{esc(body)}</pre>"


def display_id(entry) -> str:
    """`E7` / `S3`.

    Expenses and settlements have independent id sequences, so a bare "#1" is
    ambiguous - a group can hold both an expense #1 and a settlement #1. The
    kind letter matches the one used in the delete button.
    """
    return f"{'E' if entry['kind'] == 'expense' else 'S'}{entry['id']}"


def _short_date(timestamp: str | None) -> str:
    """`2026-08-30T18:16:12.345Z` -> `2026-08-30 18:16`."""
    if not timestamp:
        return ""
    return timestamp[:16].replace("T", " ")


def history_block(
    entries, members, lang: str, page: int, pages: int, splits: Mapping[int, Mapping[int, int]]
) -> str:
    """Full history page: every entry with its per-person breakdown."""
    if not entries:
        return t("history_empty", lang)

    parts = [t("history_header", lang, page=page, pages=pages)]
    for entry in entries:
        parts.append(entry_summary(entry, members, lang, splits))
    return "\n\n".join(parts)


def entry_summary(
    entry, members, lang: str, splits: Mapping[int, Mapping[int, int]] | None = None
) -> str:
    """One entry: header line, then the table of what each person was charged."""
    currency = entry["currency_code"]
    amount = money(entry["amount_minor"], currency, lang)
    date = _short_date(entry["created_at"]) if "created_at" in entry.keys() else ""

    if entry["kind"] == "expense":
        header = t(
            "history_expense",
            lang,
            id=display_id(entry),
            description=esc(entry["description"]),
            amount=amount,
            payer=name_of(members, entry["payer_id"]),
            date=date,
        )
    else:
        header = t(
            "history_settlement",
            lang,
            id=display_id(entry),
            payer=name_of(members, entry["payer_id"]),
            payee=name_of(members, entry["payee_id"]),
            amount=amount,
            date=date,
        )

    if entry["voided_at"] is not None:
        header += t("history_voided", lang)

    # Settlements move money between exactly two named people, so a breakdown
    # would just restate the header.
    if entry["kind"] != "expense" or not splits:
        return header

    shares = splits.get(entry["id"])
    if not shares:
        return header

    table = split_table(shares, members, currency, lang, payer_id=entry["payer_id"])
    return f"{header}\n{t('history_shares_label', lang)}\n{table}"
