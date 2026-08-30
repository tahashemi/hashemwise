"""Hashemwise - SQLite connection management.

Two things here are load-bearing and easy to get wrong:

**`PRAGMA foreign_keys = ON`.** SQLite ignores foreign keys unless this is set,
*per connection*. Without it every `REFERENCES` and `ON DELETE CASCADE` in
schema.sql is decorative and orphan rows accumulate silently.

**A single connection behind an `asyncio.Lock`.** aiosqlite runs statements on
one background thread, but an `await` between two statements of a transaction
lets another coroutine's statement interleave into it - two people adding an
expense in the same group at the same moment is an ordinary occurrence for this
bot. Serializing every operation removes that whole class of bug. At this scale
the contention is irrelevant; the operations are microseconds of local disk.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

import aiosqlite

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = "1"


class Database:
    """A single serialized SQLite connection."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    # -- lifecycle ---------------------------------------------------------

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row

        # foreign_keys must be set outside a transaction to take effect.
        await self._conn.execute("PRAGMA foreign_keys = ON")
        # WAL lets a reader proceed while a writer holds the file.
        await self._conn.execute("PRAGMA journal_mode = WAL")
        # Wait rather than raising "database is locked" on contention.
        await self._conn.execute("PRAGMA busy_timeout = 5000")
        # Safe against process crashes under WAL; only an OS-level crash can
        # lose the last commits, which for a shared-expense ledger is fine.
        await self._conn.execute("PRAGMA synchronous = NORMAL")
        await self._conn.commit()

        await self._verify_pragmas()
        await self._init_schema()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() has not been called")
        return self._conn

    async def _verify_pragmas(self) -> None:
        """Confirm foreign keys are actually enforced.

        A typo or an unsupported build would otherwise leave referential
        integrity quietly switched off for the life of the process.
        """
        async with self.conn.execute("PRAGMA foreign_keys") as cur:
            row = await cur.fetchone()
        if not row or row[0] != 1:
            raise RuntimeError("PRAGMA foreign_keys is not enabled; refusing to run")

    async def _init_schema(self) -> None:
        await self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        await self.conn.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT (key) DO NOTHING",
            (SCHEMA_VERSION,),
        )
        await self.conn.commit()

        async with self.conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ) as cur:
            row = await cur.fetchone()
        found = row["value"] if row else None
        if found != SCHEMA_VERSION:
            raise RuntimeError(
                f"database schema version is {found!r}, this build expects {SCHEMA_VERSION!r}"
            )

    # -- queries -----------------------------------------------------------

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run a statement and commit. Returns `lastrowid`."""
        async with self._lock:
            cursor = await self.conn.execute(sql, params)
            await self.conn.commit()
            return cursor.lastrowid or 0

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        async with self._lock:
            async with self.conn.execute(sql, params) as cur:
                return await cur.fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        async with self._lock:
            async with self.conn.execute(sql, params) as cur:
                return list(await cur.fetchall())

    async def fetchvalue(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        row = await self.fetchone(sql, params)
        return default if row is None or row[0] is None else row[0]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["Transaction"]:
        """Run several statements atomically.

        `BEGIN IMMEDIATE` takes the write lock up front rather than upgrading
        mid-transaction, so a write can never fail partway through. Any
        exception rolls the whole thing back - which is how an expense whose
        splits do not sum correctly gets discarded instead of half-written.
        """
        async with self._lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield Transaction(self.conn)
            except BaseException:
                await self.conn.rollback()
                raise
            else:
                await self.conn.commit()


class Transaction:
    """Statement runner scoped to an open transaction.

    Holds no lock of its own - `Database.transaction()` already owns it - and
    never commits, so callers cannot accidentally end the transaction early.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        cursor = await self._conn.execute(sql, params)
        return cursor.lastrowid or 0

    async def executemany(self, sql: str, params: Iterable[Sequence[Any]]) -> None:
        await self._conn.executemany(sql, params)

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        async with self._conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        async with self._conn.execute(sql, params) as cur:
            return list(await cur.fetchall())
