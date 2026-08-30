"""Net balances against a real database.

These are the tests that would catch a sign error, a double-count, or a void
that fails to reverse cleanly - the three ways a shared-expense ledger goes
quietly wrong.
"""

from __future__ import annotations

import pytest

from src.db import queries
from src.debt_engine import LedgerImbalance, apply_transfers
from src.ledger import net_balances, settlement_plan
from src.money import split_equal
from tests.conftest import key


async def add_expense(db, group, *, payer, total, participants=None, shares=None, desc="dinner"):
    participants = participants or []
    shares = shares if shares is not None else split_equal(total, participants, payer)
    return await queries.create_expense(
        db,
        group_id=group,
        payer_id=payer,
        amount_minor=total,
        currency_code="IRT",
        description=desc,
        created_by_tg=101,
        shares=shares,
        idem_key=key(),
    )


async def settle(db, group, *, payer, payee, amount):
    return await queries.create_settlement(
        db,
        group_id=group,
        payer_id=payer,
        payee_id=payee,
        amount_minor=amount,
        currency_code="IRT",
        created_by_tg=101,
        idem_key=key(),
    )


class TestSignConvention:
    async def test_fresh_group_is_all_zero(self, db, group, members):
        assert await net_balances(db, group) == {m: 0 for m in members}

    async def test_payer_is_owed_the_others_shares(self, db, group, members):
        ali, bita, cyrus = members
        await add_expense(db, group, payer=ali, total=300, participants=members)
        balances = await net_balances(db, group)
        # Ali fronted 300 and consumed 100, so the group owes him 200.
        assert balances == {ali: 200, bita: -100, cyrus: -100}

    async def test_paying_for_something_you_did_not_consume(self, db, group, members):
        ali, bita, cyrus = members
        await add_expense(db, group, payer=ali, total=200, participants=[bita, cyrus])
        assert await net_balances(db, group) == {ali: 200, bita: -100, cyrus: -100}

    async def test_paying_only_for_yourself_nets_to_zero(self, db, group, members):
        ali, _, _ = members
        await add_expense(db, group, payer=ali, total=500, participants=[ali])
        assert (await net_balances(db, group))[ali] == 0

    async def test_sending_a_settlement_credits_the_sender(self, db, group, members):
        ali, bita, _ = members
        await settle(db, group, payer=bita, payee=ali, amount=100)
        balances = await net_balances(db, group)
        assert balances[bita] == 100  # Bita handed over cash, so is now owed it
        assert balances[ali] == -100


class TestSettlingToZero:
    async def test_paying_your_share_back_clears_you(self, db, group, members):
        ali, bita, cyrus = members
        await add_expense(db, group, payer=ali, total=300, participants=members)
        await settle(db, group, payer=bita, payee=ali, amount=100)
        await settle(db, group, payer=cyrus, payee=ali, amount=100)
        assert await net_balances(db, group) == {ali: 0, bita: 0, cyrus: 0}

    async def test_following_the_suggested_plan_zeroes_the_group(self, db, group, members):
        ali, bita, cyrus = members
        await add_expense(db, group, payer=ali, total=300, participants=members)
        await add_expense(db, group, payer=bita, total=90, participants=members)
        await add_expense(db, group, payer=cyrus, total=61, participants=[ali, cyrus])

        balances = await net_balances(db, group)
        plan = await settlement_plan(db, group)
        assert apply_transfers(balances, plan) == {m: 0 for m in members}

        for t in plan:
            await settle(db, group, payer=t.from_user, payee=t.to_user, amount=t.amount_minor)
        assert await net_balances(db, group) == {m: 0 for m in members}

    async def test_overpayment_flips_the_balance_rather_than_vanishing(self, db, group, members):
        ali, bita, _ = members
        await add_expense(db, group, payer=ali, total=200, participants=[ali, bita])
        # Bita owes 100 but sends 150.
        await settle(db, group, payer=bita, payee=ali, amount=150)
        balances = await net_balances(db, group)
        assert balances[bita] == 50 and balances[ali] == -50


class TestVoiding:
    async def test_voiding_an_expense_reverts_balances_exactly(self, db, group, members):
        before = await net_balances(db, group)
        eid = await add_expense(db, group, payer=members[0], total=1234567, participants=members)
        assert await net_balances(db, group) != before
        await queries.void_expense(db, eid, 101)
        assert await net_balances(db, group) == before

    async def test_voiding_a_settlement_reverts_balances_exactly(self, db, group, members):
        ali, bita, _ = members
        await add_expense(db, group, payer=ali, total=300, participants=members)
        before = await net_balances(db, group)
        sid = await settle(db, group, payer=bita, payee=ali, amount=100)
        await queries.void_settlement(db, sid, 101)
        assert await net_balances(db, group) == before

    async def test_voiding_one_of_many_leaves_the_rest_intact(self, db, group, members):
        ali, bita, cyrus = members
        keep = await add_expense(db, group, payer=ali, total=300, participants=members)
        drop = await add_expense(db, group, payer=bita, total=600, participants=members)
        await queries.void_expense(db, drop, 101)
        assert await net_balances(db, group) == {ali: 200, bita: -100, cyrus: -100}
        assert (await queries.get_expense(db, keep))["voided_at"] is None


class TestEditing:
    async def test_edit_replaces_rather_than_double_counting(self, db, group, members):
        """An edit is void-plus-insert. The old figure must leave no trace."""
        ali, bita, cyrus = members
        original = await add_expense(db, group, payer=ali, total=300, participants=members)

        await queries.void_expense(db, original, 101)
        corrected = await queries.create_expense(
            db,
            group_id=group,
            payer_id=ali,
            amount_minor=600,  # it was actually 600, not 300
            currency_code="IRT",
            description="dinner (corrected)",
            created_by_tg=101,
            shares=split_equal(600, members, ali),
            idem_key=key(),
            supersedes_id=original,
        )

        # 600 paid by Ali, 200 each: not 900, and not 300.
        assert await net_balances(db, group) == {ali: 400, bita: -200, cyrus: -200}
        assert (await queries.get_expense(db, corrected))["supersedes_id"] == original

    async def test_the_edit_chain_is_walkable(self, db, group, members):
        first = await add_expense(db, group, payer=members[0], total=300, participants=members)
        await queries.void_expense(db, first, 101)
        second = await queries.create_expense(
            db, group_id=group, payer_id=members[0], amount_minor=400, currency_code="IRT",
            description="v2", created_by_tg=101,
            shares=split_equal(400, members, members[0]), idem_key=key(), supersedes_id=first,
        )
        assert (await queries.get_expense(db, second))["supersedes_id"] == first


class TestRemaindersDoNotLeak:
    @pytest.mark.parametrize("total", [1, 2, 100, 101, 1000, 999_999_999, 10**12 + 1])
    async def test_indivisible_totals_still_net_to_zero(self, db, group, members, total):
        await add_expense(db, group, payer=members[0], total=total, participants=members)
        assert sum((await net_balances(db, group)).values()) == 0

    async def test_many_awkward_expenses_never_drift(self, db, group, members):
        # 200 expenses that each leave a remainder. Under floats this is where
        # the cents quietly disappear.
        for i in range(200):
            await add_expense(
                db, group, payer=members[i % 3], total=100 + i, participants=members
            )
        balances = await net_balances(db, group)
        assert sum(balances.values()) == 0
        assert apply_transfers(balances, await settlement_plan(db, group)) == {
            m: 0 for m in members
        }


class TestInactiveMembers:
    async def test_a_deactivated_member_still_counts(self, db, group, members):
        """Deactivating someone must not erase their debt or break the sum."""
        ali, bita, cyrus = members
        await add_expense(db, group, payer=ali, total=300, participants=members)
        await queries.set_member_active(db, bita, False)
        balances = await net_balances(db, group)
        assert balances[bita] == -100
        assert sum(balances.values()) == 0


class TestImbalanceDetection:
    async def test_corrupted_splits_are_refused_not_displayed(self, db, group, members):
        """Simulate corruption and confirm the bot refuses to show numbers."""
        eid = await add_expense(db, group, payer=members[0], total=300, participants=members)
        # Reach past the query layer to break the invariant on purpose.
        await db.execute(
            "UPDATE expense_splits SET owed_minor = 50 WHERE expense_id = ? AND user_id = ?",
            (eid, members[1]),
        )
        with pytest.raises(LedgerImbalance):
            await net_balances(db, group)


class TestIsolationBetweenGroups:
    async def test_one_groups_expenses_do_not_affect_another(self, db, group, members):
        await queries.upsert_group(db, -555, "Other")
        other = [
            await queries.add_member(db, -555, "Dara"),
            await queries.add_member(db, -555, "Elham"),
        ]
        await add_expense(db, group, payer=members[0], total=300, participants=members)
        await add_expense(db, -555, payer=other[0], total=1000, participants=other)

        assert await net_balances(db, group) == {
            members[0]: 200, members[1]: -100, members[2]: -100
        }
        assert await net_balances(db, -555) == {other[0]: 500, other[1]: -500}


class TestGoldenScenario:
    async def test_a_weekend_trip_computed_by_hand(self, db, group, members):
        """A worked example whose every figure was calculated on paper first."""
        ali, bita, cyrus = members

        # 1. Ali pays 150,000 T for petrol, split three ways -> 50,000 each.
        await add_expense(db, group, payer=ali, total=150_000, participants=members, desc="petrol")
        # 2. Bita pays 90,000 T for groceries, split three ways -> 30,000 each.
        await add_expense(db, group, payer=bita, total=90_000, participants=members, desc="food")
        # 3. Cyrus pays 40,000 T for a taxi that only he and Ali took -> 20,000 each.
        await add_expense(db, group, payer=cyrus, total=40_000, participants=[ali, cyrus],
                          desc="taxi")

        # By hand:
        #   Ali:   paid 150,000, owes 50,000 + 30,000 + 20,000 = 100,000 -> +50,000
        #   Bita:  paid  90,000, owes 50,000 + 30,000          =  80,000 -> +10,000
        #   Cyrus: paid  40,000, owes 50,000 + 30,000 + 20,000 = 100,000 -> -60,000
        assert await net_balances(db, group) == {ali: 50_000, bita: 10_000, cyrus: -60_000}

        # Cyrus is the only debtor, so the plan is two payments out of him,
        # largest creditor first.
        plan = await settlement_plan(db, group)
        assert [(t.from_user, t.to_user, t.amount_minor) for t in plan] == [
            (cyrus, ali, 50_000),
            (cyrus, bita, 10_000),
        ]

        for t in plan:
            await settle(db, group, payer=t.from_user, payee=t.to_user, amount=t.amount_minor)
        assert await net_balances(db, group) == {ali: 0, bita: 0, cyrus: 0}
