"""Hashemwise - net balances.

This module owns the sign convention, and it is the one place where getting a
sign backwards would corrupt every number the bot displays. It is written out
in full rather than folded into a clever query, because it has to be auditable
by eye.

For a user `u`, over rows where `voided_at IS NULL`:

    paid     = expenses they paid for
    owed     = their shares of expenses (their own included)
    sent     = settlements where they handed money over
    received = settlements where they took money in

    net(u) = paid - owed + sent - received

**A positive net means the group owes `u`. A negative net means `u` owes the
group.**

Why `sent` is a *credit*: handing someone cash discharges a debt, so it moves
you toward being owed. Worked through: you pay 300 for a meal split three ways.
paid=300, owed=100, net=+200, the group owes you 200. Your friends hand you
200; received=200, net=0. Settled.

**Invariant: the nets of a group sum to exactly zero.** Every expense adds
`+amount` to one payer and subtracts shares that `money.split_equal` /
`money.validate_custom_split` guarantee sum to `amount`; every settlement adds
and subtracts the same figure. If the sum is ever non-zero the data is corrupt,
and `net_balances` raises rather than returning numbers that look reasonable
and are wrong.
"""

from __future__ import annotations

import logging

from src.db import queries
from src.db.connection import Database
from src.debt_engine import LedgerImbalance, Transfer, reduce_debts

log = logging.getLogger(__name__)


async def net_balances(db: Database, group_id: int) -> dict[int, int]:
    """Net balance in minor units for every member of the group.

    Inactive members are included: deactivating someone does not erase what
    they owe, and omitting them would break the sum-to-zero invariant.
    """
    members = await queries.list_members(db, group_id, include_inactive=True)

    paid = await queries.sum_paid_by_user(db, group_id)
    owed = await queries.sum_owed_by_user(db, group_id)
    sent = await queries.sum_settlements_sent(db, group_id)
    received = await queries.sum_settlements_received(db, group_id)

    balances = {
        m.user_id: paid.get(m.user_id, 0)
        - owed.get(m.user_id, 0)
        + sent.get(m.user_id, 0)
        - received.get(m.user_id, 0)
        for m in members
    }

    residual = sum(balances.values())
    if residual != 0:
        # Unreachable with a consistent ledger. Refuse rather than mislead.
        log.error(
            "ledger imbalance in group %s: residual=%s paid=%s owed=%s sent=%s received=%s",
            group_id,
            residual,
            paid,
            owed,
            sent,
            received,
        )
        raise LedgerImbalance(residual)

    return balances


async def settlement_plan(db: Database, group_id: int) -> list[Transfer]:
    """The suggested payments that would zero the group out."""
    return reduce_debts(await net_balances(db, group_id))
