"""Hashemwise - /settle.

Records that one person physically handed money to another: who sent, who
received, how much. Overpaying is allowed and simply moves the sender into
credit, which is what actually happens in life.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.db import queries
from src.db.connection import Database
from src.db.queries import Group
from src.handlers.common import answers_prompt, ask, money_error_text, owned_flow
from src.i18n import t
from src.keyboards import (
    FlowCB,
    confirm_keyboard,
    member_keyboard,
    new_flow_token,
    new_idem_key,
)
from src.money import MoneyError, parse_amount
from src.render import money, name_of
from src.states import SettleStates

log = logging.getLogger(__name__)

router = Router(name="settle")


@router.message(Command("settle"), F.chat.type.in_({"group", "supergroup"}))
async def settle_start(
    message: Message, state: FSMContext, db: Database, group: Group, lang: str
) -> None:
    members = await queries.list_members(db, group.group_id)
    if len(members) < 2:
        await message.answer(t("not_setup", lang))
        return

    await state.clear()
    await state.set_state(SettleStates.payer)
    flow = new_flow_token()
    await state.update_data(flow=flow, idem=new_idem_key(), owner=message.from_user.id)
    await message.answer(
        t("settle_payer", lang),
        reply_markup=member_keyboard(members, flow, message.from_user.id, lang, action="spayer"),
    )


@router.callback_query(SettleStates.payer, FlowCB.filter(F.a == "spayer"))
async def settle_payer(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
) -> None:
    if await owned_flow(callback, state, callback_data, lang) is None:
        return

    payer_id = int(callback_data.v)
    await state.update_data(payer=payer_id)
    await state.set_state(SettleStates.payee)

    members = await queries.list_members(db, group.group_id)
    if callback.message:
        await callback.message.edit_text(
            t("settle_payee", lang),
            # Excluding the payer makes a self-payment unreachable rather than
            # something the database has to reject afterwards.
            reply_markup=member_keyboard(
                members, callback_data.t, callback_data.o, lang, action="spayee", exclude=payer_id
            ),
        )


@router.callback_query(SettleStates.payee, FlowCB.filter(F.a == "spayee"))
async def settle_payee(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
) -> None:
    state_data = await owned_flow(callback, state, callback_data, lang)
    if state_data is None:
        return

    payee_id = int(callback_data.v)
    if payee_id == state_data["payer"]:
        await callback.answer(t("settle_same_person", lang), show_alert=True)
        return

    await state.update_data(payee=payee_id)
    await state.set_state(SettleStates.amount)

    members = await queries.list_members(db, group.group_id, include_inactive=True)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await ask(
            callback.message,
            state,
            t(
                "settle_amount",
                lang,
                payer=name_of(members, state_data["payer"]),
                payee=name_of(members, payee_id),
                currency=group.currency_code,
            ),
        )


@router.message(SettleStates.amount, F.reply_to_message)
async def settle_amount(
    message: Message, state: FSMContext, db: Database, group: Group, lang: str
) -> None:
    state_data = await state.get_data()
    if not answers_prompt(message, state_data):
        return

    members = await queries.list_members(db, group.group_id, include_inactive=True)
    try:
        amount_minor = parse_amount(message.text or "", group.currency_code)
    except MoneyError as exc:
        await message.answer(money_error_text(exc, group.currency_code, lang), parse_mode="HTML")
        await ask(
            message,
            state,
            t(
                "settle_amount",
                lang,
                payer=name_of(members, state_data["payer"]),
                payee=name_of(members, state_data["payee"]),
                currency=group.currency_code,
            ),
        )
        return

    await state.update_data(amount=amount_minor)
    await state.set_state(SettleStates.confirm)
    await message.answer(
        t(
            "settle_confirm",
            lang,
            payer=name_of(members, state_data["payer"]),
            payee=name_of(members, state_data["payee"]),
            amount=money(amount_minor, group.currency_code, lang),
        ),
        reply_markup=confirm_keyboard(state_data["flow"], state_data["owner"], lang),
        parse_mode="HTML",
    )


@router.callback_query(SettleStates.confirm, FlowCB.filter(F.a == "ok"))
async def settle_confirm(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
) -> None:
    state_data = await owned_flow(callback, state, callback_data, lang)
    if state_data is None:
        return

    members = await queries.list_members(db, group.group_id, include_inactive=True)
    try:
        await queries.create_settlement(
            db,
            group_id=group.group_id,
            payer_id=state_data["payer"],
            payee_id=state_data["payee"],
            amount_minor=state_data["amount"],
            currency_code=group.currency_code,
            created_by_tg=callback.from_user.id,
            idem_key=state_data["idem"],
        )
    except Exception:  # noqa: BLE001
        log.exception("failed to record settlement in group %s", group.group_id)
        await state.clear()
        if callback.message:
            await callback.message.edit_text(t("err_unexpected", lang))
        return

    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            t(
                "settle_saved",
                lang,
                payer=name_of(members, state_data["payer"]),
                payee=name_of(members, state_data["payee"]),
                amount=money(state_data["amount"], group.currency_code, lang),
            ),
            parse_mode="HTML",
        )
