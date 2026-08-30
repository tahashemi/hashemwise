"""Debt reduction: turn net balances into a short list of who-pays-whom.

The property tests here are the real safety net. Hand-written examples check
the cases we thought of; Hypothesis checks the ones we did not.
"""

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.debt_engine import (
    LedgerImbalance,
    Transfer,
    apply_transfers,
    reduce_debts,
)


def balanced_ledger(draw_ids, draw_amounts):
    """Build a dict whose values sum to exactly zero."""
    ledger = dict(zip(draw_ids, draw_amounts))
    if not ledger:
        return {}
    # Force the sum to zero by absorbing the residual into the last member.
    last = list(ledger)[-1]
    ledger[last] -= sum(ledger.values())
    return ledger


# Ledgers with 2..12 distinct members whose balances sum to zero.
ledgers = st.builds(
    balanced_ledger,
    st.lists(st.integers(1, 500), min_size=2, max_size=12, unique=True),
    st.lists(st.integers(-10**9, 10**9), min_size=2, max_size=12),
).filter(lambda d: len(d) >= 2)


class TestBasicCases:
    def test_everyone_settled_needs_no_transfers(self):
        assert reduce_debts({1: 0, 2: 0, 3: 0}) == []

    def test_empty_ledger(self):
        assert reduce_debts({}) == []

    def test_simple_two_person_debt(self):
        # 2 owes 50, 1 is owed 50.
        assert reduce_debts({1: 50, 2: -50}) == [Transfer(from_user=2, to_user=1, amount_minor=50)]

    def test_one_creditor_two_debtors(self):
        transfers = reduce_debts({1: 100, 2: -60, 3: -40})
        assert sorted((t.from_user, t.amount_minor) for t in transfers) == [(2, 60), (3, 40)]
        assert all(t.to_user == 1 for t in transfers)

    def test_chain_collapses_rather_than_hopping(self):
        # 1 owes 2, 2 owes 3 the same amount. The minimal answer is a single
        # transfer 1 -> 3, not two hops through 2.
        transfers = reduce_debts({1: -50, 2: 0, 3: 50})
        assert transfers == [Transfer(from_user=1, to_user=3, amount_minor=50)]

    def test_zero_balance_members_are_never_involved(self):
        transfers = reduce_debts({1: 100, 2: -100, 3: 0, 4: 0})
        assert all(3 not in (t.from_user, t.to_user) for t in transfers)
        assert all(4 not in (t.from_user, t.to_user) for t in transfers)


class TestImbalanceIsRefused:
    def test_non_zero_sum_raises(self):
        # This can only happen if the ledger is corrupt. Showing plausible but
        # wrong numbers would be worse than refusing.
        with pytest.raises(LedgerImbalance):
            reduce_debts({1: 100, 2: -90})

    def test_error_reports_the_residual(self):
        with pytest.raises(LedgerImbalance) as e:
            reduce_debts({1: 100, 2: -90})
        assert e.value.residual == 10

    def test_non_integer_balance_rejected(self):
        with pytest.raises(TypeError):
            reduce_debts({1: 100.0, 2: -100.0})  # type: ignore[dict-item]


class TestDeterminism:
    def test_input_order_does_not_change_output(self):
        ledger = {5: 300, 1: -100, 9: -50, 3: -150, 7: 0}
        expected = reduce_debts(ledger)
        for _ in range(20):
            items = list(ledger.items())
            random.shuffle(items)
            assert reduce_debts(dict(items)) == expected

    def test_ties_are_broken_by_user_id(self):
        # Two debtors owe exactly the same; the lower id must be listed first
        # so /balances prints the same plan every time it is called.
        transfers = reduce_debts({1: -50, 2: -50, 3: 100})
        assert [t.from_user for t in transfers] == [1, 2]

    def test_repeated_calls_are_identical(self):
        ledger = {1: -33, 2: -33, 3: -34, 4: 100}
        assert reduce_debts(ledger) == reduce_debts(ledger)


class TestProperties:
    @given(ledgers)
    @settings(max_examples=400, deadline=None)
    def test_transfers_settle_everyone_exactly(self, ledger):
        transfers = reduce_debts(ledger)
        assert apply_transfers(ledger, transfers) == {u: 0 for u in ledger}

    @given(ledgers)
    @settings(max_examples=400, deadline=None)
    def test_every_amount_is_strictly_positive(self, ledger):
        assert all(t.amount_minor > 0 for t in reduce_debts(ledger))

    @given(ledgers)
    @settings(max_examples=400, deadline=None)
    def test_at_most_n_minus_one_transfers(self, ledger):
        active = sum(1 for v in ledger.values() if v != 0)
        transfers = reduce_debts(ledger)
        assert len(transfers) <= max(active - 1, 0)

    @given(ledgers)
    @settings(max_examples=400, deadline=None)
    def test_nobody_pays_themselves(self, ledger):
        assert all(t.from_user != t.to_user for t in reduce_debts(ledger))

    @given(ledgers)
    @settings(max_examples=400, deadline=None)
    def test_money_is_conserved(self, ledger):
        # Total moved out of debtors equals total moved into creditors.
        transfers = reduce_debts(ledger)
        assert sum(t.amount_minor for t in transfers) == sum(v for v in ledger.values() if v > 0)

    @given(ledgers)
    @settings(max_examples=400, deadline=None)
    def test_debtors_only_pay_and_creditors_only_receive(self, ledger):
        for t in reduce_debts(ledger):
            assert ledger[t.from_user] < 0
            assert ledger[t.to_user] > 0

    @given(ledgers)
    @settings(max_examples=200, deadline=None)
    def test_shuffled_input_gives_identical_output(self, ledger):
        items = list(ledger.items())
        random.shuffle(items)
        assert reduce_debts(dict(items)) == reduce_debts(ledger)


class TestApplyTransfers:
    def test_helper_moves_balance_in_the_right_direction(self):
        # A debtor (negative) paying moves toward zero from below.
        result = apply_transfers({1: -50, 2: 50}, [Transfer(1, 2, 50)])
        assert result == {1: 0, 2: 0}
