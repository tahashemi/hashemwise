"""Message rendering.

A display bug is indistinguishable from a calculation bug to whoever reads the
message, so the formatting gets the same treatment as the arithmetic.
"""

from __future__ import annotations

import pytest

from src.db.queries import Member
from src.debt_engine import Transfer
from src.render import (
    balances_block,
    entry_summary,
    esc,
    history_block,
    members_block,
    name_of,
    plan_block,
    remainder_note,
    display_id,
    shares_block,
    split_table,
)

ALI, BITA, CYRUS = 1, 2, 3


def member(uid, name, tg=None, active=True):
    return Member(
        user_id=uid, group_id=-100, tg_user_id=tg, display_name=name, is_active=active
    )


MEMBERS = [member(ALI, "Ali", 101), member(BITA, "Bita", 102), member(CYRUS, "Cyrus")]


class TestEscaping:
    def test_angle_brackets_escaped(self):
        # Telegram parses the message as HTML; an unescaped name breaks it.
        assert esc("<b>hax</b>") == "&lt;b&gt;hax&lt;/b&gt;"

    def test_ampersand_escaped(self):
        assert esc("Tom & Jerry") == "Tom &amp; Jerry"

    def test_member_names_are_escaped_in_every_block(self):
        hostile = [member(ALI, "<script>"), member(BITA, "Bita")]
        assert "<script>" not in balances_block({ALI: 100, BITA: -100}, hostile, "IRT", "en")
        assert "<script>" not in shares_block({ALI: 50, BITA: 50}, hostile, ALI, "IRT", "en")
        assert "<script>" not in members_block(hostile, "en")

    def test_unknown_user_id_degrades_visibly(self):
        assert name_of(MEMBERS, 999) == "#999"


class TestSharesBlock:
    def test_payer_is_marked_and_listed_first(self):
        out = shares_block({ALI: 100, BITA: 100, CYRUS: 100}, MEMBERS, BITA, "IRT", "en")
        assert out.splitlines()[0].strip().startswith("Bita")
        assert "(payer)" in out.splitlines()[0]

    def test_every_participant_appears(self):
        out = shares_block({ALI: 34, BITA: 33, CYRUS: 33}, MEMBERS, ALI, "IRT", "en")
        assert len(out.splitlines()) == 3
        for name in ("Ali", "Bita", "Cyrus"):
            assert name in out

    def test_amounts_are_formatted_for_the_currency(self):
        assert "$1.00" in shares_block({ALI: 100}, MEMBERS, ALI, "USD", "en")
        assert "100 T" in shares_block({ALI: 100}, MEMBERS, ALI, "IRT", "en")


class TestRemainderNote:
    def test_uneven_split_is_disclosed(self):
        # The payer carries one extra unit; the user must see that, not
        # discover it later in the balances.
        assert remainder_note(100, {ALI: 34, BITA: 33, CYRUS: 33}, "IRT", "en")

    def test_clean_split_says_nothing(self):
        assert remainder_note(90, {ALI: 30, BITA: 30, CYRUS: 30}, "IRT", "en") == ""

    def test_single_participant_says_nothing(self):
        assert remainder_note(90, {ALI: 90}, "IRT", "en") == ""


class TestBalancesBlock:
    def test_settled_group_says_so(self):
        assert "square" in balances_block({ALI: 0, BITA: 0}, MEMBERS, "IRT", "en").lower()

    def test_creditors_listed_before_debtors(self):
        out = balances_block({ALI: -100, BITA: 300, CYRUS: -200}, MEMBERS, "IRT", "en")
        lines = out.splitlines()[1:]
        assert "Bita" in lines[0]  # the only creditor comes first

    def test_debts_are_shown_as_positive_amounts(self):
        # "Ali owes -100" would be nonsense; the sign is carried by the wording.
        out = balances_block({ALI: -100, BITA: 100}, MEMBERS, "IRT", "en")
        assert "-100" not in out
        assert "owes 100 T" in out

    def test_larger_amounts_come_first_within_a_group(self):
        out = balances_block({ALI: -100, BITA: 300, CYRUS: -200}, MEMBERS, "IRT", "en")
        assert out.index("Cyrus") < out.index("Ali")

    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_renders_in_both_languages(self, lang):
        assert balances_block({ALI: 100, BITA: -100}, MEMBERS, "IRT", lang).strip()


class TestPlanBlock:
    def test_empty_plan_renders_nothing(self):
        assert plan_block([], MEMBERS, "IRT", "en") == ""

    def test_each_transfer_names_both_parties_and_the_amount(self):
        out = plan_block([Transfer(CYRUS, ALI, 50_000)], MEMBERS, "IRT", "en")
        assert "Cyrus" in out and "Ali" in out and "50,000 T" in out

    def test_count_is_reported(self):
        out = plan_block(
            [Transfer(CYRUS, ALI, 50_000), Transfer(CYRUS, BITA, 10_000)],
            MEMBERS, "IRT", "en",
        )
        assert "2" in out


class TestMembersBlock:
    def test_ghost_member_is_flagged(self):
        assert "no Telegram account" in members_block(MEMBERS, "en")

    def test_inactive_member_is_struck_through(self):
        out = members_block([member(ALI, "Ali", 101, active=False)], "en")
        assert "<s>" in out

    def test_empty_list(self):
        assert members_block([], "en")


class TestSplitTable:
    def test_every_person_gets_a_row(self):
        out = split_table({ALI: 50_000, BITA: 50_000, CYRUS: 50_000}, MEMBERS, "IRT", "en")
        assert out.count("\n") == 2
        for name in ("Ali", "Bita", "Cyrus"):
            assert name in out

    def test_columns_are_aligned(self):
        # The whole point of a table: every row the same width, so the amounts
        # line up when read on a phone.
        out = split_table({ALI: 1_000, BITA: 250_000, CYRUS: 50}, MEMBERS, "IRT", "en")
        rows = out.replace("<pre>", "").replace("</pre>", "").split("\n")
        assert len({len(r) for r in rows}) == 1

    def test_amounts_are_right_aligned(self):
        out = split_table({ALI: 1_000, BITA: 250_000}, MEMBERS, "IRT", "en")
        rows = out.replace("<pre>", "").replace("</pre>", "").split("\n")
        assert all(r.endswith("T") for r in rows)

    def test_payer_is_listed_first(self):
        out = split_table({ALI: 50, BITA: 50, CYRUS: 50}, MEMBERS, "IRT", "en", payer_id=CYRUS)
        assert out.index("Cyrus") < out.index("Ali")

    def test_wrapped_in_pre_for_monospace(self):
        out = split_table({ALI: 50}, MEMBERS, "IRT", "en")
        assert out.startswith("<pre>") and out.endswith("</pre>")

    def test_long_names_are_truncated_so_columns_cannot_wrap(self):
        long_member = [member(ALI, "A" * 40)]
        out = split_table({ALI: 50}, long_member, "IRT", "en")
        assert "A" * 40 not in out

    def test_names_are_escaped_inside_the_block(self):
        out = split_table({ALI: 50}, [member(ALI, "a<b>&c")], "IRT", "en")
        assert "<b>" not in out.replace("<pre>", "").replace("</pre>", "")

    def test_width_measured_before_escaping(self):
        # "&" becomes "&amp;" once escaped. If widths were measured after
        # escaping, that row would be padded five columns too wide.
        out = split_table({ALI: 50, BITA: 60}, [member(ALI, "A&B"), member(BITA, "Bita")],
                          "IRT", "en")
        rows = out.replace("<pre>", "").replace("</pre>", "").split("\n")
        assert len(rows[0].replace("&amp;", "&")) == len(rows[1])

    def test_persian_rows_are_direction_pinned(self):
        # Without an LRM the bidi algorithm reorders the columns in an RTL
        # context and the table stops lining up.
        assert "‎" in split_table({ALI: 50}, MEMBERS, "IRT", "fa")

    def test_english_rows_are_not_pinned(self):
        assert "‎" not in split_table({ALI: 50}, MEMBERS, "IRT", "en")

    def test_empty_shares(self):
        assert split_table({}, MEMBERS, "IRT", "en") == ""


class TestHistoryBlock:
    def _rows(self):
        return [
            {
                "kind": "expense", "id": 7, "voided_at": None, "amount_minor": 150_000,
                "currency_code": "IRT", "description": "dinner",
                "payer_id": ALI, "payee_id": None,
                "created_at": "2026-08-30T18:16:12.345Z",
            },
            {
                "kind": "settlement", "id": 3, "voided_at": "2026-01-01T00:00:00Z",
                "amount_minor": 100, "currency_code": "IRT", "description": None,
                "payer_id": BITA, "payee_id": ALI,
                "created_at": "2026-08-29T09:00:00.000Z",
            },
        ]

    def _splits(self):
        return {7: {ALI: 50_000, BITA: 50_000, CYRUS: 50_000}}

    def test_both_kinds_render(self):
        out = history_block(self._rows(), MEMBERS, "en", 1, 1, self._splits())
        assert "dinner" in out and "Bita" in out

    def test_expense_shows_what_each_person_was_charged(self):
        out = history_block(self._rows(), MEMBERS, "en", 1, 1, self._splits())
        assert "<pre>" in out
        # Count inside the table only: the header's "150,000 T" total contains
        # "50,000 T" as a substring.
        table = out.split("<pre>")[1].split("</pre>")[0]
        assert table.count("50,000 T") == 3
        assert "150,000 T" in out  # and the total is still on the header line

    def test_settlement_has_no_breakdown(self):
        # Two named people and one amount; a table would just restate it.
        settlement = [self._rows()[1]]
        assert "<pre>" not in history_block(settlement, MEMBERS, "en", 1, 1, {})

    def test_date_is_shown_and_trimmed(self):
        out = history_block(self._rows(), MEMBERS, "en", 1, 1, self._splits())
        assert "2026-08-30 18:16" in out
        assert ".345Z" not in out

    def test_expense_with_no_splits_still_renders(self):
        out = history_block(self._rows(), MEMBERS, "en", 1, 1, {})
        assert "dinner" in out and "<pre>" not in out

    def test_voided_entry_is_struck_through(self):
        assert "<s>" in history_block(self._rows(), MEMBERS, "en", 1, 1, self._splits())

    def test_page_numbers_shown(self):
        assert "2" in history_block(self._rows(), MEMBERS, "en", 2, 4, self._splits())

    def test_empty_history(self):
        assert history_block([], MEMBERS, "en", 1, 1, {})

    @pytest.mark.parametrize("lang", ["en", "fa"])
    def test_renders_in_both_languages(self, lang):
        assert history_block(self._rows(), MEMBERS, lang, 1, 1, self._splits()).strip()

    def test_entry_summary_covers_both_kinds(self):
        for row in self._rows():
            assert entry_summary(row, MEMBERS, "en", self._splits()).strip()

    def test_entry_summary_includes_the_breakdown(self):
        assert "<pre>" in entry_summary(self._rows()[0], MEMBERS, "en", self._splits())

    def test_expense_and_settlement_ids_never_collide(self):
        # Both sequences start at 1, so a bare "#1" could mean either. The
        # kind letter is what makes the label and the delete button agree.
        clash = [dict(self._rows()[0], id=1), dict(self._rows()[1], id=1)]
        out = history_block(clash, MEMBERS, "en", 1, 1, {})
        assert "E1" in out and "S1" in out
        assert out.count("#E1") == 1 and out.count("#S1") == 1


class TestDisplayId:
    def test_expense_prefix(self):
        assert display_id({"kind": "expense", "id": 7}) == "E7"

    def test_settlement_prefix(self):
        assert display_id({"kind": "settlement", "id": 7}) == "S7"
