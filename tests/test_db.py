"""Database layer: constraints, atomicity, idempotency, soft deletes."""

from __future__ import annotations

import sqlite3

import pytest

from src.db import queries
from src.db.queries import DuplicateMember, MemberInUse
from src.money import SplitMismatch
from tests.conftest import key


class TestPragmasAndSchema:
    async def test_foreign_keys_are_actually_on(self, db):
        row = await db.fetchone("PRAGMA foreign_keys")
        assert row[0] == 1

    async def test_wal_mode(self, db):
        row = await db.fetchone("PRAGMA journal_mode")
        assert row[0].lower() == "wal"

    async def test_schema_version_recorded(self, db):
        assert await db.fetchvalue("SELECT value FROM schema_meta WHERE key='schema_version'")

    async def test_no_real_columns_anywhere(self, db):
        """Money must never be stored as a float."""
        tables = await db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        for t in tables:
            for col in await db.fetchall(f"PRAGMA table_info({t['name']})"):
                assert col["type"].upper() not in {"REAL", "FLOAT", "DOUBLE"}, (
                    f"{t['name']}.{col['name']} is {col['type']}"
                )

    async def test_connect_is_idempotent_on_existing_file(self, tmp_path):
        from src.db.connection import Database

        path = tmp_path / "l.db"
        for _ in range(3):
            d = Database(path)
            await d.connect()
            await d.close()


class TestGroups:
    async def test_group_starts_unauthorized(self, db):
        await queries.upsert_group(db, -100, "G")
        assert (await queries.get_group(db, -100)).is_active is False

    async def test_reupsert_does_not_reset_authorization(self, db):
        await queries.upsert_group(db, -100, "G")
        await queries.set_group_active(db, -100, True)
        await queries.set_group_currency(db, -100, "USD")
        # The bot being removed and re-added must not silently deauthorize.
        await queries.upsert_group(db, -100, "G renamed")
        g = await queries.get_group(db, -100)
        assert g.is_active is True and g.currency_code == "USD" and g.title == "G renamed"

    async def test_unknown_group_is_none(self, db):
        assert await queries.get_group(db, -999) is None

    async def test_invalid_lang_rejected_by_check_constraint(self, db, group):
        with pytest.raises(sqlite3.IntegrityError):
            await queries.set_group_lang(db, group, "de")

    async def test_group_has_entries_tracks_voided_rows_too(self, db, group, members):
        assert await queries.group_has_entries(db, group) is False
        eid = await _expense(db, group, members, 300)
        assert await queries.group_has_entries(db, group) is True
        await queries.void_expense(db, eid, 101)
        # Still true: the voided row is still denominated in the old currency.
        assert await queries.group_has_entries(db, group) is True


class TestMembers:
    async def test_ghost_member_has_no_tg_id(self, db, members):
        assert (await queries.get_member(db, members[2])).tg_user_id is None

    async def test_duplicate_display_name_rejected(self, db, group, members):
        with pytest.raises(DuplicateMember):
            await queries.add_member(db, group, "Ali")

    async def test_same_name_in_another_group_is_fine(self, db, group, members):
        await queries.upsert_group(db, -200, "Other")
        assert await queries.add_member(db, -200, "Ali")

    async def test_one_telegram_account_per_group(self, db, group, members):
        with pytest.raises(DuplicateMember):
            await queries.add_member(db, group, "Ali Second Account", tg_user_id=101)

    async def test_multiple_ghosts_allowed(self, db, group, members):
        # The partial unique index must not treat two NULLs as equal.
        assert await queries.add_member(db, group, "Dara", tg_user_id=None)
        assert await queries.add_member(db, group, "Elham", tg_user_id=None)

    async def test_lookup_by_telegram_id(self, db, group, members):
        assert (await queries.get_member_by_tg(db, group, 102)).display_name == "Bita"

    async def test_list_excludes_inactive_by_default(self, db, group, members):
        await queries.set_member_active(db, members[1], False)
        assert [m.display_name for m in await queries.list_members(db, group)] == ["Ali", "Cyrus"]
        assert len(await queries.list_members(db, group, include_inactive=True)) == 3

    async def test_unused_member_can_be_deleted(self, db, group, members):
        await queries.remove_member(db, members[2])
        assert await queries.get_member(db, members[2]) is None

    async def test_member_with_entries_cannot_be_deleted(self, db, group, members):
        await _expense(db, group, members, 300)
        with pytest.raises(MemberInUse):
            await queries.remove_member(db, members[1])

    async def test_deleting_a_group_cascades_to_members(self, db, group, members):
        await db.execute("DELETE FROM groups WHERE group_id = ?", (group,))
        assert await queries.list_members(db, group, include_inactive=True) == []


class TestExpenseWrites:
    async def test_expense_and_splits_written_together(self, db, group, members):
        eid = await _expense(db, group, members, 300)
        assert await queries.get_expense_splits(db, eid) == {m: 100 for m in members}

    async def test_shares_that_do_not_sum_are_refused(self, db, group, members):
        with pytest.raises(SplitMismatch):
            await queries.create_expense(
                db,
                group_id=group,
                payer_id=members[0],
                amount_minor=300,
                currency_code="IRT",
                description="bad",
                created_by_tg=101,
                shares={members[0]: 100, members[1]: 100},  # 200 != 300
                idem_key=key(),
            )

    async def test_a_refused_expense_leaves_nothing_behind(self, db, group, members):
        with pytest.raises(SplitMismatch):
            await queries.create_expense(
                db,
                group_id=group,
                payer_id=members[0],
                amount_minor=300,
                currency_code="IRT",
                description="bad",
                created_by_tg=101,
                shares={members[0]: 1},
                idem_key=key(),
            )
        assert await db.fetchvalue("SELECT COUNT(*) FROM expenses") == 0
        assert await db.fetchvalue("SELECT COUNT(*) FROM expense_splits") == 0

    async def test_zero_amount_rejected_by_check_constraint(self, db, group, members):
        with pytest.raises(sqlite3.IntegrityError):
            await queries.create_expense(
                db,
                group_id=group,
                payer_id=members[0],
                amount_minor=0,
                currency_code="IRT",
                description="free",
                created_by_tg=101,
                shares={members[0]: 0},
                idem_key=key(),
            )

    async def test_expense_for_a_nonexistent_payer_is_rejected(self, db, group, members):
        # Only enforced because PRAGMA foreign_keys is on.
        with pytest.raises(sqlite3.IntegrityError):
            await queries.create_expense(
                db,
                group_id=group,
                payer_id=99999,
                amount_minor=100,
                currency_code="IRT",
                description="ghost payer",
                created_by_tg=101,
                shares={members[0]: 100},
                idem_key=key(),
            )


class TestIdempotency:
    async def test_same_key_twice_creates_one_expense(self, db, group, members):
        k = key()
        first = await _expense(db, group, members, 300, idem=k)
        second = await _expense(db, group, members, 300, idem=k)
        assert first == second
        assert await db.fetchvalue("SELECT COUNT(*) FROM expenses") == 1

    async def test_double_tap_does_not_double_the_splits(self, db, group, members):
        k = key()
        eid = await _expense(db, group, members, 300, idem=k)
        await _expense(db, group, members, 300, idem=k)
        assert sum((await queries.get_expense_splits(db, eid)).values()) == 300

    async def test_different_keys_create_separate_expenses(self, db, group, members):
        assert await _expense(db, group, members, 300) != await _expense(db, group, members, 300)

    async def test_settlement_idempotency(self, db, group, members):
        k = key()
        a = await queries.create_settlement(
            db, group_id=group, payer_id=members[1], payee_id=members[0],
            amount_minor=100, currency_code="IRT", created_by_tg=102, idem_key=k,
        )
        b = await queries.create_settlement(
            db, group_id=group, payer_id=members[1], payee_id=members[0],
            amount_minor=100, currency_code="IRT", created_by_tg=102, idem_key=k,
        )
        assert a == b
        assert await db.fetchvalue("SELECT COUNT(*) FROM settlements") == 1


class TestSettlementConstraints:
    async def test_cannot_pay_yourself(self, db, group, members):
        with pytest.raises(ValueError):
            await queries.create_settlement(
                db, group_id=group, payer_id=members[0], payee_id=members[0],
                amount_minor=100, currency_code="IRT", created_by_tg=101, idem_key=key(),
            )

    async def test_non_positive_amount_rejected(self, db, group, members):
        with pytest.raises(ValueError):
            await queries.create_settlement(
                db, group_id=group, payer_id=members[0], payee_id=members[1],
                amount_minor=0, currency_code="IRT", created_by_tg=101, idem_key=key(),
            )


class TestVoiding:
    async def test_void_marks_but_does_not_delete(self, db, group, members):
        eid = await _expense(db, group, members, 300)
        assert await queries.void_expense(db, eid, 101) is True
        row = await queries.get_expense(db, eid)
        assert row is not None and row["voided_at"] is not None and row["voided_by_tg"] == 101

    async def test_voiding_twice_is_reported_not_repeated(self, db, group, members):
        eid = await _expense(db, group, members, 300)
        await queries.void_expense(db, eid, 101)
        assert await queries.void_expense(db, eid, 101) is False

    async def test_voiding_an_unknown_id_returns_false(self, db):
        assert await queries.void_expense(db, 4242, 101) is False

    async def test_voided_expense_keeps_its_splits_for_history(self, db, group, members):
        eid = await _expense(db, group, members, 300)
        await queries.void_expense(db, eid, 101)
        assert len(await queries.get_expense_splits(db, eid)) == 3


class TestHistory:
    async def test_history_mixes_both_kinds_newest_first(self, db, group, members):
        await _expense(db, group, members, 300)
        await queries.create_settlement(
            db, group_id=group, payer_id=members[1], payee_id=members[0],
            amount_minor=100, currency_code="IRT", created_by_tg=102, idem_key=key(),
        )
        rows = await queries.list_history(db, group)
        assert {r["kind"] for r in rows} == {"expense", "settlement"}
        assert await queries.count_history(db, group) == 2

    async def test_history_includes_voided_entries(self, db, group, members):
        eid = await _expense(db, group, members, 300)
        await queries.void_expense(db, eid, 101)
        assert (await queries.list_history(db, group))[0]["voided_at"] is not None

    async def test_pagination(self, db, group, members):
        for _ in range(5):
            await _expense(db, group, members, 300)
        assert len(await queries.list_history(db, group, limit=2)) == 2
        assert len(await queries.list_history(db, group, limit=2, offset=4)) == 1


async def _expense(db, group, members, total, idem=None, payer_index=0):
    """Create an equal-split expense across all members."""
    from src.money import split_equal

    payer = members[payer_index]
    return await queries.create_expense(
        db,
        group_id=group,
        payer_id=payer,
        amount_minor=total,
        currency_code="IRT",
        description="dinner",
        created_by_tg=101,
        shares=split_equal(total, members, payer),
        idem_key=idem or key(),
    )


class TestBulkSplits:
    async def test_returns_splits_grouped_by_expense(self, db, group, members):
        a = await _expense(db, group, members, 300)
        b = await _expense(db, group, members, 600)
        result = await queries.get_splits_for_expenses(db, [a, b])
        assert result[a] == {m: 100 for m in members}
        assert result[b] == {m: 200 for m in members}

    async def test_empty_input_makes_no_query(self, db):
        assert await queries.get_splits_for_expenses(db, []) == {}

    async def test_unknown_ids_are_simply_absent(self, db, group, members):
        a = await _expense(db, group, members, 300)
        assert set(await queries.get_splits_for_expenses(db, [a, 9999])) == {a}

    async def test_matches_the_single_expense_query(self, db, group, members):
        a = await _expense(db, group, members, 301)
        assert (await queries.get_splits_for_expenses(db, [a]))[a] == (
            await queries.get_expense_splits(db, a)
        )

    async def test_voided_expenses_still_return_their_splits(self, db, group, members):
        # History shows deleted entries struck through, breakdown included.
        a = await _expense(db, group, members, 300)
        await queries.void_expense(db, a, 101)
        assert len((await queries.get_splits_for_expenses(db, [a]))[a]) == 3


class TestDeleteGroup:
    """Permanently deleting a group must take everything with it, and nothing else."""

    async def test_removes_the_group(self, db, group, members):
        await queries.delete_group(db, group)
        assert await queries.get_group(db, group) is None

    async def test_cascades_to_every_table(self, db, group, members):
        eid = await _expense(db, group, members, 300)
        await queries.create_settlement(
            db, group_id=group, payer_id=members[1], payee_id=members[0],
            amount_minor=100, currency_code="IRT", created_by_tg=102, idem_key=key(),
        )
        assert await db.fetchvalue("SELECT COUNT(*) FROM expense_splits") == 3

        await queries.delete_group(db, group)

        for table in ("groups", "users", "expenses", "expense_splits", "settlements"):
            assert await db.fetchvalue(f"SELECT COUNT(*) FROM {table}") == 0, table
        assert await queries.get_expense(db, eid) is None

    async def test_leaves_other_groups_untouched(self, db, group, members):
        await queries.upsert_group(db, -555, "Other")
        other = [
            await queries.add_member(db, -555, "Dara"),
            await queries.add_member(db, -555, "Elham"),
        ]
        await _expense(db, -555, other, 1000)
        await _expense(db, group, members, 300)

        await queries.delete_group(db, group)

        assert await queries.get_group(db, -555) is not None
        assert len(await queries.list_members(db, -555)) == 2
        assert await queries.count_history(db, -555) == 1

    async def test_deleting_an_unknown_group_is_harmless(self, db, group, members):
        await queries.delete_group(db, -99999)
        assert await queries.get_group(db, group) is not None


class TestSettings:
    async def test_unset_returns_the_default(self, db):
        assert await queries.get_setting(db, "nope") is None
        assert await queries.get_setting(db, "nope", "fallback") == "fallback"

    async def test_round_trip(self, db):
        await queries.set_setting(db, "admin_lang", "fa")
        assert await queries.get_setting(db, "admin_lang") == "fa"

    async def test_setting_twice_overwrites(self, db):
        await queries.set_setting(db, "admin_lang", "fa")
        await queries.set_setting(db, "admin_lang", "en")
        assert await queries.get_setting(db, "admin_lang") == "en"
        assert await db.fetchvalue("SELECT COUNT(*) FROM settings") == 1

    async def test_settings_survive_a_reconnect(self, db, tmp_path):
        from src.db.connection import Database

        path = tmp_path / "persist.db"
        first = Database(path)
        await first.connect()
        await queries.set_setting(first, "admin_lang", "fa")
        await first.close()

        second = Database(path)
        await second.connect()
        assert await queries.get_setting(second, "admin_lang") == "fa"
        await second.close()


class TestAdminPreferences:
    async def test_defaults_to_english(self, db):
        from src.admin_prefs import get_admin_lang

        assert await get_admin_lang(db) == "en"

    async def test_reads_what_was_stored(self, db):
        from src.admin_prefs import get_admin_lang, set_admin_lang

        await set_admin_lang(db, "fa")
        assert await get_admin_lang(db) == "fa"

    async def test_unknown_language_falls_back(self, db):
        # A downgrade must not leave the panel rendering raw translation keys.
        from src.admin_prefs import get_admin_lang

        await queries.set_setting(db, "admin_lang", "kl")
        assert await get_admin_lang(db) == "en"


class TestUpgradeFromAnOlderDatabase:
    """The README promises an update never touches your data.

    Simulated by dropping the table this release added, which leaves exactly
    the shape a 1.0.0 ledger has on disk, then reopening it with the current
    code the way a restart after `git pull` would.
    """

    async def test_settings_table_appears_and_data_survives(self, tmp_path):
        from src.db.connection import Database
        from src.ledger import net_balances
        from src.money import split_equal

        path = tmp_path / "old.db"

        old = Database(path)
        await old.connect()
        await queries.upsert_group(old, -100, "Trip")
        await queries.set_group_active(old, -100, True)
        people = [await queries.add_member(old, -100, n) for n in ("Ali", "Bita", "Cyrus")]
        await queries.create_expense(
            old, group_id=-100, payer_id=people[0], amount_minor=150_000,
            currency_code="IRT", description="petrol", created_by_tg=101,
            shares=split_equal(150_000, people, people[0]), idem_key=key(),
        )
        before = await net_balances(old, -100)
        # Roll the schema back to what 1.0.0 had on disk.
        await old.execute("DROP TABLE settings")
        assert await old.fetchvalue(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='settings'"
        ) == 0
        await old.close()

        upgraded = Database(path)
        await upgraded.connect()
        try:
            # The new table is created on connect, with no migration step.
            assert await upgraded.fetchvalue(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='settings'"
            ) == 1
            await queries.set_setting(upgraded, "admin_lang", "fa")
            assert await queries.get_setting(upgraded, "admin_lang") == "fa"

            # And nothing that was already there has moved.
            assert (await queries.get_group(upgraded, -100)).title == "Trip"
            assert len(await queries.list_members(upgraded, -100)) == 3
            assert await queries.count_history(upgraded, -100) == 1
            assert await net_balances(upgraded, -100) == before
        finally:
            await upgraded.close()
