"""Hashemwise - preferences belonging to the bot administrator, not a group.

Its own module so that both the auth middleware and the group panel can reach
it without the middleware having to import a handler, which would invert the
layering.

The administrator's private chat has no group, and therefore no group language
setting, so the language it speaks is stored here instead.
"""

from __future__ import annotations

from src.db import queries
from src.db.connection import Database
from src.i18n import CATALOG, DEFAULT_LANG

ADMIN_LANG_KEY = "admin_lang"


async def get_admin_lang(db: Database, default: str = DEFAULT_LANG) -> str:
    """The language for the administrator's private chat.

    Falls back to the default when unset, and also when a language was stored
    that this build no longer ships - a downgrade should not leave the panel
    rendering raw translation keys.
    """
    stored = await queries.get_setting(db, ADMIN_LANG_KEY)
    return stored if stored in CATALOG else default


async def set_admin_lang(db: Database, lang: str) -> None:
    await queries.set_setting(db, ADMIN_LANG_KEY, lang)
