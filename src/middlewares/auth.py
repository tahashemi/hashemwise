"""Hashemwise - authorization gate.

An outer middleware on messages and callback queries. Updates from a group that
the super admin has not authorized are dropped before any handler sees them.

`my_chat_member` updates are deliberately *not* routed through this: that is
how a brand-new group gets recorded in the first place.

For every update it lets through, it injects `db`, `group`, `lang`, and
`is_super_admin` into the handler's kwargs, so no handler has to re-fetch the
group or work out which language to answer in.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.admin_prefs import get_admin_lang
from src.db import queries
from src.db.connection import Database
from src.i18n import DEFAULT_LANG, t

log = logging.getLogger(__name__)

# How often a single unauthorized group is told it is unauthorized. Without
# this, a chatty group turns one misconfiguration into a message per line.
REFUSAL_COOLDOWN_SECONDS = 600

GROUP_CHAT_TYPES = {"group", "supergroup"}


class AuthMiddleware(BaseMiddleware):
    def __init__(self, db: Database, super_admin_id: int) -> None:
        self.db = db
        self.super_admin_id = super_admin_id
        self._last_refusal: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data["super_admin_id"] = self.super_admin_id

        user = data.get("event_from_user")
        data["is_super_admin"] = bool(user and user.id == self.super_admin_id)

        chat = data.get("event_chat")
        if chat is None:
            return await handler(event, data)

        if chat.type not in GROUP_CHAT_TYPES:
            # Private chats hold no ledger, so handlers gate themselves. They
            # also have no group language, so they follow the administrator's
            # own toggle instead.
            data["group"] = None
            data["lang"] = await get_admin_lang(self.db)
            return await handler(event, data)

        group = await queries.get_group(self.db, chat.id)

        if group is None:
            # The bot is in a group it has no record of - added while it was
            # down, or the database was reset. Record it and notify the admin
            # through the normal pending-group path.
            await queries.upsert_group(self.db, chat.id, chat.title or str(chat.id))
            group = await queries.get_group(self.db, chat.id)

        if group is None or not group.is_active:
            await self._refuse(event, chat.id, group.lang if group else DEFAULT_LANG)
            return None

        data["group"] = group
        data["lang"] = group.lang
        return await handler(event, data)

    async def _refuse(self, event: TelegramObject, chat_id: int, lang: str) -> None:
        message = t("unauthorized_group", lang)

        if isinstance(event, CallbackQuery):
            # Always answer a callback, cooldown or not, or the client spins.
            await event.answer(message, show_alert=True)
            return

        now = time.monotonic()
        last = self._last_refusal.get(chat_id, 0.0)
        if now - last < REFUSAL_COOLDOWN_SECONDS:
            return
        self._last_refusal[chat_id] = now

        if isinstance(event, Message):
            try:
                await event.answer(message)
            except Exception:  # noqa: BLE001 - kicked, muted, or rate limited
                log.warning("could not send refusal to chat %s", chat_id, exc_info=True)
