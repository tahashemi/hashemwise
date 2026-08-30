"""Keyboards, and the 64-byte callback data limit.

Exceeding the limit fails at send time with an unhelpful error, and only for
users whose ids happen to be long - exactly the kind of bug that reaches
production. These tests use the largest realistic values.
"""

from __future__ import annotations

import pytest

from src.db.queries import Member
from src.keyboards import (
    CALLBACK_DATA_LIMIT,
    FlowCB,
    authorize_keyboard,
    confirm_keyboard,
    currency_keyboard,
    delete_confirm_keyboard,
    history_keyboard,
    language_keyboard,
    member_keyboard,
    new_flow_token,
    new_idem_key,
    participants_keyboard,
    split_type_keyboard,
)

# Telegram user ids are into the 10-digit range; group ids are negative and
# longer still. Use the worst case, not a convenient small number.
BIG_OWNER = 9_999_999_999
BIG_GROUP = -1_009_999_999_999


def members(n: int = 8) -> list[Member]:
    return [
        Member(
            user_id=100_000 + i,
            group_id=BIG_GROUP,
            tg_user_id=BIG_OWNER - i,
            display_name=f"Member With A Fairly Long Name {i}",
            is_active=True,
        )
        for i in range(n)
    ]


def all_data(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def assert_within_limit(markup) -> None:
    for data in all_data(markup):
        assert len(data.encode()) <= CALLBACK_DATA_LIMIT, (len(data.encode()), data)


class TestCallbackDataFitsTheLimit:
    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_currency_keyboard(self, lang):
        assert_within_limit(currency_keyboard(new_flow_token(), BIG_OWNER, lang))

    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_language_keyboard(self, lang):
        assert_within_limit(language_keyboard(new_flow_token(), BIG_OWNER, lang))

    @pytest.mark.parametrize("action", ["payer", "spayer", "spayee", "join"])
    def test_member_keyboard(self, action):
        assert_within_limit(member_keyboard(members(), new_flow_token(), BIG_OWNER, "en", action))

    def test_participants_keyboard(self):
        m = members()
        assert_within_limit(
            participants_keyboard(m, {x.user_id for x in m}, new_flow_token(), BIG_OWNER, "en")
        )

    def test_split_and_confirm_keyboards(self):
        assert_within_limit(split_type_keyboard(new_flow_token(), BIG_OWNER, "en"))
        assert_within_limit(confirm_keyboard(new_flow_token(), BIG_OWNER, "en"))

    def test_authorize_keyboard_with_a_long_group_id(self):
        assert_within_limit(authorize_keyboard(BIG_GROUP, "en"))

    def test_history_keyboards(self):
        entries = [
            {"kind": "expense", "id": 999999, "voided_at": None},
            {"kind": "settlement", "id": 888888, "voided_at": None},
        ]
        assert_within_limit(history_keyboard(entries, 2, 9, new_flow_token(), BIG_OWNER, "en"))
        assert_within_limit(delete_confirm_keyboard("e999999", new_flow_token(), BIG_OWNER, "en"))


class TestCallbackRoundTrip:
    def test_unpacks_to_the_same_values(self):
        packed = FlowCB(t="abcd1234", o=BIG_OWNER, a="payer", v="12345").pack()
        restored = FlowCB.unpack(packed)
        assert (restored.t, restored.o, restored.a, restored.v) == (
            "abcd1234",
            BIG_OWNER,
            "payer",
            "12345",
        )

    def test_valueless_action_round_trips(self):
        # Cancel/Done/Confirm carry no payload. aiogram packs the missing value
        # as an empty string and unpacks it back to None, so the field has to
        # be nullable or every such press raises a validation error.
        restored = FlowCB.unpack(FlowCB(t="abcd1234", o=1, a="cancel").pack())
        assert restored.v is None
        assert restored.a == "cancel"


class TestParticipantsKeyboard:
    def test_selection_state_is_visible(self):
        m = members(3)
        markup = participants_keyboard(m, {m[0].user_id}, "tok12345", BIG_OWNER, "en")
        labels = [b.text for row in markup.inline_keyboard for b in row]
        assert any(label.startswith("✅") for label in labels)
        assert any(label.startswith("⬜") for label in labels)

    def test_every_member_gets_a_button_plus_done_and_cancel(self):
        m = members(5)
        markup = participants_keyboard(m, set(), "tok12345", BIG_OWNER, "en")
        assert len([b for row in markup.inline_keyboard for b in row]) == 5 + 2


class TestMemberKeyboardExclusion:
    def test_excluded_member_is_absent(self):
        m = members(4)
        markup = member_keyboard(m, "tok12345", BIG_OWNER, "en", "spayee", exclude=m[1].user_id)
        assert all(str(m[1].user_id) not in d for d in all_data(markup))


class TestHistoryKeyboard:
    def test_voided_entries_get_no_delete_button(self):
        entries = [
            {"kind": "expense", "id": 1, "voided_at": "2026-01-01T00:00:00Z"},
            {"kind": "expense", "id": 2, "voided_at": None},
        ]
        data = all_data(history_keyboard(entries, 1, 1, "tok12345", BIG_OWNER, "en"))
        assert any("e2" in d for d in data)
        assert not any("e1" in d for d in data)

    def test_paging_buttons_appear_only_where_there_is_a_page(self):
        entries = [{"kind": "expense", "id": 1, "voided_at": None}]
        first = all_data(history_keyboard(entries, 1, 3, "tok12345", BIG_OWNER, "en"))
        middle = all_data(history_keyboard(entries, 2, 3, "tok12345", BIG_OWNER, "en"))
        last = all_data(history_keyboard(entries, 3, 3, "tok12345", BIG_OWNER, "en"))
        assert sum("hpage" in d for d in first) == 1
        assert sum("hpage" in d for d in middle) == 2
        assert sum("hpage" in d for d in last) == 1


class TestTokens:
    def test_flow_token_is_short_enough_to_share_a_callback(self):
        assert len(new_flow_token()) == 8

    def test_idem_key_is_full_length_and_unique(self):
        keys = {new_idem_key() for _ in range(1000)}
        assert len(keys) == 1000
        assert all(len(k) == 32 for k in keys)
