"""Native tables (Bot API rich messages).

Two things are checked here. The payload shape, against the documented schema,
because Telegram only says a field is wrong at send time and nothing else in
this suite talks to Telegram. And the numbers in the cells, because a table
whose per-person cells do not add up to its total column is a calculation bug
as far as anyone reading it is concerned.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src import rich
from src.db.queries import Member
from src.debt_engine import Transfer, reduce_debts
from src.money import format_amount, split_equal
from src.render import balances_rich, history_rich

ALI, BITA, CYRUS = 1, 2, 3


def member(uid, name):
    return Member(user_id=uid, group_id=-100, tg_user_id=None, display_name=name, is_active=True)


MEMBERS = [member(ALI, "Ali"), member(BITA, "Bita"), member(CYRUS, "Cyrus")]


def expense(eid, payer, amount, description="Dinner", voided=False):
    return {
        "kind": "expense", "id": eid, "created_at": "2026-08-30T18:16:12.345Z",
        "voided_at": "2026-08-31T00:00:00Z" if voided else None,
        "amount_minor": amount, "currency_code": "IRT", "description": description,
        "payer_id": payer, "payee_id": None,
    }


def settlement(sid, payer, payee, amount):
    return {
        "kind": "settlement", "id": sid, "created_at": "2026-08-30T19:00:00Z",
        "voided_at": None, "amount_minor": amount, "currency_code": "IRT",
        "description": None, "payer_id": payer, "payee_id": payee,
    }


def the_table(msg):
    tables = [b for b in msg["blocks"] if b["type"] == "table"]
    assert tables, "no table block in the message"
    return tables[0]


def texts(row):
    return [c["text"] for c in row]


def number(s: str) -> int:
    return int(s.replace(",", ""))


class TestSchema:
    """Field names and required fields from core.telegram.org/bots/api."""

    def test_every_cell_has_align_and_valign(self):
        # Required in RichBlockTableCell, unlike every other cell field.
        t = rich.table(["a", "b"], [["1", "2"], ["3", "4"]], "cap")
        for row in t["cells"]:
            for c in row:
                assert c["align"] in {"left", "center", "right"}
                assert c["valign"] in {"top", "middle", "bottom"}

    def test_only_the_first_row_is_a_header(self):
        t = rich.table(["a", "b"], [["1", "2"]])
        assert all(c.get("is_header") for c in t["cells"][0])
        assert not any(c.get("is_header") for c in t["cells"][1])

    def test_table_block_type_and_caption(self):
        t = rich.table(["a"], [["1"]], "Balances")
        assert t["type"] == "table"
        assert t["caption"] == "Balances"

    def test_message_uses_blocks_not_text(self):
        # Exactly one of html, markdown or blocks may be set.
        m = rich.message([rich.paragraph("hi")], "en")
        assert set(m) == {"blocks", "is_rtl"}

    def test_persian_is_right_to_left(self):
        assert rich.message([], "fa")["is_rtl"] is True
        assert rich.message([], "en")["is_rtl"] is False

    def test_struck_text_shape(self):
        assert rich.struck("x") == {"type": "strikethrough", "text": "x"}


class TestLimits:
    def test_twenty_columns_fits(self):
        assert rich.fits(rich.message([rich.table(["h"] * 20, [["c"] * 20])], "en"))

    def test_twenty_one_columns_does_not(self):
        assert not rich.fits(rich.message([rich.table(["h"] * 21, [["c"] * 21])], "en"))

    def test_too_many_rows_does_not(self):
        assert not rich.fits(rich.message([rich.table(["h"], [["c"]] * 600)], "en"))

    def test_html_message_always_fits(self):
        assert rich.fits(rich.html_message("<b>x</b>", "en"))


class TestBareAmounts:
    def test_no_unit(self):
        assert format_amount(300_000, "IRT", "fa", unit=False) == "300,000"
        assert format_amount(-123_456, "USD", "en", unit=False) == "-1,234.56"

    def test_unit_is_still_the_default(self):
        assert format_amount(300_000, "IRT", "en") != "300,000"


class TestHistoryTable:
    def render(self, entries, splits, lang="en"):
        return history_rich(entries, MEMBERS, lang, 1, 1, splits, "IRT")

    def test_one_column_per_person_charged(self):
        shares = split_equal(300_000, [ALI, BITA, CYRUS], ALI)
        t = the_table(self.render([expense(1, ALI, 300_000)], {1: shares}))
        header = texts(t["cells"][0])
        assert header[-3:] == ["Ali", "Bita", "Cyrus"]

    def test_people_not_charged_on_this_page_get_no_column(self):
        shares = split_equal(100_000, [ALI, BITA], ALI)
        t = the_table(self.render([expense(1, ALI, 100_000)], {1: shares}))
        assert "Cyrus" not in texts(t["cells"][0])

    def test_someone_not_in_a_split_gets_a_dash(self):
        two = split_equal(100_000, [ALI, BITA], ALI)
        three = split_equal(90_000, [ALI, BITA, CYRUS], BITA)
        t = the_table(self.render(
            [expense(2, BITA, 90_000), expense(1, ALI, 100_000)], {1: two, 2: three}
        ))
        row_for_e1 = texts(t["cells"][2])
        assert row_for_e1[-1] == "—"  # Cyrus was not part of E1

    def test_remainder_is_visible_in_the_cells(self):
        # 100 across three: the payer absorbs the odd unit, and the table must
        # show 34, not round it away.
        shares = split_equal(100, [ALI, BITA, CYRUS], ALI)
        t = the_table(self.render([expense(1, ALI, 100)], {1: shares}))
        assert texts(t["cells"][1])[-3:] == ["34", "33", "33"]

    def test_deleted_row_is_struck_through_in_every_cell(self):
        shares = split_equal(300_000, [ALI, BITA, CYRUS], ALI)
        t = the_table(self.render([expense(1, ALI, 300_000, voided=True)], {1: shares}))
        row = texts(t["cells"][1])
        assert all(c["type"] == "strikethrough" for c in row)
        assert "deleted" in row[2]["text"]

    def test_settlement_row_charges_nobody(self):
        shares = split_equal(300_000, [ALI, BITA, CYRUS], ALI)
        t = the_table(self.render(
            [settlement(1, BITA, ALI, 100_000), expense(1, ALI, 300_000)], {1: shares}
        ))
        row = texts(t["cells"][1])
        assert row[0] == "S1"
        assert row[2] == "Bita → Ali"
        assert row[-3:] == ["—", "—", "—"]

    def test_names_are_not_html_escaped(self):
        # Cells are never parsed, so escaping would show a literal "&amp;".
        members = MEMBERS + [member(4, "Tom & Jerry")]
        shares = split_equal(200, [ALI, 4], ALI)
        t = history_rich([expense(1, ALI, 200, "<b>snacks</b>")], members, "en", 1, 1,
                         {1: shares}, "IRT")
        flat = str(t)
        assert "Tom & Jerry" in flat and "&amp;" not in flat
        assert "<b>snacks</b>" in flat

    def test_caption_names_the_page_and_the_currency(self):
        shares = split_equal(300, [ALI, BITA], ALI)
        cap = the_table(history_rich([expense(1, ALI, 300)], MEMBERS, "en", 2, 5,
                                     {1: shares}, "IRT"))["caption"]
        assert "2" in cap and "5" in cap and "Toman" in cap

    def test_persian_page_is_rtl_and_uses_persian_headers(self):
        shares = split_equal(300, [ALI, BITA], ALI)
        msg = self.render([expense(1, ALI, 300)], {1: shares}, lang="fa")
        assert msg["is_rtl"] is True
        assert "پرداخت‌کننده" in texts(the_table(msg)["cells"][0])

    @settings(max_examples=300, deadline=None)
    @given(
        amount=st.integers(min_value=1, max_value=10**12),
        people=st.lists(st.sampled_from([ALI, BITA, CYRUS]), min_size=1, max_size=3, unique=True),
        payer=st.sampled_from([ALI, BITA, CYRUS]),
    )
    def test_cells_always_add_up_to_the_total(self, amount, people, payer):
        shares = split_equal(amount, people, payer)
        t = the_table(self.render([expense(1, payer, amount)], {1: shares}))
        row = texts(t["cells"][1])
        cells = [number(c) for c in row[5:] if c != "—"]
        assert sum(cells) == number(row[4]) == amount


class TestBalancesTables:
    def test_all_settled_is_a_sentence_not_a_table(self):
        msg = balances_rich({ALI: 0, BITA: 0}, [], MEMBERS, "IRT", "en")
        assert [b["type"] for b in msg["blocks"]] == ["paragraph"]

    def test_two_tables_and_a_note_when_money_is_owed(self):
        balances = {ALI: 200, BITA: -100, CYRUS: -100}
        msg = balances_rich(balances, reduce_debts(balances), MEMBERS, "IRT", "en")
        assert [b["type"] for b in msg["blocks"]] == ["table", "table", "paragraph"]

    def test_creditor_first_and_wording_matches_the_sign(self):
        balances = {ALI: 200, BITA: -100, CYRUS: -100}
        t = the_table(balances_rich(balances, [], MEMBERS, "IRT", "en"))
        assert texts(t["cells"][1]) == ["Ali", "is owed 200"]
        assert texts(t["cells"][2])[1] == "owes 100"

    def test_plan_rows_match_the_transfers(self):
        plan = [Transfer(from_user=BITA, to_user=ALI, amount_minor=1_500)]
        msg = balances_rich({ALI: 1_500, BITA: -1_500}, plan, MEMBERS, "IRT", "en")
        plan_table = [b for b in msg["blocks"] if b["type"] == "table"][1]
        assert texts(plan_table["cells"][1]) == ["Bita", "Ali", "1,500"]

    @settings(max_examples=200, deadline=None)
    @given(st.lists(st.integers(min_value=-10**9, max_value=10**9), min_size=2, max_size=3))
    def test_displayed_balances_sum_to_zero(self, values):
        # Make the ledger balance, as net_balances guarantees, then check the
        # signed figures read back out of the table still sum to exactly zero.
        values = values[:-1] + [-sum(values[:-1])]
        assume(any(values))  # all-zero is the "everyone is square" sentence
        balances = dict(zip([ALI, BITA, CYRUS], values))
        t = the_table(balances_rich(balances, [], MEMBERS, "IRT", "en"))
        total = 0
        for _, status in (texts(r) for r in t["cells"][1:]):
            if status.startswith("is owed "):
                total += number(status.removeprefix("is owed "))
            elif status.startswith("owes "):
                total -= number(status.removeprefix("owes "))
        assert total == 0
