"""
Tests for the SQL safety gate in the Datum adapter.

The gate lives in src/adapter/datum.py and blocks destructive SQL operations
(DROP, TRUNCATE, ALTER TABLE ... DROP, etc.) at the adapter boundary before
anything reaches the Datum proxy.

Legitimate operations (SELECT, INSERT, UPDATE, CREATE TABLE IF NOT EXISTS,
BEGIN/COMMIT) must pass through untouched.  DELETE FROM is always blocked.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.adapter.datum import (
    validate_sql_safety,
    DestructiveSqlError,
    DatumClient,
)


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  1. validate_sql_safety – allowed statements                          ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestSafetyGateAllowed:
    """Statements the app legitimately sends must pass the gate."""

    def test_simple_select(self):
        validate_sql_safety("SELECT * FROM users")

    def test_select_with_where(self):
        validate_sql_safety("SELECT id, name FROM users WHERE id = 1")

    def test_select_distinct(self):
        validate_sql_safety('SELECT DISTINCT "col" FROM schema.tbl ORDER BY "col"')

    def test_insert_into(self):
        validate_sql_safety(
            "INSERT INTO mods (row_pk, col) VALUES ('{}', 'name') RETURNING id"
        )

    def test_update_with_where(self):
        validate_sql_safety(
            'UPDATE "schema"."data" SET "col" = \'val\' WHERE "id" = 1'
        )

    def test_delete_from_with_where_is_blocked(self):
        with pytest.raises(DestructiveSqlError, match="DELETE FROM"):
            validate_sql_safety(
                "DELETE FROM schema.mods WHERE row_pk = '{}'::jsonb AND id = 5"
            )

    def test_create_table_if_not_exists(self):
        validate_sql_safety(
            "CREATE TABLE IF NOT EXISTS schema.mods (id SERIAL PRIMARY KEY)"
        )

    def test_create_schema_if_not_exists(self):
        validate_sql_safety('CREATE SCHEMA IF NOT EXISTS "myschema"')

    def test_create_index_if_not_exists(self):
        validate_sql_safety(
            "CREATE INDEX IF NOT EXISTS idx_mods_pk ON schema.mods (row_pk)"
        )

    def test_begin_commit_wrapper(self):
        validate_sql_safety(
            "BEGIN; UPDATE tbl SET x = 1 WHERE id = 2; COMMIT;"
        )

    def test_begin_insert_commit(self):
        validate_sql_safety(
            "BEGIN; INSERT INTO t (a) VALUES ('b'); COMMIT;"
        )

    def test_begin_delete_commit_is_blocked(self):
        with pytest.raises(DestructiveSqlError, match="DELETE FROM"):
            validate_sql_safety(
                "BEGIN; DELETE FROM t WHERE id = 1; COMMIT;"
            )

    def test_empty_sql_passes(self):
        validate_sql_safety("")

    def test_whitespace_only_passes(self):
        validate_sql_safety("   \n  ")

    def test_none_style_empty(self):
        validate_sql_safety("")

    def test_rollback(self):
        validate_sql_safety("ROLLBACK")

    def test_create_table_without_if_not_exists(self):
        validate_sql_safety(
            "CREATE TABLE schema.mods (id SERIAL PRIMARY KEY)"
        )

    def test_create_schema_without_if_not_exists(self):
        validate_sql_safety('CREATE SCHEMA "myschema"')


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  2. validate_sql_safety – blocked destructive operations              ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestSafetyGateBlocked:
    """Destructive DDL must be caught and rejected."""

    def test_drop_table(self):
        with pytest.raises(DestructiveSqlError, match="DROP TABLE"):
            validate_sql_safety("DROP TABLE users")

    def test_drop_table_if_exists(self):
        with pytest.raises(DestructiveSqlError, match="DROP TABLE"):
            validate_sql_safety("DROP TABLE IF EXISTS users")

    def test_drop_schema(self):
        with pytest.raises(DestructiveSqlError, match="DROP SCHEMA"):
            validate_sql_safety("DROP SCHEMA public CASCADE")

    def test_drop_database(self):
        with pytest.raises(DestructiveSqlError, match="DROP DATABASE"):
            validate_sql_safety("DROP DATABASE mydb")

    def test_drop_index(self):
        with pytest.raises(DestructiveSqlError, match="DROP INDEX"):
            validate_sql_safety("DROP INDEX idx_mods_pk")

    def test_drop_view(self):
        with pytest.raises(DestructiveSqlError, match="DROP VIEW"):
            validate_sql_safety("DROP VIEW my_view")

    def test_drop_function(self):
        with pytest.raises(DestructiveSqlError, match="DROP FUNCTION"):
            validate_sql_safety("DROP FUNCTION my_func()")

    def test_drop_trigger(self):
        with pytest.raises(DestructiveSqlError, match="DROP TRIGGER"):
            validate_sql_safety("DROP TRIGGER my_trigger ON my_table")

    def test_drop_sequence(self):
        with pytest.raises(DestructiveSqlError, match="DROP SEQUENCE"):
            validate_sql_safety("DROP SEQUENCE my_seq")

    def test_drop_type(self):
        with pytest.raises(DestructiveSqlError, match="DROP TYPE"):
            validate_sql_safety("DROP TYPE my_type")

    def test_truncate(self):
        with pytest.raises(DestructiveSqlError, match="TRUNCATE"):
            validate_sql_safety("TRUNCATE users")

    def test_truncate_table(self):
        with pytest.raises(DestructiveSqlError, match="TRUNCATE"):
            validate_sql_safety("TRUNCATE TABLE users CASCADE")

    def test_alter_table_drop_column(self):
        with pytest.raises(DestructiveSqlError, match="ALTER TABLE"):
            validate_sql_safety("ALTER TABLE users DROP COLUMN name")

    def test_alter_table_rename(self):
        with pytest.raises(DestructiveSqlError, match="ALTER TABLE"):
            validate_sql_safety("ALTER TABLE users RENAME TO old_users")

    def test_case_insensitive_drop(self):
        with pytest.raises(DestructiveSqlError):
            validate_sql_safety("drop table USERS")

    def test_case_insensitive_truncate(self):
        with pytest.raises(DestructiveSqlError):
            validate_sql_safety("Truncate users")

    def test_drop_embedded_in_begin_commit(self):
        """DROP hidden inside a transaction wrapper is still caught."""
        with pytest.raises(DestructiveSqlError):
            validate_sql_safety("BEGIN; DROP TABLE users; COMMIT;")

    def test_drop_table_with_leading_whitespace(self):
        with pytest.raises(DestructiveSqlError):
            validate_sql_safety("   \n  DROP TABLE users")


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  3. validate_sql_safety – unknown statement types                     ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestSafetyGateUnknownStatements:
    """Unrecognized statement types that aren't in the allowlist."""

    def test_grant(self):
        with pytest.raises(DestructiveSqlError, match="not in allowlist"):
            validate_sql_safety("GRANT ALL ON users TO public")

    def test_revoke(self):
        with pytest.raises(DestructiveSqlError, match="not in allowlist"):
            validate_sql_safety("REVOKE ALL ON users FROM public")

    def test_copy(self):
        with pytest.raises(DestructiveSqlError, match="not in allowlist"):
            validate_sql_safety("COPY users TO '/tmp/dump.csv'")

    def test_alter_table_add_column(self):
        """Even benign ALTER is not in allowlist — blocked by prefix check."""
        with pytest.raises(DestructiveSqlError):
            validate_sql_safety("ALTER TABLE users ADD COLUMN email TEXT")

    def test_vacuum(self):
        with pytest.raises(DestructiveSqlError, match="not in allowlist"):
            validate_sql_safety("VACUUM FULL users")


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  4. Injection payloads that attempt to smuggle destructive ops        ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestSafetyGateInjectionPayloads:
    """Injection attempts that try to sneak destructive SQL through."""

    def test_drop_in_filter_value_is_safe(self):
        """A DROP keyword inside a string literal is fine — it's data, not DDL.
        The blocked-pattern regex matches word boundaries, so 'DROP TABLE'
        inside a WHERE value still triggers. But in practice the app never
        constructs such SQL. This test documents the conservative behavior."""
        # This WILL trigger because the regex can't parse string literals.
        # This is the desired conservative behavior — false-positive on
        # destructive keywords even if they appear in string values.
        with pytest.raises(DestructiveSqlError):
            validate_sql_safety(
                "SELECT * FROM t WHERE note = 'DROP TABLE users'"
            )

    def test_semicolon_injection_drop(self):
        with pytest.raises(DestructiveSqlError):
            validate_sql_safety(
                "SELECT 1; DROP TABLE users; --"
            )

    def test_truncate_smuggled_after_select(self):
        with pytest.raises(DestructiveSqlError):
            validate_sql_safety("SELECT 1; TRUNCATE users")

    def test_update_without_where_allowed(self):
        """UPDATE without WHERE is risky but allowed — the app uses targeted
        UPDATEs and the safety gate is for DDL, not DML logic errors."""
        validate_sql_safety("UPDATE t SET x = 1")


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  5. Integration: DatumClient.execute_sql uses the gate                ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestDatumClientGateIntegration:
    """DatumClient.execute_sql must call validate_sql_safety before sending."""

    @pytest.fixture
    def client(self):
        return DatumClient(base_url="http://test", token="tok")

    def test_drop_table_blocked_before_network(self, client):
        """DROP TABLE must be blocked without any HTTP call."""
        with pytest.raises(DestructiveSqlError, match="DROP TABLE"):
            client.execute_sql(sql="DROP TABLE users", database="db")

    def test_truncate_blocked_before_network(self, client):
        with pytest.raises(DestructiveSqlError, match="TRUNCATE"):
            client.execute_sql(sql="TRUNCATE users", database="db")

    @patch("src.adapter.datum.DatumClient._call_proxy")
    def test_safe_select_reaches_proxy(self, mock_proxy, client):
        """A legitimate SELECT must pass the gate and call the proxy."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.body = '{"description":"ok","query":"SELECT 1","row_count":1,"columns":["?column?"],"data":[{"?column?":1}]}'
        mock_proxy.return_value = mock_resp

        result = client.execute_sql(sql="SELECT 1", database="db")
        assert mock_proxy.called
        assert result.row_count == 1

    @patch("src.adapter.datum.DatumClient._call_proxy")
    def test_safe_insert_reaches_proxy(self, mock_proxy, client):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.body = '{"description":"ok","query":"INSERT","row_count":1,"columns":["id"],"data":[{"id":1}]}'
        mock_proxy.return_value = mock_resp

        result = client.execute_sql(
            sql="BEGIN; INSERT INTO t (a) VALUES ('b') RETURNING id; COMMIT;",
            database="db",
        )
        assert mock_proxy.called

    @patch("src.adapter.datum.DatumClient._call_proxy")
    def test_delete_blocked_at_proxy(self, mock_proxy, client):
        """DELETE FROM is blocked by the safety gate before reaching proxy."""
        with pytest.raises(DestructiveSqlError, match="DELETE FROM"):
            client.execute_sql(
                sql="BEGIN; DELETE FROM t WHERE id = 1; COMMIT;",
                database="db",
            )
        assert not mock_proxy.called

    def test_drop_inside_transaction_blocked(self, client):
        with pytest.raises(DestructiveSqlError):
            client.execute_sql(
                sql="BEGIN; DROP TABLE users; COMMIT;", database="db"
            )
