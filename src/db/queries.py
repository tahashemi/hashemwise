"""Hashemwise - every SQL statement in the project.

No other module writes SQL. Keeping it in one file means the schema's
invariants (soft deletes, idempotency keys, split sums) are enforced in one
reviewable place rather than scattered through handlers.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Mapping, Sequence

from src.db.connection import Database
from src.money import validate_custom_split

log = logging.getLogger(__name__)

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


class MemberInUse(Exception):
    """A member has ledger entries and so cannot be removed, only deactivated."""

    key = "err_member_in_use"


class DuplicateMember(Exception):
    key = "err_member_duplicate"


@dataclass(frozen=True)
class Group:
    group_id: int
    title: str
    is_active: bool
    currency_code: str
    lang: str
    is_setup: bool


@dataclass(frozen=True)
class Member:
    user_id: int
    group_id: int
    tg_user_id: int | None
    display_name: str
    is_active: bool


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


async def upsert_group(db: Database, group_id: int, title: str) -> None:
    """Record a group the bot has been added to, leaving it unauthorized.

    Re-adding the bot must never reset an existing group's authorization,
    currency, or language, so the conflict path only refreshes the title.
    """
    await db.execute(
        "INSERT INTO groups (group_id, title) VALUES (?, ?) "
        "ON CONFLICT (group_id) DO UPDATE SET title = excluded.title",
        (group_id, title),
    )


async def get_group(db: Database, group_id: int) -> Group | None:
    row = await db.fetchone(
        "SELECT group_id, title, is_active, currency_code, lang, is_setup "
        "FROM groups WHERE group_id = ?",
        (group_id,),
    )
    if row is None:
        return None
    return Group(
        group_id=row["group_id"],
        title=row["title"],
        is_active=bool(row["is_active"]),
        currency_code=row["currency_code"],
        lang=row["lang"],
        is_setup=bool(row["is_setup"]),
    )


async def set_group_active(db: Database, group_id: int, active: bool) -> None:
    await db.execute(
        "UPDATE groups SET is_active = ? WHERE group_id = ?", (1 if active else 0, group_id)
    )


async def set_group_currency(db: Database, group_id: int, currency_code: str) -> None:
    """Change a group's currency.

    Callers must check `group_has_entries` first. Amounts are stored as minor
    units under the old currency's scale, and there is no exchange rate to
    reinterpret them with, so switching after entries exist would silently
    change what every historical figure means.
    """
    await db.execute(
        "UPDATE groups SET currency_code = ? WHERE group_id = ?", (currency_code, group_id)
    )


async def set_group_lang(db: Database, group_id: int, lang: str) -> None:
    await db.execute("UPDATE groups SET lang = ? WHERE group_id = ?", (lang, group_id))


async def mark_group_setup(db: Database, group_id: int) -> None:
    await db.execute("UPDATE groups SET is_setup = 1 WHERE group_id = ?", (group_id,))


async def list_groups(db: Database) -> list[Group]:
    rows = await db.fetchall(
        "SELECT group_id, title, is_active, currency_code, lang, is_setup "
        "FROM groups ORDER BY added_at"
    )
    return [
        Group(
            group_id=r["group_id"],
            title=r["title"],
            is_active=bool(r["is_active"]),
            currency_code=r["currency_code"],
            lang=r["lang"],
            is_setup=bool(r["is_setup"]),
        )
        for r in rows
    ]


async def group_has_entries(db: Database, group_id: int) -> bool:
    """True if the group has any expense or settlement, voided or not.

    Voided rows count: they are still denominated in the old currency and are
    still visible in history.
    """
    row = await db.fetchone(
        "SELECT 1 FROM expenses WHERE group_id = ? "
        "UNION ALL SELECT 1 FROM settlements WHERE group_id = ? LIMIT 1",
        (group_id, group_id),
    )
    return row is not None


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


async def add_member(
    db: Database, group_id: int, display_name: str, tg_user_id: int | None = None
) -> int:
    name = display_name.strip()
    try:
        return await db.execute(
            "INSERT INTO users (group_id, display_name, tg_user_id) VALUES (?, ?, ?)",
            (group_id, name, tg_user_id),
        )
    except sqlite3.IntegrityError as exc:
        # Either the display name or the Telegram account is already a member.
        raise DuplicateMember(str(exc)) from exc


async def get_member(db: Database, user_id: int) -> Member | None:
    row = await db.fetchone(
        "SELECT user_id, group_id, tg_user_id, display_name, is_active "
        "FROM users WHERE user_id = ?",
        (user_id,),
    )
    return _member(row) if row else None


async def get_member_by_tg(db: Database, group_id: int, tg_user_id: int) -> Member | None:
    row = await db.fetchone(
        "SELECT user_id, group_id, tg_user_id, display_name, is_active "
        "FROM users WHERE group_id = ? AND tg_user_id = ?",
        (group_id, tg_user_id),
    )
    return _member(row) if row else None


async def list_members(db: Database, group_id: int, include_inactive: bool = False) -> list[Member]:
    sql = (
        "SELECT user_id, group_id, tg_user_id, display_name, is_active "
        "FROM users WHERE group_id = ?"
    )
    if not include_inactive:
        sql += " AND is_active = 1"
    sql += " ORDER BY user_id"
    return [_member(r) for r in await db.fetchall(sql, (group_id,))]


async def set_member_active(db: Database, user_id: int, active: bool) -> None:
    await db.execute(
        "UPDATE users SET is_active = ? WHERE user_id = ?", (1 if active else 0, user_id)
    )


async def rename_member(db: Database, user_id: int, display_name: str) -> None:
    try:
        await db.execute(
            "UPDATE users SET display_name = ? WHERE user_id = ?", (display_name.strip(), user_id)
        )
    except sqlite3.IntegrityError as exc:
        raise DuplicateMember(str(exc)) from exc


async def member_has_entries(db: Database, user_id: int) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM expenses WHERE payer_id = ? "
        "UNION ALL SELECT 1 FROM expense_splits WHERE user_id = ? "
        "UNION ALL SELECT 1 FROM settlements WHERE payer_id = ? OR payee_id = ? LIMIT 1",
        (user_id, user_id, user_id, user_id),
    )
    return row is not None


async def remove_member(db: Database, user_id: int) -> None:
    """Delete a member outright. Only legal while they have no ledger entries.

    Once someone appears in an expense, deleting them would orphan that split
    or, worse, silently drop their share from the totals. Deactivation is the
    supported path from then on.
    """
    if await member_has_entries(db, user_id):
        raise MemberInUse(f"user {user_id} appears in the ledger")
    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))


def _member(row) -> Member:
    return Member(
        user_id=row["user_id"],
        group_id=row["group_id"],
        tg_user_id=row["tg_user_id"],
        display_name=row["display_name"],
        is_active=bool(row["is_active"]),
    )


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------


async def create_expense(
    db: Database,
    *,
    group_id: int,
    payer_id: int,
    amount_minor: int,
    currency_code: str,
    description: str,
    created_by_tg: int,
    shares: Mapping[int, int],
    idem_key: str,
    supersedes_id: int | None = None,
) -> int:
    """Write an expense and its splits atomically. Returns the expense id.

    The shares are validated to sum to the total *before* anything is written,
    and the written rows are summed back inside the same transaction as a
    second check. Either failure rolls back the whole expense rather than
    leaving a half-written one that would corrupt every future balance.

    Idempotent on `idem_key`: a double-tapped confirm button returns the id of
    the expense the first tap created instead of writing a duplicate.
    """
    validate_custom_split(amount_minor, shares)

    existing = await db.fetchone("SELECT expense_id FROM expenses WHERE idem_key = ?", (idem_key,))
    if existing is not None:
        log.info("expense idem_key %s already applied; returning existing row", idem_key)
        return existing["expense_id"]

    try:
        async with db.transaction() as tx:
            expense_id = await tx.execute(
                "INSERT INTO expenses "
                "(group_id, payer_id, amount_minor, currency_code, description, "
                " created_by_tg, supersedes_id, idem_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    group_id,
                    payer_id,
                    amount_minor,
                    currency_code,
                    description,
                    created_by_tg,
                    supersedes_id,
                    idem_key,
                ),
            )
            await tx.executemany(
                "INSERT INTO expense_splits (expense_id, user_id, owed_minor) VALUES (?, ?, ?)",
                [(expense_id, uid, owed) for uid, owed in sorted(shares.items())],
            )

            row = await tx.fetchone(
                "SELECT COALESCE(SUM(owed_minor), 0) AS total, COUNT(*) AS n "
                "FROM expense_splits WHERE expense_id = ?",
                (expense_id,),
            )
            assert row is not None
            if row["total"] != amount_minor or row["n"] != len(shares):
                raise AssertionError(
                    f"split write mismatch: stored {row['n']} rows totalling "
                    f"{row['total']}, expected {len(shares)} totalling {amount_minor}"
                )
            return expense_id
    except sqlite3.IntegrityError:
        # Lost a race on idem_key with a concurrent confirm; the other write won.
        row = await db.fetchone("SELECT expense_id FROM expenses WHERE idem_key = ?", (idem_key,))
        if row is not None:
            return row["expense_id"]
        raise


async def void_expense(db: Database, expense_id: int, voided_by_tg: int) -> bool:
    """Soft-delete an expense. Returns False if it was already voided."""
    async with db.transaction() as tx:
        cursor_rows = await tx.fetchall(
            "SELECT voided_at FROM expenses WHERE expense_id = ?", (expense_id,)
        )
        if not cursor_rows or cursor_rows[0]["voided_at"] is not None:
            return False
        await tx.execute(
            f"UPDATE expenses SET voided_at = {NOW}, voided_by_tg = ? WHERE expense_id = ?",
            (voided_by_tg, expense_id),
        )
        return True


async def get_expense(db: Database, expense_id: int):
    return await db.fetchone("SELECT * FROM expenses WHERE expense_id = ?", (expense_id,))


async def get_expense_splits(db: Database, expense_id: int) -> dict[int, int]:
    rows = await db.fetchall(
        "SELECT user_id, owed_minor FROM expense_splits WHERE expense_id = ? ORDER BY user_id",
        (expense_id,),
    )
    return {r["user_id"]: r["owed_minor"] for r in rows}


async def get_splits_for_expenses(
    db: Database, expense_ids: Sequence[int]
) -> dict[int, dict[int, int]]:
    """Splits for several expenses at once, keyed by expense id.

    One query instead of one per row: /history shows a full per-person
    breakdown for every entry on the page, and doing that a row at a time
    would be a query per expense.
    """
    if not expense_ids:
        return {}

    placeholders = ",".join("?" * len(expense_ids))
    rows = await db.fetchall(
        f"SELECT expense_id, user_id, owed_minor FROM expense_splits "
        f"WHERE expense_id IN ({placeholders}) ORDER BY expense_id, user_id",
        tuple(expense_ids),
    )

    grouped: dict[int, dict[int, int]] = {}
    for row in rows:
        grouped.setdefault(row["expense_id"], {})[row["user_id"]] = row["owed_minor"]
    return grouped


# ---------------------------------------------------------------------------
# Settlements
# ---------------------------------------------------------------------------


async def create_settlement(
    db: Database,
    *,
    group_id: int,
    payer_id: int,
    payee_id: int,
    amount_minor: int,
    currency_code: str,
    created_by_tg: int,
    idem_key: str,
    supersedes_id: int | None = None,
) -> int:
    """Record that `payer_id` handed `amount_minor` to `payee_id`."""
    if payer_id == payee_id:
        raise ValueError("a settlement needs two different people")
    if amount_minor <= 0:
        raise ValueError("settlement amount must be positive")

    existing = await db.fetchone(
        "SELECT settlement_id FROM settlements WHERE idem_key = ?", (idem_key,)
    )
    if existing is not None:
        return existing["settlement_id"]

    try:
        return await db.execute(
            "INSERT INTO settlements "
            "(group_id, payer_id, payee_id, amount_minor, currency_code, "
            " created_by_tg, supersedes_id, idem_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                group_id,
                payer_id,
                payee_id,
                amount_minor,
                currency_code,
                created_by_tg,
                supersedes_id,
                idem_key,
            ),
        )
    except sqlite3.IntegrityError:
        row = await db.fetchone(
            "SELECT settlement_id FROM settlements WHERE idem_key = ?", (idem_key,)
        )
        if row is not None:
            return row["settlement_id"]
        raise


async def void_settlement(db: Database, settlement_id: int, voided_by_tg: int) -> bool:
    async with db.transaction() as tx:
        rows = await tx.fetchall(
            "SELECT voided_at FROM settlements WHERE settlement_id = ?", (settlement_id,)
        )
        if not rows or rows[0]["voided_at"] is not None:
            return False
        await tx.execute(
            f"UPDATE settlements SET voided_at = {NOW}, voided_by_tg = ? WHERE settlement_id = ?",
            (voided_by_tg, settlement_id),
        )
        return True


async def get_settlement(db: Database, settlement_id: int):
    return await db.fetchone(
        "SELECT * FROM settlements WHERE settlement_id = ?", (settlement_id,)
    )


# ---------------------------------------------------------------------------
# Balance components
#
# Four deliberately dull aggregates. `ledger.py` combines them; see the sign
# convention documented there. Doing this as one clever join would be harder to
# audit, and this is the arithmetic that must not be wrong.
# ---------------------------------------------------------------------------


async def sum_paid_by_user(db: Database, group_id: int) -> dict[int, int]:
    rows = await db.fetchall(
        "SELECT payer_id AS uid, SUM(amount_minor) AS total FROM expenses "
        "WHERE group_id = ? AND voided_at IS NULL GROUP BY payer_id",
        (group_id,),
    )
    return {r["uid"]: r["total"] for r in rows}


async def sum_owed_by_user(db: Database, group_id: int) -> dict[int, int]:
    rows = await db.fetchall(
        "SELECT s.user_id AS uid, SUM(s.owed_minor) AS total "
        "FROM expense_splits s JOIN expenses e ON e.expense_id = s.expense_id "
        "WHERE e.group_id = ? AND e.voided_at IS NULL GROUP BY s.user_id",
        (group_id,),
    )
    return {r["uid"]: r["total"] for r in rows}


async def sum_settlements_sent(db: Database, group_id: int) -> dict[int, int]:
    rows = await db.fetchall(
        "SELECT payer_id AS uid, SUM(amount_minor) AS total FROM settlements "
        "WHERE group_id = ? AND voided_at IS NULL GROUP BY payer_id",
        (group_id,),
    )
    return {r["uid"]: r["total"] for r in rows}


async def sum_settlements_received(db: Database, group_id: int) -> dict[int, int]:
    rows = await db.fetchall(
        "SELECT payee_id AS uid, SUM(amount_minor) AS total FROM settlements "
        "WHERE group_id = ? AND voided_at IS NULL GROUP BY payee_id",
        (group_id,),
    )
    return {r["uid"]: r["total"] for r in rows}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


async def list_history(
    db: Database, group_id: int, limit: int = 10, offset: int = 0
) -> list[Sequence]:
    """Expenses and settlements interleaved, newest first, for /history."""
    return await db.fetchall(
        "SELECT 'expense' AS kind, expense_id AS id, created_at, voided_at, "
        "       amount_minor, currency_code, description, payer_id, NULL AS payee_id "
        "FROM expenses WHERE group_id = ? "
        "UNION ALL "
        "SELECT 'settlement', settlement_id, created_at, voided_at, "
        "       amount_minor, currency_code, NULL, payer_id, payee_id "
        "FROM settlements WHERE group_id = ? "
        "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        (group_id, group_id, limit, offset),
    )


async def count_history(db: Database, group_id: int) -> int:
    return await db.fetchvalue(
        "SELECT (SELECT COUNT(*) FROM expenses WHERE group_id = ?) + "
        "       (SELECT COUNT(*) FROM settlements WHERE group_id = ?)",
        (group_id, group_id),
        default=0,
    )
