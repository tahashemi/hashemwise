"""Does a command actually reach its handler?

Every other test in this suite checks arithmetic, rendering or keyboards. None
of them exercise aiogram's routing, which is the layer where /history silently
stopped working: a handler earlier in the chain consumed the message and the
user saw nothing at all.

These feed real Update objects through the real dispatcher, with a session that
records outgoing API calls instead of making them.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update, User

from src.config import Settings
from src.db import queries
from src.db.connection import Database
from src.main import build_dispatcher
from src.money import split_equal
from tests.conftest import key

GROUP_ID = -1001234567890
ADMIN_ID = 111222333
MEMBER_ID = 444555666


class RecordingSession(BaseSession):
    """Captures API calls instead of performing them."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []

    async def close(self) -> None:  # pragma: no cover - nothing to close
        pass

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        yield b""

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None):
        self.calls.append(method)
        name = type(method).__name__
        if name in {"SendMessage", "EditMessageText"}:
            return Message.model_construct(
                message_id=999,
                date=dt.datetime.now(dt.timezone.utc),
                chat=Chat.model_construct(id=GROUP_ID, type="supergroup"),
                text=getattr(method, "text", ""),
            )
        if name == "GetMe":
            return User.model_construct(id=42, is_bot=True, first_name="Test", username="testbot")
        return True

    # What was actually sent, as plain text.
    def texts(self) -> list[str]:
        return [
            getattr(c, "text", "") for c in self.calls
            if type(c).__name__ in {"SendMessage", "EditMessageText"}
        ]


def make_message(text: str, user_id: int, chat_id: int = GROUP_ID, chat_type: str = "supergroup"):
    return Message.model_construct(
        message_id=1,
        date=dt.datetime.now(dt.timezone.utc),
        chat=Chat.model_construct(id=chat_id, type=chat_type, title="Trip"),
        from_user=User.model_construct(
            id=user_id, is_bot=False, first_name="Tester", username="tester"
        ),
        text=text,
    )


def _detach_routers() -> None:
    """Let each test build its own dispatcher.

    The routers are module-level singletons, so the second Dispatcher to
    include one raises "Router is already attached". Production builds exactly
    one dispatcher and never hits this; the tests need a fresh one per case so
    that FSM state does not leak between them.
    """
    from src.handlers import admin, balances, expense, groups, history, settle, setup
    from src.handlers import help as help_handler

    for module in (groups, admin, setup, help_handler, expense, settle, balances, history):
        module.router._parent_router = None


@pytest_asyncio.fixture
async def wired(tmp_path):
    """A dispatcher, a recording bot, and a group with one expense in it."""
    _detach_routers()
    db = Database(tmp_path / "routing.db")
    await db.connect()

    await queries.upsert_group(db, GROUP_ID, "Trip")
    await queries.set_group_active(db, GROUP_ID, True)
    await queries.mark_group_setup(db, GROUP_ID)
    people = [
        await queries.add_member(db, GROUP_ID, "Ali", tg_user_id=ADMIN_ID),
        await queries.add_member(db, GROUP_ID, "Bita", tg_user_id=MEMBER_ID),
        await queries.add_member(db, GROUP_ID, "Cyrus"),
    ]
    await queries.create_expense(
        db, group_id=GROUP_ID, payer_id=people[0], amount_minor=150_000,
        currency_code="IRT", description="petrol for the trip", created_by_tg=ADMIN_ID,
        shares=split_equal(150_000, people, people[0]), idem_key=key(),
    )

    settings = Settings(_env_file=None, BOT_TOKEN="42:TEST", SUPER_ADMIN_ID=str(ADMIN_ID))
    session = RecordingSession()
    bot = Bot(token="42:TEST", session=session)
    dispatcher = build_dispatcher(db, settings)

    try:
        yield dispatcher, bot, session, db
    finally:
        await db.close()


async def feed(dispatcher, bot, message):
    await dispatcher.feed_update(bot, Update(update_id=1, message=message))


class TestHistoryReaches:
    async def test_admin_gets_the_history(self, wired):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message("/history", ADMIN_ID))
        sent = " ".join(session.texts())
        assert sent, "/history produced no reply at all"
        assert "petrol for the trip" in sent

    async def test_ordinary_member_gets_the_history(self, wired):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message("/history", MEMBER_ID))
        sent = " ".join(session.texts())
        assert sent, "/history produced no reply at all for a group member"
        assert "petrol for the trip" in sent
        assert "Only the bot administrator" not in sent

    async def test_member_sees_each_persons_share(self, wired):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message("/history", MEMBER_ID))
        sent = " ".join(session.texts())
        # 150,000 across three people, payer absorbing the remainder.
        assert "50,000" in sent

    async def test_member_is_sent_no_delete_buttons(self, wired):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message("/history", MEMBER_ID))
        for call in session.calls:
            markup = getattr(call, "reply_markup", None)
            rows = getattr(markup, "inline_keyboard", []) or []
            for row in rows:
                for button in row:
                    assert "hdel" not in (button.callback_data or "")

    async def test_admin_is_sent_delete_buttons(self, wired):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message("/history", ADMIN_ID))
        data = [
            b.callback_data or ""
            for c in session.calls
            for row in (getattr(getattr(c, "reply_markup", None), "inline_keyboard", []) or [])
            for b in row
        ]
        assert any("hdel" in d for d in data)


class TestAnAbandonedWizardDoesNotBlockCommands:
    """The bug: a half-finished /expense swallowed every later command."""

    async def test_history_still_works_after_starting_an_expense(self, wired):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message("/expense", ADMIN_ID))
        session.calls.clear()

        await feed(dispatcher, bot, make_message("/history", ADMIN_ID))
        sent = " ".join(session.texts())
        assert sent, "/history was swallowed by the unfinished expense wizard"
        assert "petrol for the trip" in sent

    async def test_balances_still_works_after_starting_an_expense(self, wired):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message("/expense", ADMIN_ID))
        session.calls.clear()

        await feed(dispatcher, bot, make_message("/balances", ADMIN_ID))
        assert " ".join(session.texts()), "/balances was swallowed"


class TestOtherCommandsRoute:
    @pytest.mark.parametrize("command", ["/balances", "/members", "/help", "/version", "/start"])
    async def test_command_gets_a_reply(self, wired, command):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message(command, MEMBER_ID))
        assert " ".join(session.texts()), f"{command} produced no reply"

    async def test_unauthorized_group_is_refused(self, wired):
        dispatcher, bot, session, db = wired
        await queries.set_group_active(db, GROUP_ID, False)
        await feed(dispatcher, bot, make_message("/history", MEMBER_ID))
        assert "not authorized" in " ".join(session.texts()).lower()
