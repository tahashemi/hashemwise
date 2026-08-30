"""Hashemwise - /balances.

Shows each person's net position and the payments that would clear the group.

If the ledger's sum-to-zero invariant is ever violated the numbers are not
shown at all. A shared-expense bot that displays confident wrong figures is
worse than one that admits it has a problem, because people act on what it
says.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from src.db import queries
from src.db.connection import Database
from src.db.queries import Group
from src.debt_engine import LedgerImbalance, reduce_debts
from src.i18n import t
from src.ledger import net_balances
from src.render import balances_block, plan_block

log = logging.getLogger(__name__)

router = Router(name="balances")


@router.message(Command("balances", "balance"), F.chat.type.in_({"group", "supergroup"}))
async def balances_command(
    message: Message,
    bot: Bot,
    db: Database,
    group: Group,
    lang: str,
    super_admin_id: int,
) -> None:
    members = await queries.list_members(db, group.group_id, include_inactive=True)
    if not members:
        await message.answer(t("not_setup", lang))
        return

    if not await queries.group_has_entries(db, group.group_id):
        await message.answer(t("no_entries_yet", lang))
        return

    try:
        balances = await net_balances(db, group.group_id)
        plan = reduce_debts(balances)
    except LedgerImbalance as exc:
        await message.answer(t("err_ledger_imbalance", lang))
        await _alert_admin(bot, super_admin_id, group, exc)
        return

    parts = [balances_block(balances, members, group.currency_code, lang)]
    suggestion = plan_block(plan, members, group.currency_code, lang)
    if suggestion:
        parts.append(suggestion)

    await message.answer("\n\n".join(parts), parse_mode="HTML")


async def _alert_admin(bot: Bot, super_admin_id: int, group: Group, exc: LedgerImbalance) -> None:
    log.error("ledger imbalance in group %s: residual %s", group.group_id, exc.residual)
    try:
        await bot.send_message(
            super_admin_id,
            f"Ledger imbalance in {group.title} ({group.group_id}): "
            f"balances sum to {exc.residual} instead of 0.",
        )
    except Exception:  # noqa: BLE001 - never let the alert mask the original problem
        log.warning("could not alert super admin about the imbalance", exc_info=True)
