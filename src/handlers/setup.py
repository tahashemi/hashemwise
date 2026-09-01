"""Hashemwise - /setup, /members, /join, /start, /cancel.

Members are added by *name*, not by @username. Telegram gives bots no way to
resolve a username to a user id, so any design that asked for @mentions would
either fail or quietly create members it cannot link to anyone. Instead setup
creates named members, and each person links their own account afterwards with
/join - which the bot can do, because a /join command carries its sender's id.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.currencies import get_currency
from src.db import queries
from src.db.connection import Database
from src.db.queries import DuplicateMember, Group
from src.handlers.common import (
    MAX_MEMBERS_PER_BATCH,
    MAX_NAME_LENGTH,
    answers_prompt,
    ask,
    clean_text,
    owned_flow,
)
from src.i18n import t
from src.keyboards import (
    FlowCB,
    currency_keyboard,
    language_keyboard,
    member_keyboard,
    new_flow_token,
)
from src.render import esc, members_block
from src.states import SetupStates

log = logging.getLogger(__name__)

router = Router(name="setup")


@router.message(CommandStart())
async def start(message: Message, lang: str) -> None:
    key = "start_group" if message.chat.type in {"group", "supergroup"} else "start_private"
    await message.answer(t(key, lang), parse_mode="HTML")


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext, lang: str) -> None:
    if await state.get_state() is None:
        await message.answer(t("nothing_to_cancel", lang))
        return
    await state.clear()
    await message.answer(t("cancelled", lang))


@router.callback_query(FlowCB.filter(F.a == "cancel"))
async def cancel_button(
    callback: CallbackQuery, callback_data: FlowCB, state: FSMContext, lang: str
) -> None:
    if callback.from_user.id != callback_data.o:
        await callback.answer(t("not_your_menu", lang), show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(t("cancelled", lang))


# ---------------------------------------------------------------------------
# /setup
# ---------------------------------------------------------------------------


@router.message(Command("setup"), F.chat.type.in_({"group", "supergroup"}))
async def setup_start(
    message: Message, state: FSMContext, db: Database, group: Group, lang: str
) -> None:
    await state.clear()

    if await queries.group_has_entries(db, group.group_id):
        # Re-running setup on a live group must not offer to change the
        # currency: the stored minor units are already scaled to the old one
        # and there is no rate to convert them with.
        await message.answer(
            t("setup_currency_locked", lang, currency=group.currency_code), parse_mode="HTML"
        )
        flow = new_flow_token()
        await state.set_state(SetupStates.lang)
        await state.update_data(flow=flow)
        await message.answer(
            t("setup_lang", lang), reply_markup=language_keyboard(flow, message.from_user.id, lang)
        )
        return

    flow = new_flow_token()
    await state.set_state(SetupStates.currency)
    await state.update_data(flow=flow)
    await message.answer(
        t("setup_currency", lang),
        reply_markup=currency_keyboard(flow, message.from_user.id, lang),
    )


@router.callback_query(SetupStates.currency, FlowCB.filter(F.a == "cur"))
async def setup_currency(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
) -> None:
    if await owned_flow(callback, state, callback_data, lang) is None:
        return

    await queries.set_group_currency(db, group.group_id, callback_data.v)

    await state.set_state(SetupStates.lang)
    if callback.message:
        await callback.message.edit_text(
            t("setup_lang", lang),
            reply_markup=language_keyboard(callback_data.t, callback_data.o, lang),
        )


@router.callback_query(SetupStates.lang, FlowCB.filter(F.a == "lang"))
async def setup_language(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
) -> None:
    if await owned_flow(callback, state, callback_data, lang) is None:
        return

    chosen = callback_data.v
    await queries.set_group_lang(db, group.group_id, chosen)

    await state.set_state(SetupStates.members)
    if callback.message:
        # Retire the old keyboard rather than restating the question: ask()
        # below is what poses it, with the ForceReply attached.
        await callback.message.edit_reply_markup(reply_markup=None)
        await ask(callback.message, state, t("setup_members_prompt", chosen))


@router.message(SetupStates.members, F.reply_to_message)
async def setup_members(
    message: Message, state: FSMContext, db: Database, group: Group, lang: str
) -> None:
    state_data = await state.get_data()
    if not answers_prompt(message, state_data):
        return

    names, added, skipped = _parse_names(message.text or ""), [], []
    if not names:
        await ask(message, state, t("setup_members_prompt", lang))
        return

    for name in names[:MAX_MEMBERS_PER_BATCH]:
        try:
            await queries.add_member(db, group.group_id, name)
            added.append(name)
        except DuplicateMember:
            skipped.append(name)

    lines = []
    if added:
        lines.append(t("setup_members_added", lang, names=esc(", ".join(added))))
    if skipped:
        lines.append(t("setup_members_skipped", lang, names=esc(", ".join(skipped))))

    members = await queries.list_members(db, group.group_id)
    if len(members) < 2:
        lines.append(t("setup_need_two_members", lang))
        await message.answer("\n".join(lines), parse_mode="HTML")
        await ask(message, state, t("setup_members_prompt", lang))
        return

    await queries.mark_group_setup(db, group.group_id)
    await state.clear()

    currency = get_currency(group.currency_code)
    lines.append("")
    lines.append(
        t(
            "setup_complete",
            lang,
            currency=currency.name_fa if lang == "fa" else currency.name_en,
            count=len(members),
        )
    )
    await message.answer("\n".join(lines), parse_mode="HTML")


def _parse_names(raw: str) -> list[str]:
    """One name per line, de-duplicated, order preserved."""
    seen: set[str] = set()
    names: list[str] = []
    for line in raw.splitlines():
        name = clean_text(line)[:MAX_NAME_LENGTH]
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            names.append(name)
    return names


# ---------------------------------------------------------------------------
# /members and /join
# ---------------------------------------------------------------------------


@router.message(Command("members"), F.chat.type.in_({"group", "supergroup"}))
async def members_command(message: Message, db: Database, group: Group, lang: str) -> None:
    members = await queries.list_members(db, group.group_id, include_inactive=True)
    await message.answer(members_block(members, lang), parse_mode="HTML")


@router.message(Command("join"), F.chat.type.in_({"group", "supergroup"}))
async def join_command(
    message: Message, state: FSMContext, db: Database, group: Group, lang: str
) -> None:
    """Link the sender's Telegram account to one of the named members."""
    existing = await queries.get_member_by_tg(db, group.group_id, message.from_user.id)
    if existing is not None:
        await message.answer(
            t("join_already", lang, name=esc(existing.display_name)), parse_mode="HTML"
        )
        return

    members = await queries.list_members(db, group.group_id)
    if not members:
        await message.answer(t("not_setup", lang))
        return

    unlinked = [m for m in members if m.tg_user_id is None]
    if not unlinked:
        await message.answer(t("join_none_free", lang))
        return

    flow = new_flow_token()
    await state.clear()
    await state.update_data(flow=flow)
    await message.answer(
        t("join_prompt", lang),
        reply_markup=member_keyboard(unlinked, flow, message.from_user.id, lang, action="join"),
    )


@router.callback_query(FlowCB.filter(F.a == "join"))
async def join_pick(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
) -> None:
    if await owned_flow(callback, state, callback_data, lang) is None:
        return

    member = await queries.get_member(db, int(callback_data.v))
    if member is None or member.group_id != group.group_id:
        await callback.answer(t("err_unexpected", lang), show_alert=True)
        return
    if member.tg_user_id is not None:
        # Someone else claimed this name between the menu opening and the tap.
        if callback.message:
            await callback.message.edit_text(
                t("join_taken", lang, name=esc(member.display_name)), parse_mode="HTML"
            )
        return

    try:
        await db.execute(
            "UPDATE users SET tg_user_id = ? WHERE user_id = ? AND tg_user_id IS NULL",
            (callback.from_user.id, member.user_id),
        )
    except Exception:  # noqa: BLE001 - unique index: this account already has a name here
        log.warning("join failed for user %s", callback.from_user.id, exc_info=True)
        if callback.message:
            await callback.message.edit_text(t("err_unexpected", lang))
        return

    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            t("join_done", lang, name=esc(member.display_name)), parse_mode="HTML"
        )
