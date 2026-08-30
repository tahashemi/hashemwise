-- Hashemwise ledger schema.
--
-- Money is always an INTEGER count of minor units (see src/money.py). There is
-- no REAL column anywhere in this file, deliberately.
--
-- Nothing is ever hard-deleted. Corrections void a row and insert a replacement
-- that points back via `supersedes_id`, so history stays truthful and every
-- balance query is a plain `WHERE voided_at IS NULL`.

CREATE TABLE IF NOT EXISTS groups (
    group_id      INTEGER PRIMARY KEY,          -- Telegram chat id (negative for groups)
    title         TEXT    NOT NULL,
    -- Default 0: a group the bot is added to starts unauthorized and must be
    -- explicitly approved by the super admin.
    is_active     INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    currency_code TEXT    NOT NULL DEFAULT 'IRT',
    lang          TEXT    NOT NULL DEFAULT 'en' CHECK (lang IN ('en', 'fa')),
    is_setup      INTEGER NOT NULL DEFAULT 0 CHECK (is_setup IN (0, 1)),
    added_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id     INTEGER NOT NULL REFERENCES groups (group_id) ON DELETE CASCADE,
    tg_user_id   INTEGER,                       -- NULL for a "ghost" member with no Telegram account
    display_name TEXT    NOT NULL,
    -- Members are deactivated, never deleted, so historical splits keep a name.
    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    added_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (group_id, display_name)
);

-- One Telegram account maps to at most one member per group.
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_group_tg
    ON users (group_id, tg_user_id) WHERE tg_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_group ON users (group_id);

CREATE TABLE IF NOT EXISTS expenses (
    expense_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id      INTEGER NOT NULL REFERENCES groups (group_id) ON DELETE CASCADE,
    payer_id      INTEGER NOT NULL REFERENCES users (user_id),
    amount_minor  INTEGER NOT NULL CHECK (amount_minor > 0),
    -- Snapshot of the group's currency at entry time, so a later currency
    -- change can never silently reinterpret the scale of an old amount.
    currency_code TEXT    NOT NULL,
    description   TEXT    NOT NULL,
    created_by_tg INTEGER NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    voided_at     TEXT,
    voided_by_tg  INTEGER,
    supersedes_id INTEGER REFERENCES expenses (expense_id),
    -- Unique per confirmation flow: a double-tapped "Confirm" button collides
    -- here instead of creating a second expense.
    idem_key      TEXT    NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_expenses_group_live
    ON expenses (group_id) WHERE voided_at IS NULL;

CREATE TABLE IF NOT EXISTS expense_splits (
    expense_id INTEGER NOT NULL REFERENCES expenses (expense_id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users (user_id),
    -- Zero is legal: a participant can be listed but owe nothing.
    owed_minor INTEGER NOT NULL CHECK (owed_minor >= 0),
    -- Composite PK: one row per person per expense, so a retried write cannot
    -- double-count a share.
    PRIMARY KEY (expense_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_splits_user ON expense_splits (user_id);

CREATE TABLE IF NOT EXISTS settlements (
    settlement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id      INTEGER NOT NULL REFERENCES groups (group_id) ON DELETE CASCADE,
    payer_id      INTEGER NOT NULL REFERENCES users (user_id),   -- sent the money
    payee_id      INTEGER NOT NULL REFERENCES users (user_id),   -- received the money
    amount_minor  INTEGER NOT NULL CHECK (amount_minor > 0),
    currency_code TEXT    NOT NULL,
    created_by_tg INTEGER NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    voided_at     TEXT,
    voided_by_tg  INTEGER,
    supersedes_id INTEGER REFERENCES settlements (settlement_id),
    idem_key      TEXT    NOT NULL UNIQUE,
    CHECK (payer_id <> payee_id)
);

CREATE INDEX IF NOT EXISTS idx_settlements_group_live
    ON settlements (group_id) WHERE voided_at IS NULL;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
