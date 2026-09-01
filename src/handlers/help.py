"""Hashemwise - /help.

One message explaining every command and the few behaviours that would
otherwise be surprising (the remainder rule, soft deletes, the currency lock).

The admin section is only shown to the bot administrator: listing commands that
answer "only the bot administrator can do that" is noise for everyone else.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.i18n import t
from src.version import __version__

router = Router(name="help")


def help_text(lang: str, include_admin: bool) -> str:
    sections = [
        t("help_title", lang),
        t("help_intro", lang),
        t("help_start", lang),
        t("help_daily", lang),
    ]
    if include_admin:
        sections.append(t("help_admin", lang))
    sections.append(t("help_notes", lang))
    return "\n\n".join(sections)


@router.message(Command("help", "commands"))
async def help_command(message: Message, lang: str, is_super_admin: bool) -> None:
    await message.answer(
        help_text(lang, include_admin=is_super_admin),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(Command("version"))
async def version_command(message: Message, lang: str) -> None:
    """Report the running version, so a server's state is checkable from chat."""
    await message.answer(t("version_line", lang, version=__version__), parse_mode="HTML")
