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
from aiogram.exceptions import TelegramBadRequest
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


SENDS = {"SendMessage", "EditMessageText", "SendRichMessage", "EditRichMessage"}
RICH = {"SendRichMessage", "EditRichMessage"}


def flatten(node) -> list[str]:
    """Every human-readable string in a rich-message payload.

    Only text-bearing fields are collected; `type`, `align` and the like are
    schema, not content, and would let an assertion pass on the word "table".
    """
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [s for item in node for s in flatten(item)]
    if isinstance(node, dict):
        out = []
        for k in ("text", "caption", "html", "markdown", "blocks", "cells"):
            if k in node:
                out += flatten(node[k])
        return out
    return []


class RecordingSession(BaseSession):
    """Captures API calls instead of performing them."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        # Set to make every rich message fail, as an older API server would.
        self.refuse_rich = False

    async def close(self) -> None:  # pragma: no cover - nothing to close
        pass

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        yield b""

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None):
        self.calls.append(method)
        name = type(method).__name__
        if name in RICH and self.refuse_rich:
            raise TelegramBadRequest(method=method, message="Bad Request: method not found")
        if name in SENDS:
            return Message.model_construct(
                message_id=999,
                date=dt.datetime.now(dt.timezone.utc),
                chat=Chat.model_construct(id=GROUP_ID, type="supergroup"),
                text=getattr(method, "text", ""),
            )
        if name == "GetMe":
            return User.model_construct(id=42, is_bot=True, first_name="Test", username="testbot")
        return True

    # What was actually sent, as plain text - rich payloads flattened.
    def texts(self) -> list[str]:
        out = []
        for c in self.calls:
            name = type(c).__name__
            if name in RICH and not self.refuse_rich:
                out.append(" ".join(flatten(c.rich_message)))
            elif name in SENDS and name not in RICH:
                out.append(getattr(c, "text", ""))
        return out

    def kinds(self) -> list[str]:
        return [type(c).__name__ for c in self.calls if type(c).__name__ in SENDS]


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


class TestNativeTables:
    """/history and /balances send real tables, and fall back to text."""

    @pytest.mark.parametrize("command", ["/history", "/balances"])
    async def test_sent_as_a_rich_message(self, wired, command):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message(command, MEMBER_ID))
        assert session.kinds() == ["SendRichMessage"]
        call = session.calls[-1]
        assert call.chat_id == GROUP_ID
        assert any(b["type"] == "table" for b in call.rich_message["blocks"])

    async def test_history_table_keeps_the_page_buttons(self, wired):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message("/history", ADMIN_ID))
        markup = session.calls[-1].reply_markup
        assert markup is not None and markup.inline_keyboard

    async def test_history_table_shows_each_share(self, wired):
        dispatcher, bot, session, _ = wired
        await feed(dispatcher, bot, make_message("/history", MEMBER_ID))
        sent = " ".join(session.texts())
        for expected in ("petrol for the trip", "Ali", "Bita", "Cyrus", "150,000", "50,000"):
            assert expected in sent

    @pytest.mark.parametrize("command", ["/history", "/balances"])
    async def test_refused_table_falls_back_to_text(self, wired, command):
        dispatcher, bot, session, _ = wired
        session.refuse_rich = True
        await feed(dispatcher, bot, make_message(command, MEMBER_ID))
        assert session.kinds() == ["SendRichMessage", "SendMessage"]
        fallback = session.calls[-1].text
        assert fallback, f"{command} fell back to an empty message"
        assert "50,000" in fallback  # Bita's share, or her balance: both 50,000

    async def test_fallback_keeps_the_buttons(self, wired):
        dispatcher, bot, session, _ = wired
        session.refuse_rich = True
        await feed(dispatcher, bot, make_message("/history", ADMIN_ID))
        data = [b.callback_data for row in session.calls[-1].reply_markup.inline_keyboard
                for b in row]
        assert any("hdel" in d for d in data)


class TestDeliverEditing:
    """Paging and delete confirmations replace the message in place."""

    def bot_message(self, bot):
        return Message.model_construct(
            message_id=77,
            date=dt.datetime.now(dt.timezone.utc),
            chat=Chat.model_construct(id=GROUP_ID, type="supergroup"),
            text="",
        ).as_(bot)

    async def test_edit_uses_edit_message_text_with_rich_message(self, wired):
        from src import rich
        from src.telegram_rich import deliver

        _, bot, session, _ = wired
        await deliver(self.bot_message(bot), rich.html_message("<b>x</b>", "en"), "x", edit=True)
        call = session.calls[-1]
        assert type(call).__name__ == "EditRichMessage"
        assert call.__api_method__ == "editMessageText"
        assert (call.chat_id, call.message_id) == (GROUP_ID, 77)
        assert call.rich_message == {"html": "<b>x</b>", "is_rtl": False}

    async def test_refused_edit_falls_back_to_a_text_edit(self, wired):
        from src import rich
        from src.telegram_rich import deliver

        _, bot, session, _ = wired
        session.refuse_rich = True
        await deliver(self.bot_message(bot), rich.html_message("<b>x</b>", "en"), "x", edit=True)
        assert session.kinds() == ["EditRichMessage", "EditMessageText"]

    async def test_oversized_table_skips_straight_to_text(self, wired):
        from src import rich
        from src.telegram_rich import deliver

        _, bot, session, _ = wired
        wide = rich.message([rich.table(["h"] * 21, [["c"] * 21])], "en")
        await deliver(self.bot_message(bot), wide, "fallback")
        assert session.kinds() == ["SendMessage"]

    async def test_payload_serialises_with_the_documented_method_name(self, wired):
        # What actually goes over the wire, through aiogram's own serialiser.
        from src import rich
        from src.telegram_rich import SendRichMessage

        _, bot, session, _ = wired
        method = SendRichMessage(chat_id=GROUP_ID, rich_message=rich.message(
            [rich.table(["a"], [["1"]])], "fa"))
        assert method.__api_method__ == "sendRichMessage"
        dumped = method.model_dump(exclude_none=True)
        assert dumped["rich_message"]["is_rtl"] is True
        assert dumped["rich_message"]["blocks"][0]["cells"][0][0]["is_header"] is True
