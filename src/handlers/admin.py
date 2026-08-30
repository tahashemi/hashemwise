"""Hashemwise - super-admin commands and group onboarding.

Only `SUPER_ADMIN_ID` can authorize a group, revoke it, or list what the bot
has been added to.

Onboarding runs off `my_chat_member`, which is *not* behind the auth
middleware - it is what records an unknown group in the first place. A new
group is stored inactive and the admin gets a DM with an Authorize button, so
approving one never requires being in the group at the time.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from src.db import queries
from src.db.connection import Database
from src.i18n import DEFAULT_LANG, LANG_NAMES, t
from src.keyboards import AdminCB, authorize_keyboard
from src.render import esc

log = logging.getLogger(__name__)

router = Router(name="admin")

# Statuses that mean the bot is now usable in the chat.
PRESENT = {"member", "administrator"}


@router.my_chat_member()
async def on_membership_change(
    event: ChatMemberUpdated, bot: Bot, db: Database, super_admin_id: int
) -> None:
    """Record a group the bot was added to and ask the admin to approve it."""
    chat = event.chat
    if chat.type not in {"group", "supergroup"}:
        return

    was_present = event.old_chat_member.status in PRESENT
    is_present = event.new_chat_member.status in PRESENT
    if was_present or not is_present:
        return  # left, demoted, or already known to be present

    await queries.upsert_group(db, chat.id, chat.title or str(chat.id))
    group = await queries.get_group(db, chat.id)
    if group is not None and group.is_active:
        return  # re-added to a group that was already approved

    try:
        await bot.send_message(
            super_admin_id,
            t(
                "new_group_pending",
                DEFAULT_LANG,
                title=esc(chat.title or str(chat.id)),
                group_id=chat.id,
            ),
            reply_markup=authorize_keyboard(chat.id, DEFAULT_LANG),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001 - admin has never opened a chat with the bot
        log.warning(
            "could not notify super admin about group %s; they can still run /auth there",
            chat.id,
            exc_info=True,
        )


@router.callback_query(AdminCB.filter(F.a == "auth"))
async def authorize_button(
    callback: CallbackQuery, callback_data: AdminCB, db: Database, is_super_admin: bool
) -> None:
    if not is_super_admin:
        await callback.answer(t("admin_only", DEFAULT_LANG), show_alert=True)
        return

    group_id = int(callback_data.v)
    group = await queries.get_group(db, group_id)
    if group is not None and group.is_active:
        await callback.answer(t("auth_already", DEFAULT_LANG), show_alert=True)
        return

    await queries.set_group_active(db, group_id, True)
    await callback.answer()
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(t("auth_done", DEFAULT_LANG))


@router.message(Command("auth"))
async def auth_command(message: Message, db: Database, is_super_admin: bool, lang: str) -> None:
    """Authorize the current group. Only useful when run inside one."""
    if not is_super_admin:
        await message.answer(t("admin_only", lang))
        return
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer(t("group_only", lang))
        return

    await queries.upsert_group(db, message.chat.id, message.chat.title or str(message.chat.id))
    group = await queries.get_group(db, message.chat.id)
    if group is not None and group.is_active:
        await message.answer(t("auth_already", lang))
        return

    await queries.set_group_active(db, message.chat.id, True)
    await message.answer(t("auth_done", lang))


@router.message(Command("deauth"))
async def deauth_command(message: Message, db: Database, is_super_admin: bool, lang: str) -> None:
    """Revoke a group's access. The ledger is kept; only access is withdrawn."""
    if not is_super_admin:
        await message.answer(t("admin_only", lang))
        return
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer(t("group_only", lang))
        return

    await queries.set_group_active(db, message.chat.id, False)
    await message.answer(t("deauth_done", lang))


@router.message(Command("groups"))
async def groups_command(message: Message, db: Database, is_super_admin: bool, lang: str) -> None:
    if not is_super_admin:
        await message.answer(t("admin_only", lang))
        return

    groups = await queries.list_groups(db)
    if not groups:
        await message.answer(t("groups_empty", lang))
        return

    lines = [t("groups_header", lang), ""]
    for g in groups:
        lines.append(
            t(
                "group_row",
                lang,
                mark="✅" if g.is_active else "⛔",
                title=esc(g.title),
                group_id=g.group_id,
                currency=g.currency_code,
                lang=LANG_NAMES.get(g.lang, g.lang),
            )
        )
    await message.answer("\n".join(lines), parse_mode="HTML")
