"""Hashemwise - sending rich messages through aiogram.

aiogram 3.15 predates Bot API 10.1, so it has no `sendRichMessage` and its
`EditMessageText` has no `rich_message` field. Declaring them as methods here,
rather than posting to the HTTP API directly, means they travel through the
bot's own session: the configured proxy, timeouts and error mapping all apply,
and the routing tests' recording session sees them like any other call.

Every send carries the existing text layout as a fallback. A rich message that
Telegram rejects - an older Bot API server, a table over the documented limits,
a field this module got wrong - must degrade to the message people already had,
never to no reply at all. `/history` has gone silent before, and the fallback
exists so a new feature cannot do that again.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

from aiogram.exceptions import TelegramAPIError
from aiogram.methods.base import TelegramMethod
from aiogram.types import InlineKeyboardMarkup, Message

from src import rich

log = logging.getLogger(__name__)


class SendRichMessage(TelegramMethod[Message]):
    """https://core.telegram.org/bots/api#sendrichmessage"""

    __returning__ = Message
    __api_method__ = "sendRichMessage"

    chat_id: Union[int, str]
    rich_message: dict[str, Any]
    message_thread_id: Optional[int] = None
    reply_markup: Optional[InlineKeyboardMarkup] = None


class EditRichMessage(TelegramMethod[Union[Message, bool]]):
    """`editMessageText` with `rich_message` in place of `text`.

    https://core.telegram.org/bots/api#editmessagetext
    """

    __returning__ = Union[Message, bool]
    __api_method__ = "editMessageText"

    chat_id: Union[int, str]
    message_id: int
    rich_message: dict[str, Any]
    reply_markup: Optional[InlineKeyboardMarkup] = None


async def deliver(
    message: Message,
    rich_message: dict,
    fallback_html: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    edit: bool = False,
) -> None:
    """Send (or edit `message` into) a rich message; on failure, the text one.

    With `edit=False`, `message` is the message being answered and the reply
    goes to its chat. With `edit=True`, `message` is the bot's own message and
    it is replaced in place.
    """
    bot = message.bot
    if rich.fits(rich_message):
        try:
            if edit:
                await bot(
                    EditRichMessage(
                        chat_id=message.chat.id,
                        message_id=message.message_id,
                        rich_message=rich_message,
                        reply_markup=reply_markup,
                    )
                )
            else:
                await bot(
                    SendRichMessage(
                        chat_id=message.chat.id,
                        message_thread_id=message.message_thread_id
                        if message.is_topic_message
                        else None,
                        rich_message=rich_message,
                        reply_markup=reply_markup,
                    )
                )
            return
        except TelegramAPIError as exc:
            log.warning("rich message refused, sending text instead: %s", exc)

    if edit:
        await message.edit_text(fallback_html, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await message.answer(fallback_html, reply_markup=reply_markup, parse_mode="HTML")
