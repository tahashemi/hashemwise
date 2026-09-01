"""Hashemwise - the administrator's group panel, in the bot's private chat.

`/auth` and `/deauth` only work from inside a group, which means managing one
requires being there at the time. This panel lifts that: from the private chat
the administrator can see every group the bot knows about, authorize or revoke
it, add one by chat id, or delete it and its whole ledger.

Two things are deliberate:

**No flow token.** Unlike the group wizards, these buttons carry only an action
and a value. The panel exists solely in the administrator's own private chat and
every handler re-checks `is_super_admin`, which is the actual security boundary.
The upside is that the menu still works after a restart rather than expiring.

**The delete confirmation carries the entry count.** If the group has gained or
lost entries since the menu was drawn, the delete is refused. A destructive
confirmation has to apply to the thing that was shown, not to whatever the group
happens to hold by the time the button is pressed.
"""

from __future__ import annotations

import logging
import math

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.admin_prefs import set_admin_lang
from src.db import queries
from src.db.connection import Database
from src.handlers.common import answers_prompt, ask, clean_text
from src.i18n import CATALOG, LANG_NAMES, t
from src.keyboards import (
    GROUPS_PAGE_SIZE,
    AdminCB,
    group_delete_keyboard,
    group_detail_keyboard,
    groups_panel_keyboard,
)
from src.render import esc
from src.states import AdminStates

log = logging.getLogger(__name__)

router = Router(name="groups")

GROUP_CHAT_TYPES = {"group", "supergroup"}


def _other_lang(lang: str) -> tuple[str, str]:
    """The language the toggle would switch to, and its name."""
    for code, name in LANG_NAMES.items():
        if code != lang:
            return code, name
    return lang, LANG_NAMES.get(lang, lang)


# ---------------------------------------------------------------------------
# The list
# ---------------------------------------------------------------------------


@router.message(Command("groups"), F.chat.type == "private")
async def groups_panel(
    message: Message, state: FSMContext, db: Database, lang: str, is_super_admin: bool
) -> None:
    if not is_super_admin:
        await message.answer(t("admin_only", lang))
        return
    await state.clear()
    await _render_list(message, db, lang, page=1)


@router.callback_query(AdminCB.filter(F.a == "glist"))
async def groups_list_page(
    callback: CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
    db: Database,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not await _admin_only(callback, lang, is_super_admin):
        return
    await state.clear()
    await callback.answer()
    if callback.message:
        await _render_list(callback.message, db, lang, page=int(callback_data.v or 1), edit=True)


async def _render_list(
    message: Message, db: Database, lang: str, *, page: int, edit: bool = False
) -> None:
    groups = await queries.list_groups(db)

    if not groups:
        body = t("panel_empty", lang)
        keyboard = groups_panel_keyboard([], 1, 1, lang, *_other_lang(lang))
    else:
        pages = max(1, math.ceil(len(groups) / GROUPS_PAGE_SIZE))
        page = min(max(page, 1), pages)
        window = groups[(page - 1) * GROUPS_PAGE_SIZE : page * GROUPS_PAGE_SIZE]
        body = (
            t("panel_header", lang, count=len(groups))
            if pages == 1
            else t("panel_page", lang, count=len(groups), page=page, pages=pages)
        )
        keyboard = groups_panel_keyboard(window, page, pages, lang, *_other_lang(lang))

    await _send(message, body, keyboard, edit=edit)


# ---------------------------------------------------------------------------
# One group
# ---------------------------------------------------------------------------


@router.callback_query(AdminCB.filter(F.a == "gopen"))
async def group_open(
    callback: CallbackQuery,
    callback_data: AdminCB,
    db: Database,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not await _admin_only(callback, lang, is_super_admin):
        return
    await callback.answer()
    await _render_detail(callback, db, lang, int(callback_data.v))


@router.callback_query(AdminCB.filter(F.a.in_({"gauth", "grevoke"})))
async def group_set_active(
    callback: CallbackQuery,
    callback_data: AdminCB,
    db: Database,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not await _admin_only(callback, lang, is_super_admin):
        return

    group_id = int(callback_data.v)
    if await queries.get_group(db, group_id) is None:
        await callback.answer(t("group_gone", lang), show_alert=True)
        if callback.message:
            await _render_list(callback.message, db, lang, page=1, edit=True)
        return

    activate = callback_data.a == "gauth"
    await queries.set_group_active(db, group_id, activate)
    await callback.answer(t("group_authorized" if activate else "group_revoked", lang))
    await _render_detail(callback, db, lang, group_id)


async def _render_detail(callback: CallbackQuery, db: Database, lang: str, group_id: int) -> None:
    group = await queries.get_group(db, group_id)
    if group is None:
        if callback.message:
            await _render_list(callback.message, db, lang, page=1, edit=True)
        return

    members = await queries.list_members(db, group_id, include_inactive=True)
    entries = await queries.count_history(db, group_id)

    body = "\n\n".join(
        [
            t(
                "group_detail",
                lang,
                mark="✅" if group.is_active else "⛔",
                title=esc(group.title),
                group_id=group.group_id,
                currency=group.currency_code,
                lang=LANG_NAMES.get(group.lang, group.lang),
                members=len(members),
                entries=entries,
            ),
            t("group_detail_active" if group.is_active else "group_detail_revoked", lang),
        ]
    )
    if callback.message:
        await _send(callback.message, body, group_detail_keyboard(group, lang), edit=True)


# ---------------------------------------------------------------------------
# Deleting a group
# ---------------------------------------------------------------------------


@router.callback_query(AdminCB.filter(F.a == "gdel"))
async def group_delete_prompt(
    callback: CallbackQuery,
    callback_data: AdminCB,
    db: Database,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not await _admin_only(callback, lang, is_super_admin):
        return

    group_id = int(callback_data.v)
    group = await queries.get_group(db, group_id)
    if group is None:
        await callback.answer(t("group_gone", lang), show_alert=True)
        if callback.message:
            await _render_list(callback.message, db, lang, page=1, edit=True)
        return

    members = await queries.list_members(db, group_id, include_inactive=True)
    entries = await queries.count_history(db, group_id)

    await callback.answer()
    if callback.message:
        await _send(
            callback.message,
            t(
                "group_delete_confirm",
                lang,
                title=esc(group.title),
                members=len(members),
                entries=entries,
            ),
            group_delete_keyboard(group_id, entries, lang),
            edit=True,
        )


@router.callback_query(AdminCB.filter(F.a == "gdelok"))
async def group_delete(
    callback: CallbackQuery,
    callback_data: AdminCB,
    db: Database,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not await _admin_only(callback, lang, is_super_admin):
        return

    group_id, _, shown = (callback_data.v or "").partition("|")
    group = await queries.get_group(db, int(group_id))
    if group is None:
        await callback.answer(t("group_gone", lang), show_alert=True)
        if callback.message:
            await _render_list(callback.message, db, lang, page=1, edit=True)
        return

    # Refuse if the group is not the one that was shown on the confirmation.
    current = await queries.count_history(db, group.group_id)
    if str(current) != shown:
        await callback.answer(t("group_changed_since", lang), show_alert=True)
        await _render_detail(callback, db, lang, group.group_id)
        return

    title = group.title
    await queries.delete_group(db, group.group_id)
    log.warning("group %s (%r) deleted by admin with %s entries", group.group_id, title, current)

    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            t("group_deleted", lang, title=esc(title)), parse_mode="HTML"
        )
        await _render_list(callback.message, db, lang, page=1)


# ---------------------------------------------------------------------------
# Adding a group by chat id
# ---------------------------------------------------------------------------


@router.callback_query(AdminCB.filter(F.a == "gadd"))
async def group_add_prompt(
    callback: CallbackQuery, state: FSMContext, lang: str, is_super_admin: bool
) -> None:
    if not await _admin_only(callback, lang, is_super_admin):
        return
    await callback.answer()
    if callback.message:
        await state.set_state(AdminStates.add_group_id)
        await ask(callback.message, state, t("group_add_prompt", lang))


@router.message(AdminStates.add_group_id, F.reply_to_message)
async def group_add(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: Database,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not is_super_admin:
        await state.clear()
        return
    if not answers_prompt(message, await state.get_data()):
        return

    raw = clean_text(message.text).replace(",", "")
    try:
        chat_id = int(raw)
    except ValueError:
        await message.answer(t("group_add_bad_id", lang))
        await ask(message, state, t("group_add_prompt", lang))
        return

    # Resolving the chat proves two things at once: the id is real, and the bot
    # is actually a member. A bot cannot add itself to a group, so an id alone
    # is never enough to go on.
    try:
        chat = await bot.get_chat(chat_id)
    except Exception:  # noqa: BLE001 - not a member, wrong id, or no such chat
        log.info("admin tried to add unreachable chat %s", chat_id, exc_info=True)
        await message.answer(t("group_add_unreachable", lang))
        await ask(message, state, t("group_add_prompt", lang))
        return

    if chat.type not in GROUP_CHAT_TYPES:
        await message.answer(t("group_add_not_a_group", lang))
        await ask(message, state, t("group_add_prompt", lang))
        return

    existed = await queries.get_group(db, chat.id) is not None
    title = chat.title or str(chat.id)
    await queries.upsert_group(db, chat.id, title)
    await queries.set_group_active(db, chat.id, True)

    await state.clear()
    await message.answer(
        t("group_add_already" if existed else "group_add_done", lang, title=esc(title)),
        parse_mode="HTML",
    )
    await _render_list(message, db, lang, page=1)


# ---------------------------------------------------------------------------
# Language toggle
# ---------------------------------------------------------------------------


@router.callback_query(AdminCB.filter(F.a == "glang"))
async def admin_set_language(
    callback: CallbackQuery,
    callback_data: AdminCB,
    db: Database,
    lang: str,
    is_super_admin: bool,
) -> None:
    if not await _admin_only(callback, lang, is_super_admin):
        return

    chosen = callback_data.v if callback_data.v in CATALOG else lang
    await set_admin_lang(db, chosen)
    await callback.answer(t("admin_lang_set", chosen, name=LANG_NAMES.get(chosen, chosen)))
    if callback.message:
        await _render_list(callback.message, db, chosen, page=1, edit=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_only(callback: CallbackQuery, lang: str, is_super_admin: bool) -> bool:
    """Answer and refuse if the presser is not the administrator."""
    if is_super_admin:
        return True
    await callback.answer(t("admin_only", lang), show_alert=True)
    return False


async def _send(message: Message, body: str, keyboard, *, edit: bool) -> None:
    """Edit in place where possible, fall back to a new message.

    Telegram rejects an edit whose text and markup are both unchanged, and
    treats an edit of a message it did not send as an error; neither is worth
    failing the whole interaction over.
    """
    if edit:
        try:
            await message.edit_text(body, reply_markup=keyboard, parse_mode="HTML")
            return
        except Exception:  # noqa: BLE001
            log.debug("could not edit panel message, sending a new one", exc_info=True)
    await message.answer(body, reply_markup=keyboard, parse_mode="HTML")
