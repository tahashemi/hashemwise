"""Hashemwise - collapsing net balances into a short list of payments.

Pure and integer-only: no Telegram, no database, no float. Give it a mapping of
user id to net balance in minor units and it returns the transfers that settle
the group.

On terminology: this is the standard greedy two-pointer reduction. It always
produces at most `n-1` transfers, which is a large improvement over the `n*(n-1)/2`
pairwise debts it replaces. It is *not* provably the fewest possible - minimum
cash flow is NP-hard in general - so the bot says "suggested payments" rather
than claiming optimality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, order=True)
class Transfer:
    """`from_user` pays `amount_minor` to `to_user`."""

    from_user: int
    to_user: int
    amount_minor: int


class LedgerImbalance(ValueError):
    """Net balances did not sum to zero.

    This is unreachable with a consistent ledger: every expense adds `+amount`
    to its payer and subtracts shares that provably sum to `amount`, and every
    settlement adds and subtracts the same figure. If it fires, the data is
    corrupt, and the bot refuses to display anything rather than showing
    plausible-looking wrong numbers.
    """

    key = "err_ledger_imbalance"

    def __init__(self, residual: int) -> None:
        self.residual = residual
        super().__init__(f"net balances sum to {residual}, expected 0")


def reduce_debts(balances: Mapping[int, int]) -> list[Transfer]:
    """Return the transfers that bring every balance to zero.

    Convention (matching `ledger.py`): a positive balance means the group owes
    that user, a negative balance means that user owes the group.

    Both sides are sorted by `(-magnitude, user_id)`. The magnitude ordering is
    what keeps the transfer count low; the `user_id` tie-break is what makes the
    output stable, so `/balances` prints the same plan every time it is called
    on unchanged data instead of appearing to flicker.
    """
    for uid, amount in balances.items():
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise TypeError(f"balance for user {uid} is {type(amount).__name__}, expected int")

    residual = sum(balances.values())
    if residual != 0:
        raise LedgerImbalance(residual)

    debtors = sorted(
        ((uid, -amount) for uid, amount in balances.items() if amount < 0),
        key=lambda pair: (-pair[1], pair[0]),
    )
    creditors = sorted(
        ((uid, amount) for uid, amount in balances.items() if amount > 0),
        key=lambda pair: (-pair[1], pair[0]),
    )

    transfers: list[Transfer] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor, owed = debtors[i]
        creditor, due = creditors[j]

        amount = min(owed, due)
        transfers.append(Transfer(from_user=debtor, to_user=creditor, amount_minor=amount))

        owed -= amount
        due -= amount
        debtors[i] = (debtor, owed)
        creditors[j] = (creditor, due)

        # At least one side is now zero, which is what bounds the result at
        # n-1 transfers. When both are, we retire two members with one payment.
        if owed == 0:
            i += 1
        if due == 0:
            j += 1

    _check_postconditions(balances, transfers)
    return transfers


def apply_transfers(balances: Mapping[int, int], transfers: list[Transfer]) -> dict[int, int]:
    """Replay transfers against balances. Used to verify a settlement plan.

    Paying reduces what you are owed and moves a debt toward zero, so the payer
    gains and the payee loses under our sign convention.
    """
    result = dict(balances)
    for t in transfers:
        result[t.from_user] = result.get(t.from_user, 0) + t.amount_minor
        result[t.to_user] = result.get(t.to_user, 0) - t.amount_minor
    return result


def _check_postconditions(balances: Mapping[int, int], transfers: list[Transfer]) -> None:
    """Assert the plan is actually valid before anyone acts on it."""
    assert all(t.amount_minor > 0 for t in transfers), "non-positive transfer"
    assert all(t.from_user != t.to_user for t in transfers), "self-payment"

    active = sum(1 for v in balances.values() if v != 0)
    assert len(transfers) <= max(active - 1, 0), "more transfers than n-1"

    settled = apply_transfers(balances, transfers)
    assert all(v == 0 for v in settled.values()), "plan does not settle the group"
