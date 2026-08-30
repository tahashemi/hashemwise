"""Hashemwise - guards and helpers shared by every wizard.

Three problems recur in a group-chat bot, and they are solved once here:

**Anyone can press anyone's buttons.** A group member tapping someone else's
half-finished menu must be refused, not silently acted on under the presser's
own state.

**Stale menus.** An abandoned wizard leaves live buttons in the chat history.
Each carries its flow token, and a token that no longer matches the current
state is refused rather than applied to whatever flow is running now.

**Privacy mode.** Free text only reaches the bot in a group when it is a reply
to one of the bot's own messages, so every text step is asked with ForceReply
and matched back to the exact prompt it answers.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.currencies import get_currency
from src.i18n import t
from src.keyboards import FlowCB, force_reply
from src.money import (
    AmountTooLarge,
    InvalidAmount,
    MoneyError,
    NonPositiveAmount,
    SplitMismatch,
    TooManyDecimals,
)

log = logging.getLogger(__name__)

MAX_DESCRIPTION_LENGTH = 100
MAX_NAME_LENGTH = 40
MAX_MEMBERS_PER_BATCH = 30


async def owned_flow(
    callback: CallbackQuery, state: FSMContext, data: FlowCB, lang: str
) -> dict[str, Any] | None:
    """Return the flow's state data, or None if this press should be ignored.

    Always answers the callback either way - an unanswered callback leaves a
    spinner running on the presser's client.
    """
    if callback.from_user.id != data.o:
        await callback.answer(t("not_your_menu", lang), show_alert=True)
        return None

    state_data = await state.get_data()
    if state_data.get("flow") != data.t:
        await callback.answer(t("menu_expired", lang), show_alert=True)
        return None

    await callback.answer()
    return state_data


async def ask(message: Message, state: FSMContext, text: str) -> None:
    """Ask a free-text question and remember which message asked it."""
    sent = await message.answer(text, reply_markup=force_reply(), parse_mode="HTML")
    await state.update_data(prompt_id=sent.message_id)


def answers_prompt(message: Message, state_data: dict[str, Any]) -> bool:
    """True if this message is the reply to the question we are waiting on."""
    replied = message.reply_to_message
    return bool(
        replied
        and replied.from_user
        and replied.from_user.is_bot
        and replied.message_id == state_data.get("prompt_id")
    )


def money_error_text(exc: Exception, currency_code: str, lang: str) -> str:
    """Translate a money exception into something the user can act on."""
    currency = get_currency(currency_code)
    example = "1,250,000" if currency.decimals == 0 else "12.34"

    if isinstance(exc, TooManyDecimals):
        return t(
            "err_amount_too_precise", lang, currency=currency.code, allowed=exc.allowed
        )
    if isinstance(exc, NonPositiveAmount):
        return t("err_amount_non_positive", lang)
    if isinstance(exc, AmountTooLarge):
        return t("err_amount_too_large", lang)
    if isinstance(exc, InvalidAmount):
        return t("err_amount_invalid", lang, example=example)
    if isinstance(exc, SplitMismatch):
        return t("err_split_mismatch", lang, sum=exc.sum_minor, total=exc.total_minor)
    if isinstance(exc, MoneyError):
        return t(getattr(exc, "key", "err_money"), lang)
    return t("err_unexpected", lang)


async def clear_flow(state: FSMContext) -> None:
    await state.clear()


def clean_text(raw: str | None) -> str:
    """Collapse whitespace in a user-supplied single-line value."""
    return " ".join((raw or "").split())
