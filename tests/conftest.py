"""Shared fixtures. Every DB test runs against a real SQLite file on disk, not
an in-memory shim, so PRAGMAs and constraints behave exactly as in production.
"""

from __future__ import annotations

import uuid

import pytest_asyncio

from src.db import queries
from src.db.connection import Database

GROUP_ID = -1001234567890


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "ledger.db")
    await database.connect()
    try:
        yield database
    finally:
        await database.close()


@pytest_asyncio.fixture
async def group(db):
    await queries.upsert_group(db, GROUP_ID, "Test Group")
    await queries.set_group_active(db, GROUP_ID, True)
    return GROUP_ID


@pytest_asyncio.fixture
async def members(db, group):
    """Three members: Ali, Bita, Cyrus. Returns their user ids in that order."""
    return [
        await queries.add_member(db, group, "Ali", tg_user_id=101),
        await queries.add_member(db, group, "Bita", tg_user_id=102),
        await queries.add_member(db, group, "Cyrus", tg_user_id=None),  # a ghost member
    ]


def key() -> str:
    """A fresh idempotency key, standing in for one confirmation flow."""
    return uuid.uuid4().hex
