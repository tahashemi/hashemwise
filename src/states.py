"""Hashemwise - finite state machine states.

aiogram keys FSM storage by (bot, chat, user), so two people can run wizards
side by side in the same group without treading on each other.

Each flow's state data carries:
  `flow`  - a short token echoed in every button, so a stale menu from an
            abandoned flow is recognised and refused instead of acted on.
  `idem`  - a full uuid used as the database idempotency key, so a
            double-tapped Confirm cannot write the entry twice. It never
            travels inside callback data.
  `prompt_id` - the message id of the outstanding ForceReply prompt, so a
            reply is matched to the question it actually answers.
"""

from aiogram.fsm.state import State, StatesGroup


class SetupStates(StatesGroup):
    currency = State()
    lang = State()
    members = State()


class ExpenseStates(StatesGroup):
    amount = State()
    description = State()
    payer = State()
    participants = State()
    split_type = State()
    custom_amount = State()
    confirm = State()


class SettleStates(StatesGroup):
    payer = State()
    payee = State()
    amount = State()
    confirm = State()


class HistoryStates(StatesGroup):
    browsing = State()
    confirm_delete = State()
