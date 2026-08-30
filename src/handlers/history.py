"""Hashemwise - /history, restricted to SUPER_ADMIN_ID.

Viewing history, deleting an entry, and editing one are all admin-only in every
group, per the configured permission model.

Deleting is a soft delete: the row is marked voided and stays visible, struck
through, so the record of what happened survives the correction. Editing voids
the old entry and records a replacement that points back at it - and only in
that order, so a failure halfway leaves the original intact rather than
destroying it with nothing to show for it.
"""

from __future__ import annotations

import logging
import math

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.db import queries
from src.db.connection import Database
from src.db.queries import Group
from src.handlers.common import owned_flow
from src.i18n import t
from src.keyboards import FlowCB, delete_confirm_keyboard, history_keyboard, new_flow_token
from src.render import entry_summary, history_block
from src.states import HistoryStates

log = logging.getLogger(__name__)

router = Router(name="history")

PAGE_SIZE = 3


@router.message(Command("history"), F.chat.type.in_({"group", "supergroup"}))
async def history_command(
    message: Message,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not is_super_admin:
        await message.answer(t("admin_only", lang))
        return

    await state.clear()
    flow = new_flow_token()
    await state.set_state(HistoryStates.browsing)
    await state.update_data(flow=flow, owner=message.from_user.id)
    await _render_page(message, db, group, lang, page=1, flow=flow, owner=message.from_user.id)


@router.callback_query(HistoryStates.browsing, FlowCB.filter(F.a == "hpage"))
@router.callback_query(HistoryStates.confirm_delete, FlowCB.filter(F.a == "hpage"))
async def history_page(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not is_super_admin:
        await callback.answer(t("admin_only", lang), show_alert=True)
        return
    if await owned_flow(callback, state, callback_data, lang) is None:
        return

    await state.set_state(HistoryStates.browsing)
    if callback.message:
        await _render_page(
            callback.message,
            db,
            group,
            lang,
            page=int(callback_data.v),
            flow=callback_data.t,
            owner=callback_data.o,
            edit=True,
        )


@router.callback_query(HistoryStates.browsing, FlowCB.filter(F.a == "hdel"))
async def history_delete_prompt(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not is_super_admin:
        await callback.answer(t("admin_only", lang), show_alert=True)
        return
    if await owned_flow(callback, state, callback_data, lang) is None:
        return

    entry = await _load_entry(db, group.group_id, callback_data.v)
    if entry is None:
        await callback.answer(t("err_unexpected", lang), show_alert=True)
        return
    if entry["voided_at"] is not None:
        await callback.answer(t("history_already_deleted", lang), show_alert=True)
        return

    members = await queries.list_members(db, group.group_id, include_inactive=True)
    splits = await queries.get_splits_for_expenses(
        db, [entry["id"]] if entry["kind"] == "expense" else []
    )
    await state.set_state(HistoryStates.confirm_delete)
    if callback.message:
        await callback.message.edit_text(
            t(
                "history_delete_confirm",
                lang,
                summary=entry_summary(entry, members, lang, splits),
            ),
            reply_markup=delete_confirm_keyboard(
                callback_data.v, callback_data.t, callback_data.o, lang
            ),
            parse_mode="HTML",
        )


@router.callback_query(HistoryStates.confirm_delete, FlowCB.filter(F.a == "hdelok"))
async def history_delete(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not is_super_admin:
        await callback.answer(t("admin_only", lang), show_alert=True)
        return
    if await owned_flow(callback, state, callback_data, lang) is None:
        return

    kind, entry_id = _parse_ref(callback_data.v)
    if kind == "expense":
        done = await queries.void_expense(db, entry_id, callback.from_user.id)
    else:
        done = await queries.void_settlement(db, entry_id, callback.from_user.id)

    await state.set_state(HistoryStates.browsing)
    if callback.message:
        await callback.message.edit_text(
            t("history_deleted" if done else "history_already_deleted", lang)
        )
        await _render_page(
            callback.message,
            db,
            group,
            lang,
            page=1,
            flow=callback_data.t,
            owner=callback_data.o,
        )


async def _render_page(
    message: Message,
    db: Database,
    group: Group,
    lang: str,
    *,
    page: int,
    flow: str,
    owner: int,
    edit: bool = False,
) -> None:
    total = await queries.count_history(db, group.group_id)
    if total == 0:
        await message.answer(t("history_empty", lang))
        return

    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(max(page, 1), pages)

    entries = await queries.list_history(
        db, group.group_id, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
    )
    members = await queries.list_members(db, group.group_id, include_inactive=True)
    splits = await queries.get_splits_for_expenses(
        db, [e["id"] for e in entries if e["kind"] == "expense"]
    )

    body = history_block(entries, members, lang, page, pages, splits)
    keyboard = history_keyboard(entries, page, pages, flow, owner, lang)

    if edit:
        await message.edit_text(body, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(body, reply_markup=keyboard, parse_mode="HTML")


def _parse_ref(ref: str) -> tuple[str, int]:
    """`e12` -> ("expense", 12); `s7` -> ("settlement", 7)."""
    return ("expense" if ref[0] == "e" else "settlement"), int(ref[1:])


async def _load_entry(db: Database, group_id: int, ref: str):
    """Fetch an entry, shaped like a history row, and confirm it is this group's.

    The group check matters: callback data is client-supplied, so an admin's
    button from one group must not be able to reach another group's row.
    """
    kind, entry_id = _parse_ref(ref)
    row = (
        await queries.get_expense(db, entry_id)
        if kind == "expense"
        else await queries.get_settlement(db, entry_id)
    )
    if row is None or row["group_id"] != group_id:
        return None

    return {
        "kind": kind,
        "id": entry_id,
        "created_at": row["created_at"],
        "voided_at": row["voided_at"],
        "amount_minor": row["amount_minor"],
        "currency_code": row["currency_code"],
        "description": row["description"] if kind == "expense" else None,
        "payer_id": row["payer_id"],
        "payee_id": row["payee_id"] if kind == "settlement" else None,
    }
