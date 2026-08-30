"""Hashemwise - /expense.

amount -> description -> who paid -> who shares -> how to divide -> confirm.

Two steps exist that the original design did not have, and both are there
because their absence produces figures people stop trusting:

* **Who shares it.** Not every expense involves the whole group. Forcing every
  member into every split silently invents debts.
* **A confirmation screen listing every share.** Nothing is written until the
  exact per-person breakdown - remainder included - has been shown.

Custom splits ask for all but the last participant and assign the remainder to
the last one, stated up front. That makes `sum(shares) == total` structurally
true rather than something the user has to hit by hand.
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
from src.handlers.common import (
    MAX_DESCRIPTION_LENGTH,
    answers_prompt,
    ask,
    clean_text,
    money_error_text,
    owned_flow,
)
from src.i18n import t
from src.keyboards import (
    FlowCB,
    confirm_keyboard,
    member_keyboard,
    new_flow_token,
    new_idem_key,
    participants_keyboard,
    split_type_keyboard,
)
from src.money import MoneyError, format_amount, parse_amount, split_equal
from src.render import esc, money, name_of, remainder_note, shares_block
from src.states import ExpenseStates

log = logging.getLogger(__name__)

router = Router(name="expense")


@router.message(Command("expense", "add"), F.chat.type.in_({"group", "supergroup"}))
async def expense_start(
    message: Message, state: FSMContext, db: Database, group: Group, lang: str
) -> None:
    members = await queries.list_members(db, group.group_id)
    if len(members) < 1:
        await message.answer(t("not_setup", lang))
        return

    await state.clear()
    await state.set_state(ExpenseStates.amount)
    await state.update_data(
        flow=new_flow_token(),
        idem=new_idem_key(),
        supersedes=None,
        # Recorded once: ForceReply steps have no callback to read it from,
        # but still have to rebuild keyboards bound to the same owner.
        owner=message.from_user.id,
    )
    await ask(message, state, t("expense_amount", lang, currency=group.currency_code))


@router.message(ExpenseStates.amount)
async def expense_amount(
    message: Message, state: FSMContext, group: Group, lang: str
) -> None:
    state_data = await state.get_data()
    if not answers_prompt(message, state_data):
        return

    try:
        amount_minor = parse_amount(message.text or "", group.currency_code)
    except MoneyError as exc:
        await message.answer(money_error_text(exc, group.currency_code, lang), parse_mode="HTML")
        await ask(message, state, t("expense_amount", lang, currency=group.currency_code))
        return

    await state.update_data(amount=amount_minor)
    await state.set_state(ExpenseStates.description)
    await ask(message, state, t("expense_description", lang))


@router.message(ExpenseStates.description)
async def expense_description(
    message: Message, state: FSMContext, db: Database, group: Group, lang: str
) -> None:
    state_data = await state.get_data()
    if not answers_prompt(message, state_data):
        return

    description = clean_text(message.text)
    if not description:
        await message.answer(t("err_description_empty", lang))
        await ask(message, state, t("expense_description", lang))
        return
    if len(description) > MAX_DESCRIPTION_LENGTH:
        await message.answer(t("err_too_long", lang, limit=MAX_DESCRIPTION_LENGTH))
        await ask(message, state, t("expense_description", lang))
        return

    await state.update_data(description=description)
    await state.set_state(ExpenseStates.payer)

    members = await queries.list_members(db, group.group_id)
    await message.answer(
        t("expense_payer", lang),
        reply_markup=member_keyboard(
            members, state_data["flow"], message.from_user.id, lang, action="payer"
        ),
    )


@router.callback_query(ExpenseStates.payer, FlowCB.filter(F.a == "payer"))
async def expense_payer(
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
    members = await queries.list_members(db, group.group_id)

    # Everyone is selected to begin with: the common case is a whole-group
    # expense, and deselecting is quicker than selecting.
    selected = {m.user_id for m in members}
    await state.update_data(payer=payer_id, selected=sorted(selected))
    await state.set_state(ExpenseStates.participants)

    if callback.message:
        await callback.message.edit_text(
            t("expense_participants", lang),
            reply_markup=participants_keyboard(
                members, selected, callback_data.t, callback_data.o, lang
            ),
        )


@router.callback_query(ExpenseStates.participants, FlowCB.filter(F.a == "tog"))
async def expense_toggle_participant(
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

    selected = set(state_data.get("selected", []))
    user_id = int(callback_data.v)
    selected.symmetric_difference_update({user_id})
    await state.update_data(selected=sorted(selected))

    members = await queries.list_members(db, group.group_id)
    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=participants_keyboard(
                members, selected, callback_data.t, callback_data.o, lang
            )
        )


@router.callback_query(ExpenseStates.participants, FlowCB.filter(F.a == "pdone"))
async def expense_participants_done(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    group: Group,
    lang: str,
) -> None:
    state_data = await owned_flow(callback, state, callback_data, lang)
    if state_data is None:
        return

    if not state_data.get("selected"):
        await callback.answer(t("expense_need_participant", lang), show_alert=True)
        return

    await state.set_state(ExpenseStates.split_type)
    if callback.message:
        await callback.message.edit_text(
            t(
                "expense_split_type",
                lang,
                amount=money(state_data["amount"], group.currency_code, lang),
            ),
            reply_markup=split_type_keyboard(callback_data.t, callback_data.o, lang),
            parse_mode="HTML",
        )


@router.callback_query(ExpenseStates.split_type, FlowCB.filter(F.a == "split"))
async def expense_split_type(
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

    participants = list(state_data["selected"])

    if callback_data.v == "eq":
        shares = split_equal(state_data["amount"], participants, state_data["payer"])
        await state.update_data(shares=shares)
        await _show_confirmation(callback.message, state, db, group, lang, callback_data)
        return

    if len(participants) == 1:
        # Nothing to divide: asking would let the single share disagree with
        # the total, which the confirmation step would then have to reject.
        await state.update_data(shares={participants[0]: state_data["amount"]})
        await _show_confirmation(callback.message, state, db, group, lang, callback_data)
        return

    # Custom: ask for each participant except the last, who takes the balance.
    await state.update_data(custom={}, custom_index=0)
    await state.set_state(ExpenseStates.custom_amount)
    if callback.message:
        await _ask_next_custom_share(callback.message, state, db, group, lang)


@router.message(ExpenseStates.custom_amount)
async def expense_custom_amount(
    message: Message, state: FSMContext, db: Database, group: Group, lang: str
) -> None:
    state_data = await state.get_data()
    if not answers_prompt(message, state_data):
        return

    participants = list(state_data["selected"])
    custom: dict[int, int] = dict(state_data.get("custom", {}))
    index = state_data["custom_index"]
    remaining = state_data["amount"] - sum(custom.values())

    try:
        share = parse_amount(message.text or "", group.currency_code)
    except MoneyError as exc:
        await message.answer(money_error_text(exc, group.currency_code, lang), parse_mode="HTML")
        await _ask_next_custom_share(message, state, db, group, lang)
        return

    if share > remaining:
        await message.answer(
            t(
                "expense_custom_over",
                lang,
                remaining=money(remaining, group.currency_code, lang),
            ),
            parse_mode="HTML",
        )
        await _ask_next_custom_share(message, state, db, group, lang)
        return

    custom[participants[index]] = share
    await state.update_data(custom=custom, custom_index=index + 1)

    if index + 1 >= len(participants) - 1:
        # The last participant takes exactly what is left, so the shares
        # cannot fail to sum to the total.
        custom[participants[-1]] = state_data["amount"] - sum(custom.values())
        await state.update_data(shares=custom)
        await _show_confirmation(message, state, db, group, lang, None)
        return

    await _ask_next_custom_share(message, state, db, group, lang)


async def _ask_next_custom_share(
    message: Message, state: FSMContext, db: Database, group: Group, lang: str
) -> None:
    state_data = await state.get_data()
    participants = list(state_data["selected"])
    custom = dict(state_data.get("custom", {}))
    index = state_data["custom_index"]
    remaining = state_data["amount"] - sum(custom.values())

    members = await queries.list_members(db, group.group_id, include_inactive=True)
    await ask(
        message,
        state,
        t(
            "expense_custom_prompt",
            lang,
            name=name_of(members, participants[index]),
            total=money(state_data["amount"], group.currency_code, lang),
            remaining=money(remaining, group.currency_code, lang),
        ),
    )


async def _show_confirmation(
    message: Message | None,
    state: FSMContext,
    db: Database,
    group: Group,
    lang: str,
    callback_data: FlowCB | None,
) -> None:
    if message is None:
        return

    state_data = await state.get_data()
    members = await queries.list_members(db, group.group_id, include_inactive=True)
    shares = state_data["shares"]

    body = t(
        "expense_confirm",
        lang,
        description=esc(state_data["description"]),
        amount=money(state_data["amount"], group.currency_code, lang),
        payer=name_of(members, state_data["payer"]),
        shares=shares_block(shares, members, state_data["payer"], group.currency_code, lang),
    )
    note = remainder_note(state_data["amount"], shares, group.currency_code, lang)
    if note:
        body = f"{body}\n\n{note}"

    await state.set_state(ExpenseStates.confirm)
    keyboard = confirm_keyboard(state_data["flow"], state_data["owner"], lang)
    if callback_data is not None:
        await message.edit_text(body, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(body, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(ExpenseStates.confirm, FlowCB.filter(F.a == "ok"))
async def expense_confirm(
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
    shares = {int(k): int(v) for k, v in state_data["shares"].items()}

    try:
        await queries.create_expense(
            db,
            group_id=group.group_id,
            payer_id=state_data["payer"],
            amount_minor=state_data["amount"],
            currency_code=group.currency_code,
            description=state_data["description"],
            created_by_tg=callback.from_user.id,
            shares=shares,
            # Constant for the whole wizard, so a double-tapped Confirm hits
            # the unique index instead of writing a second expense.
            idem_key=state_data["idem"],
            supersedes_id=state_data.get("supersedes"),
        )
    except Exception:  # noqa: BLE001
        log.exception("failed to record expense in group %s", group.group_id)
        await state.clear()
        if callback.message:
            await callback.message.edit_text(t("err_unexpected", lang))
        return

    # An edit voids the entry it replaces, and only once the new one is safely
    # written, so a failure mid-way cannot leave the group with neither.
    superseded = state_data.get("supersedes")
    if superseded:
        await queries.void_expense(db, superseded, callback.from_user.id)

    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            t(
                "expense_saved",
                lang,
                description=esc(state_data["description"]),
                amount=format_amount(state_data["amount"], group.currency_code, lang),
                payer=name_of(members, state_data["payer"]),
            ),
            parse_mode="HTML",
        )
