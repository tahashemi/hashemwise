"""Hashemwise - entry point.

Long polling, not webhooks: it needs no inbound port, no TLS certificate, and
no public hostname, which is what makes `docker compose up` on any Linux box
the whole deployment story.

Router order matters. `admin` is first so /auth still works in a group that is
not yet authorized, and `setup` carries /start and /cancel, which must stay
reachable from inside any half-finished wizard.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from src.config import Settings, get_settings
from src.db.connection import Database
from src.handlers import admin, balances, expense, groups, history, settle, setup
from src.handlers import help as help_handler
from src.i18n.en import COMMANDS as EN_COMMANDS
from src.i18n.fa import COMMANDS as FA_COMMANDS
from src.middlewares.auth import AuthMiddleware
from src.version import __version__

COMMAND_MENUS = {"en": EN_COMMANDS, "fa": FA_COMMANDS}

# Logged once Telegram has accepted the token. install.sh waits for this exact
# string; a test asserts the two agree.
READY_MARKER = "startup complete:"

log = logging.getLogger("hashemwise")


def build_dispatcher(db: Database, settings: Settings) -> Dispatcher:
    # MemoryStorage: an in-progress wizard does not survive a restart, which is
    # an acceptable trade for having no second service to run. Nothing is
    # written until Confirm, so a lost flow loses no ledger data - the user
    # just starts over.
    dispatcher = Dispatcher(storage=MemoryStorage())

    auth = AuthMiddleware(db, settings.super_admin_id)
    dispatcher.message.outer_middleware(auth)
    dispatcher.callback_query.outer_middleware(auth)

    # my_chat_member is deliberately left ungated: it is how an unknown group
    # gets recorded and surfaced to the admin in the first place.
    dispatcher.my_chat_member.outer_middleware(_inject_dependencies(db, settings))

    # `groups` before `admin` so the interactive panel claims /groups in a
    # private chat; admin's plain-text version keeps it inside a group.
    for module in (groups, admin, setup, help_handler, expense, settle, balances, history):
        dispatcher.include_router(module.router)

    return dispatcher


def _inject_dependencies(db: Database, settings: Settings):
    async def middleware(handler, event, data):
        data["db"] = db
        data["super_admin_id"] = settings.super_admin_id
        return await handler(event, data)

    return middleware


def build_bot(settings: Settings) -> Bot:
    # api.telegram.org is unreachable on some networks; the proxy is opt-in and
    # empty by default.
    session = AiohttpSession(proxy=settings.telegram_proxy) if settings.telegram_proxy else None
    return Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def command_menu(lang: str) -> list[BotCommand]:
    return [
        BotCommand(command=name, description=description)
        for name, description in COMMAND_MENUS[lang]
    ]


async def publish_commands(bot: Bot) -> None:
    """Fill in Telegram's own "/" menu, so the commands are discoverable
    without anyone having to read /help first.

    English is published twice: once under "en", and once with no
    language_code as the fallback every other client sees.
    """
    await bot.set_my_commands(command_menu("en"))
    for lang in COMMAND_MENUS:
        await bot.set_my_commands(command_menu(lang), language_code=lang)


async def run() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    db = Database(settings.db_path)
    await db.connect()
    log.info("ledger opened at %s", settings.db_path)

    bot = build_bot(settings)
    dispatcher = build_dispatcher(db, settings)

    try:
        me = await bot.get_me()
        # install.sh greps for READY_MARKER to decide whether the bot actually
        # authenticated, rather than trusting that the container is "running" -
        # a bad token produces a crash loop that looks running every few
        # seconds. Change this string and you must change install.sh with it.
        log.info(
            "%s Hashemwise v%s as @%s (super admin %s)",
            READY_MARKER,
            __version__,
            me.username,
            settings.super_admin_id,
        )
        # Drop anything queued while the bot was down: replaying a week of
        # stale button presses against fresh state would be worse than
        # losing them.
        await bot.delete_webhook(drop_pending_updates=True)
        await publish_commands(bot)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()
        await db.close()
        log.info("stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
