"""
Blind-spot tests covering the three most critical audit findings:

  1. SQL INJECTION SURFACE  – Datum f-string interpolated methods have minimal
     escaping and zero tests.  Verify _escape_sql_value, _format_table_name,
     _build_where_clause(use_params=False), and every _*_datum() method
     produces safe (or at minimum, correctly-escaped) SQL when fed adversarial
     input.

  2. FETCH PIPELINE  – get_status_counts, get_filtered_count, fetch_page are
     the entire data path and were never tested.  Both Datum and SQLAlchemy
     modes are exercised.

  3. PARTIAL-FAILURE CONSISTENCY  – perform_cell_edit and perform_undo mutate
     the DataFrame BEFORE writing to the DB.  If the DB call raises, the
     caller gets back a modified DataFrame but the DB is unchanged.  Tests
     prove the inconsistency exists so the risk is documented and visible.
"""

import json
import os
import pandas as pd
import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers – lightweight surrogates so we never hit the real DB
# ---------------------------------------------------------------------------

from src.config.config_instance import (
    _format_table_name,
    _build_mod_status_expr,
    _escape_identifier,
    _escape_literal,
    DataFetcher,
    QueryParams,
)


def _make_fetcher(
    *,
    mode: str = "direct",
    datum_client: Any = None,
    engine: Any = None,
    columns: List[str] = None,
    data_table: str = "schema.data",
    mods_table: str = "schema.mods",
    pk_columns: List[str] = None,
    status_column: str = None,
    status_labels: dict = None,
    searchable_columns: List[str] = None,
) -> DataFetcher:
    """Build a DataFetcher without __post_init__ touching any real resource."""
    fetcher = object.__new__(DataFetcher)
    fetcher._columns = columns or ["id", "name", "status"]
    fetcher._total_count = 100
    fetcher._engine = engine
    fetcher._datum_client = datum_client

    # Minimal app_config stub
    cfg = MagicMock()
    cfg.database.mode = mode
    cfg.database.data_table = data_table
    cfg.database.mods_table = mods_table
    cfg.database.datum_database = "testdb"
    cfg.database.datum_schema = "public"
    cfg.database.datum_service_name = "svc"
    cfg.database.status_column = status_column
    cfg.table.primary_key = pk_columns or ["id"]
    cfg.query.searchable_columns = searchable_columns
    cfg.status_labels = status_labels
    # Needed when getattr(self.app_config, "status_labels", None) is called
    type(cfg).status_labels = status_labels
    fetcher.app_config = cfg
    return fetcher


def _make_config_instance(
    *,
    mode: str = "datum",
    datum_base_url: str = "http://datum",
    datum_token: str = "tok",
    datum_database: str = "testdb",
    datum_schema: str = "public",
    datum_service_name: str = "svc",
    data_table: str = "schema.data",
    mods_table: str = "schema.mods",
    pk_columns: List[str] = None,
    username: str = "testuser",
    status_column: str = None,
):
    """Build a lightweight mock that has the attributes Datum methods access."""
    ci = MagicMock()
    ci.app_config.database.mode = mode
    ci.app_config.database.datum_base_url = datum_base_url
    ci.app_config.database.datum_token = datum_token
    ci.app_config.database.datum_database = datum_database
    ci.app_config.database.datum_schema = datum_schema
    ci.app_config.database.datum_service_name = datum_service_name
    ci.app_config.database.data_table = data_table
    ci.app_config.database.mods_table = mods_table
    ci.app_config.database.state_table = "schema.state"
    ci.app_config.database.status_column = status_column
    ci.app_config.table.primary_key = pk_columns or ["id"]
    ci.username = username
    return ci


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  1.  SQL INJECTION SURFACE                                            ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestEscapeSqlValue:
    """Direct unit tests for DataFetcher._escape_sql_value."""

    @pytest.fixture
    def fetcher(self):
        return _make_fetcher()

    # -- happy-path -----------------------------------------------------------
    def test_none_returns_null(self, fetcher):
        assert fetcher._escape_sql_value(None) == "NULL"

    def test_bool_true(self, fetcher):
        assert fetcher._escape_sql_value(True) == "TRUE"

    def test_bool_false(self, fetcher):
        assert fetcher._escape_sql_value(False) == "FALSE"

    def test_int(self, fetcher):
        assert fetcher._escape_sql_value(42) == "42"

    def test_float(self, fetcher):
        assert fetcher._escape_sql_value(3.14) == "3.14"

    def test_plain_string(self, fetcher):
        assert fetcher._escape_sql_value("hello") == "'hello'"

    # -- adversarial strings --------------------------------------------------
    def test_single_quote_doubled(self, fetcher):
        """O'Brien must become O''Brien inside quotes."""
        assert fetcher._escape_sql_value("O'Brien") == "'O''Brien'"

    def test_double_single_quote(self, fetcher):
        assert fetcher._escape_sql_value("it''s") == "'it''''s'"

    def test_classic_injection_payload(self, fetcher):
        val = "'; DROP TABLE users; --"
        result = fetcher._escape_sql_value(val)
        # The dangerous ' must be doubled, making parsed SQL a string literal
        assert "''" in result
        assert result == "'''; DROP TABLE users; --'"

    def test_backslash_quote(self, fetcher):
        """PostgreSQL standard_conforming_strings=on treats \\ as literal."""
        val = "back\\slash"
        result = fetcher._escape_sql_value(val)
        assert result == "'back\\slash'"

    def test_unicode_injection(self, fetcher):
        val = "val\u0027; DROP TABLE x; --"  # \u0027 is '
        result = fetcher._escape_sql_value(val)
        assert "''" in result  # The embedded quote must be doubled

    def test_empty_string(self, fetcher):
        assert fetcher._escape_sql_value("") == "''"

    def test_newline_in_string(self, fetcher):
        """Newlines should pass through – they are valid inside SQL strings."""
        val = "line1\nline2"
        result = fetcher._escape_sql_value(val)
        assert result == "'line1\nline2'"

    def test_null_byte(self, fetcher):
        """Null bytes must not truncate the string."""
        val = "a\x00b"
        result = fetcher._escape_sql_value(val)
        assert "a" in result and "b" in result


class TestFormatTableName:
    """Test _format_table_name with adversarial inputs."""

    def test_simple_name(self):
        assert _format_table_name("users") == '"users"'

    def test_schema_qualified(self):
        assert _format_table_name("public.users") == '"public"."users"'

    def test_three_part_name(self):
        result = _format_table_name("catalog.schema.table")
        assert result == '"catalog"."schema"."table"'

    def test_embedded_double_quote(self):
        """Double-quote in the name IS now escaped by doubling."""
        result = _format_table_name('evil"name')
        # Should produce '"evil""name"' — escaped double-quote
        assert result == '"evil""name"'

    def test_semicolon_in_name(self):
        result = _format_table_name("schema;DROP TABLE x")
        # It's wrapped in double-quotes, so the semicolon is inert
        assert result == '"schema;DROP TABLE x"'

    def test_empty_string(self):
        """Empty table name now raises ValueError (not a valid table name)."""
        with pytest.raises(ValueError):
            _format_table_name("")


class TestBuildWhereClauseInjection:
    """_build_where_clause with use_params=False (Datum mode)."""

    @pytest.fixture
    def fetcher(self):
        return _make_fetcher(columns=["name", "status", "age"])

    def test_exact_match_injection(self, fetcher):
        params = QueryParams(filters={"name": "'; DROP TABLE users; --"})
        clause, sql_params = fetcher._build_where_clause(params, use_params=False)
        # Must NOT contain an un-escaped single quote
        assert "DROP TABLE" in clause  # payload gets through as a string
        assert "''''" in clause or "''" in clause  # but the quote is doubled

    def test_list_filter_injection(self, fetcher):
        params = QueryParams(filters={"name": ["safe", "'; DROP TABLE x; --"]})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        # Each value individually escaped
        assert "'safe'" in clause
        assert "''" in clause  # doubled quote

    def test_operator_contains_injection(self, fetcher):
        params = QueryParams(filters={"name": {"op": "contains", "value": "'; DELETE FROM t; --"}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert "ILIKE" in clause
        assert "''" in clause  # quote doubled

    def test_search_term_injection(self, fetcher):
        params = QueryParams(search_term="' OR 1=1 --")
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert "ILIKE" in clause
        assert "''" in clause

    def test_regex_filter_injection(self, fetcher):
        params = QueryParams(filters={"name": {"op": "regex", "value": ".*'; DROP TABLE--"}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert "''" in clause

    def test_between_filter_injection(self, fetcher):
        params = QueryParams(filters={"age": {"op": "between", "value": ["1' OR '1'='1", "100"]}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert "BETWEEN" in clause
        assert "''" in clause

    def test_parameterized_mode_returns_placeholders(self, fetcher):
        """Parameterized mode must NOT interpolate values."""
        params = QueryParams(filters={"name": "'; DROP TABLE users; --"})
        clause, sql_params = fetcher._build_where_clause(params, use_params=True)
        assert ":p0" in clause
        assert "DROP TABLE" not in clause
        assert sql_params["p0"] == "'; DROP TABLE users; --"


class TestBuildStatusFilterClause:
    """_build_status_filter_clause — status values are not escaped."""

    @pytest.fixture
    def fetcher(self):
        return _make_fetcher()

    def test_no_filter_returns_empty(self, fetcher):
        params = QueryParams()
        assert fetcher._build_status_filter_clause(params) == ""

    def test_all_statuses_returns_empty(self, fetcher):
        params = QueryParams(status_filters=["unprocessed", "edited", "approved", "rejected"])
        assert fetcher._build_status_filter_clause(params) == ""

    def test_subset_produces_in_clause(self, fetcher):
        params = QueryParams(status_filters=["edited", "approved"])
        result = fetcher._build_status_filter_clause(params)
        assert "_mod_status IN" in result
        assert "'edited'" in result
        assert "'approved'" in result


class TestDatumUpdateInjection:
    """_update_data_in_datum – now properly escapes PK values, new_value, and column names."""

    def _call_update(self, row_pk, column, new_value, pk_columns=None):
        """Import the real method and call it, capturing the SQL sent to DatumClient."""
        from src.config.config_instance import ConfigInstance

        ci = object.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.datum_base_url = "http://datum"
        ci.app_config.database.datum_token = "tok"
        ci.app_config.database.datum_database = "testdb"
        ci.app_config.database.datum_schema = "public"
        ci.app_config.database.datum_service_name = "svc"
        ci.app_config.database.data_table = "schema.data"
        ci.app_config.table.primary_key = pk_columns or ["id"]

        mock_client = MagicMock()
        with patch("src.adapter.datum.DatumClient", return_value=mock_client):
            ci._update_data_in_datum(row_pk, column, new_value)

        if mock_client.execute_sql.called:
            return mock_client.execute_sql.call_args
        return None

    def test_string_pk_with_quote_now_escaped(self):
        """PK string values are now properly escaped in _update_data_in_datum."""
        result = self._call_update(
            row_pk={"id": "val'ue"},
            column="name",
            new_value="safe",
        )
        assert result is not None
        sql = result.kwargs.get("sql") or result[1].get("sql") if result[1] else result[0][0]
        # The quote must be doubled — injection mitigated
        assert "val''ue" in sql
        assert "val'ue" not in sql.replace("val''ue", "")

    def test_new_value_with_quote_now_escaped(self):
        """new_value containing a single quote is now properly escaped."""
        result = self._call_update(
            row_pk={"id": 1},
            column="name",
            new_value="it's",
        )
        assert result is not None
        sql = result.kwargs.get("sql") or result[1].get("sql") if result[1] else result[0][0]
        # The embedded quote must be doubled
        assert "it''s" in sql

    def test_column_name_with_quote(self):
        """Column name embedded double-quotes are now escaped by doubling."""
        result = self._call_update(
            row_pk={"id": 1},
            column='col"inject',
            new_value="x",
        )
        assert result is not None
        sql = result.kwargs.get("sql") or result[1].get("sql") if result[1] else result[0][0]
        # Double-quote in identifier must be doubled
        assert 'col""inject' in sql

    def test_none_value_gives_null(self):
        result = self._call_update(
            row_pk={"id": 1},
            column="name",
            new_value=None,
        )
        assert result is not None
        sql = result.kwargs.get("sql") or result[1].get("sql") if result[1] else result[0][0]
        assert "NULL" in sql

    def test_numeric_pk_no_quotes(self):
        result = self._call_update(
            row_pk={"id": 42},
            column="name",
            new_value="val",
        )
        assert result is not None
        sql = result.kwargs.get("sql") or result[1].get("sql") if result[1] else result[0][0]
        assert '"id" = 42' in sql


class TestDatumSaveModification:
    """_save_modification_to_datum escapes SOME values but not all."""

    def _call_save(self, row_pk, column, old_value, new_value, mod_type="field_modification",
                   username="testuser"):
        from src.config.config_instance import ConfigInstance
        ci = object.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.datum_base_url = "http://datum"
        ci.app_config.database.datum_token = "tok"
        ci.app_config.database.datum_database = "testdb"
        ci.app_config.database.datum_schema = "public"
        ci.app_config.database.datum_service_name = "svc"
        ci.app_config.database.mods_table = "schema.mods"
        ci.username = username
        ci._ensure_mods_table_exists = MagicMock()
        ci.invalidate_mods_cache = MagicMock()

        mock_client = MagicMock()
        mock_client.execute_sql.return_value = MagicMock(data=[{"id": 1}])
        with patch("src.adapter.datum.DatumClient", return_value=mock_client):
            ci._save_modification_to_datum(row_pk, column, old_value, new_value, mod_type)

        if mock_client.execute_sql.called:
            return mock_client.execute_sql.call_args_list[0]  # first call is the INSERT
        return None

    def test_column_with_single_quote_escaped(self):
        result = self._call_save({"id": "PK1"}, "col'name", "old", "new")
        assert result is not None
        sql = result.kwargs.get("sql", result[1].get("sql", ""))
        # column is escaped: replace("'", "''")
        assert "col''name" in sql

    def test_old_value_with_single_quote_escaped(self):
        result = self._call_save({"id": "PK1"}, "col", "it's", "new")
        assert result is not None
        sql = result.kwargs.get("sql", result[1].get("sql", ""))
        assert "it''s" in sql

    def test_new_value_with_single_quote_escaped(self):
        result = self._call_save({"id": "PK1"}, "col", "old", "it's")
        assert result is not None
        sql = result.kwargs.get("sql", result[1].get("sql", ""))
        assert "it''s" in sql

    def test_none_old_value_gives_null(self):
        result = self._call_save({"id": "PK1"}, "col", None, "new")
        assert result is not None
        sql = result.kwargs.get("sql", result[1].get("sql", ""))
        assert "NULL" in sql

    def test_username_escaped_but_unused_in_insert(self):
        """Username is escaped (safe_username) but NOT included in the INSERT
        columns.  This documents the dead code: created_by is missing from
        the SQL, so the escaping has no effect.  The test proves the column
        list omits username."""
        result = self._call_save({"id": "PK1"}, "col", "old", "new", username="O'Malley")
        assert result is not None
        sql = result.kwargs.get("sql", result[1].get("sql", ""))
        # Username not in INSERT — documenting the gap
        assert "O'Malley" not in sql
        assert "created_by" not in sql

    def test_row_pk_json_quotes_escaped(self):
        result = self._call_save({"key": "val'ue"}, "col", "old", "new")
        assert result is not None
        sql = result.kwargs.get("sql", result[1].get("sql", ""))
        # json.dumps + .replace("'", "''") should double the quote in JSON
        assert "''" in sql


class TestDatumDeletePreset:
    """_delete_preset_datum – preset_name escaping."""

    def _call_delete(self, preset_name):
        from src.config.config_instance import ConfigInstance
        ci = object.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.datum_base_url = "http://datum"
        ci.app_config.database.datum_token = "tok"
        ci.app_config.database.datum_database = "testdb"
        ci.app_config.database.datum_schema = "public"
        ci.app_config.database.datum_service_name = "svc"
        ci._get_preset_table_name = MagicMock(return_value="schema.presets")

        mock_client = MagicMock()
        with patch("src.adapter.datum.DatumClient", return_value=mock_client):
            ci._delete_preset_datum(preset_name)

        if mock_client.execute_sql.called:
            return mock_client.execute_sql.call_args
        return None

    def test_preset_name_escaped(self):
        result = self._call_delete("it's a test")
        assert result is not None
        sql = result.kwargs.get("sql", result[1].get("sql", ""))
        assert "it''s a test" in sql

    def test_injection_via_preset_name(self):
        result = self._call_delete("'; DROP TABLE presets; --")
        assert result is not None
        sql = result.kwargs.get("sql", result[1].get("sql", ""))
        assert "''''" in sql or "''" in sql  # quote before ; must be doubled


class TestDatumMarkUndone:
    """_mark_modification_undone_datum – mod_id is now validated as integer."""

    def _call_mark(self, mod_id):
        from src.config.config_instance import ConfigInstance
        ci = object.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.datum_base_url = "http://datum"
        ci.app_config.database.datum_token = "tok"
        ci.app_config.database.datum_database = "testdb"
        ci.app_config.database.datum_schema = "public"
        ci.app_config.database.datum_service_name = "svc"
        ci.app_config.database.mods_table = "schema.mods"
        ci.invalidate_mods_cache = MagicMock()

        mock_client = MagicMock()
        with patch("src.adapter.datum.DatumClient", return_value=mock_client):
            result = ci._mark_modification_undone_datum(mod_id)

        return result, mock_client

    def test_integer_mod_id(self):
        ok, client = self._call_mark(42)
        assert ok is True
        sql = client.execute_sql.call_args.kwargs.get(
            "sql", client.execute_sql.call_args[1].get("sql", "")
        )
        assert "WHERE id = 42" in sql

    def test_string_mod_id_injection(self):
        """Non-int mod_id is now rejected by int() validation."""
        ok, client = self._call_mark("1; DROP TABLE mods; --")
        # int() conversion raises ValueError, caught by except block
        assert ok is False
        assert not client.execute_sql.called  # SQL never sent


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  2.  FETCH PIPELINE                                                    ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestGetStatusCounts:
    """DataFetcher.get_status_counts – both modes + exception."""

    def test_datum_mode_returns_counts(self):
        mock_client = MagicMock()
        mock_client.execute_sql.return_value = MagicMock(data=[
            {"_mod_status": "unprocessed", "cnt": 50},
            {"_mod_status": "edited", "cnt": 10},
            {"_mod_status": "approved", "cnt": 5},
            {"_mod_status": "rejected", "cnt": 2},
        ])
        fetcher = _make_fetcher(mode="datum", datum_client=mock_client, pk_columns=["id"])
        counts = fetcher.get_status_counts()
        assert counts == {"unprocessed": 50, "edited": 10, "approved": 5, "rejected": 2}

    def test_datum_mode_partial_counts(self):
        """Response missing some statuses should still return zeroes for them."""
        mock_client = MagicMock()
        mock_client.execute_sql.return_value = MagicMock(data=[
            {"_mod_status": "edited", "cnt": 3},
        ])
        fetcher = _make_fetcher(mode="datum", datum_client=mock_client, pk_columns=["id"])
        counts = fetcher.get_status_counts()
        assert counts["unprocessed"] == 0
        assert counts["edited"] == 3
        assert counts["approved"] == 0

    def test_sqlalchemy_mode_returns_counts(self):
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("unprocessed", 40),
            ("edited", 8),
        ]
        mock_conn.execute.return_value = mock_result
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        fetcher = _make_fetcher(mode="direct", engine=mock_engine, pk_columns=["id"])
        counts = fetcher.get_status_counts()
        assert counts["unprocessed"] == 40
        assert counts["edited"] == 8
        assert counts["approved"] == 0

    def test_exception_returns_zeroes(self):
        mock_client = MagicMock()
        mock_client.execute_sql.side_effect = RuntimeError("connection timeout")
        fetcher = _make_fetcher(mode="datum", datum_client=mock_client, pk_columns=["id"])
        counts = fetcher.get_status_counts()
        assert counts == {"unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}

    def test_with_filters_passes_where_clause(self):
        mock_client = MagicMock()
        mock_client.execute_sql.return_value = MagicMock(data=[])
        fetcher = _make_fetcher(mode="datum", datum_client=mock_client,
                                pk_columns=["id"], columns=["id", "name"])
        params = QueryParams(filters={"name": "test"})
        fetcher.get_status_counts(params)
        sql = mock_client.execute_sql.call_args.kwargs.get(
            "sql", mock_client.execute_sql.call_args[1].get("sql", "")
        )
        assert "WHERE" in sql
        assert "GROUP BY" in sql


class TestGetFilteredCount:
    """DataFetcher.get_filtered_count – both modes + exception."""

    def test_datum_mode_returns_count(self):
        mock_client = MagicMock()
        mock_client.execute_sql.return_value = MagicMock(data=[{"cnt": 42}])
        fetcher = _make_fetcher(mode="datum", datum_client=mock_client, pk_columns=["id"])
        params = QueryParams()
        result = fetcher.get_filtered_count(params)
        assert result == 42

    def test_datum_empty_response_returns_zero(self):
        mock_client = MagicMock()
        mock_client.execute_sql.return_value = MagicMock(data=[])
        fetcher = _make_fetcher(mode="datum", datum_client=mock_client, pk_columns=["id"])
        result = fetcher.get_filtered_count(QueryParams())
        assert result == 0

    def test_sqlalchemy_mode_returns_count(self):
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (17,)
        mock_conn.execute.return_value = mock_result
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        fetcher = _make_fetcher(mode="direct", engine=mock_engine, pk_columns=["id"])
        result = fetcher.get_filtered_count(QueryParams())
        assert result == 17

    def test_exception_returns_zero(self):
        mock_client = MagicMock()
        mock_client.execute_sql.side_effect = Exception("boom")
        fetcher = _make_fetcher(mode="datum", datum_client=mock_client, pk_columns=["id"])
        result = fetcher.get_filtered_count(QueryParams())
        assert result == 0

    def test_status_filter_included(self):
        mock_client = MagicMock()
        mock_client.execute_sql.return_value = MagicMock(data=[{"cnt": 5}])
        fetcher = _make_fetcher(mode="datum", datum_client=mock_client,
                                pk_columns=["id"], columns=["id", "name"])
        params = QueryParams(status_filters=["edited"])
        fetcher.get_filtered_count(params)
        sql = mock_client.execute_sql.call_args.kwargs.get(
            "sql", mock_client.execute_sql.call_args[1].get("sql", "")
        )
        assert "_mod_status IN" in sql
        assert "'edited'" in sql


class TestFetchPage:
    """DataFetcher.fetch_page – the main data pipeline."""

    def _make_datum_fetcher(self, response_data):
        mock_client = MagicMock()
        mock_client.execute_sql.return_value = MagicMock(data=response_data)
        fetcher = _make_fetcher(
            mode="datum",
            datum_client=mock_client,
            pk_columns=["id"],
            columns=["id", "name"],
        )
        fetcher._apply_field_modifications = MagicMock(side_effect=lambda df: df)
        return fetcher, mock_client

    def test_datum_returns_dataframe(self):
        data = [{"id": 1, "name": "a", "_mod_status": "unprocessed"},
                {"id": 2, "name": "b", "_mod_status": "edited"}]
        fetcher, _ = self._make_datum_fetcher(data)
        df = fetcher.fetch_page(QueryParams(page=1, page_size=10))
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["id", "name", "_mod_status"]

    def test_datum_applies_field_modifications(self):
        fetcher, _ = self._make_datum_fetcher([{"id": 1, "_mod_status": "x"}])
        fetcher.fetch_page(QueryParams())
        fetcher._apply_field_modifications.assert_called_once()

    def test_sort_column_in_query(self):
        fetcher, client = self._make_datum_fetcher([])
        fetcher.fetch_page(QueryParams(sort_column="name", sort_ascending=False))
        sql = client.execute_sql.call_args.kwargs.get(
            "sql", client.execute_sql.call_args[1].get("sql", "")
        )
        assert 'ORDER BY "name" DESC' in sql

    def test_pagination_in_query(self):
        fetcher, client = self._make_datum_fetcher([])
        fetcher.fetch_page(QueryParams(page=3, page_size=25))
        sql = client.execute_sql.call_args.kwargs.get(
            "sql", client.execute_sql.call_args[1].get("sql", "")
        )
        assert "LIMIT 25" in sql
        assert "OFFSET 50" in sql

    def test_filters_in_query(self):
        fetcher, client = self._make_datum_fetcher([])
        fetcher.fetch_page(QueryParams(filters={"name": "test"}))
        sql = client.execute_sql.call_args.kwargs.get(
            "sql", client.execute_sql.call_args[1].get("sql", "")
        )
        assert "WHERE" in sql
        assert "'test'" in sql

    def test_status_filter_in_query(self):
        fetcher, client = self._make_datum_fetcher([])
        fetcher.fetch_page(QueryParams(status_filters=["approved"]))
        sql = client.execute_sql.call_args.kwargs.get(
            "sql", client.execute_sql.call_args[1].get("sql", "")
        )
        assert "_mod_status IN" in sql

    def test_exception_returns_empty_dataframe(self):
        mock_client = MagicMock()
        mock_client.execute_sql.side_effect = RuntimeError("crash")
        fetcher = _make_fetcher(mode="datum", datum_client=mock_client, pk_columns=["id"])
        df = fetcher.fetch_page(QueryParams())
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_sqlalchemy_mode(self):
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(1, "a", "unprocessed")]
        mock_result.keys.return_value = ["id", "name", "_mod_status"]
        mock_conn.execute.return_value = mock_result
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        fetcher = _make_fetcher(mode="direct", engine=mock_engine,
                                pk_columns=["id"], columns=["id", "name"])
        fetcher._apply_field_modifications = MagicMock(side_effect=lambda df: df)
        df = fetcher.fetch_page(QueryParams(page=1, page_size=10))
        assert len(df) == 1

    def test_default_order_uses_pk(self):
        """When no sort_column is set, ORDER BY first PK column."""
        fetcher, client = self._make_datum_fetcher([])
        fetcher.fetch_page(QueryParams())
        sql = client.execute_sql.call_args.kwargs.get(
            "sql", client.execute_sql.call_args[1].get("sql", "")
        )
        assert 'ORDER BY "id" ASC' in sql

    def test_unknown_sort_column_ignored(self):
        """Sort column not in _columns should be skipped, falling back to PK."""
        fetcher, client = self._make_datum_fetcher([])
        fetcher.fetch_page(QueryParams(sort_column="nonexistent"))
        sql = client.execute_sql.call_args.kwargs.get(
            "sql", client.execute_sql.call_args[1].get("sql", "")
        )
        assert 'ORDER BY "id" ASC' in sql  # fallback to PK


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  3.  PARTIAL-FAILURE CONSISTENCY                                       ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestPartialFailureCellEdit:
    """
    perform_cell_edit now writes to DB BEFORE mutating the DataFrame.
    If update_data_in_db raises, the returned DataFrame is unchanged.
    If save_modification_to_db raises (but update succeeded), DF is mutated.
    """

    @pytest.fixture
    def df(self):
        return pd.DataFrame({
            "PatientID_Mutsequence": ["PK001", "PK002"],
            "Gene_names": ["BRCA1", "TP53"],
        })

    @pytest.fixture
    def ci(self):
        ci = MagicMock()
        ci.app_config.table.primary_key = ["PatientID_Mutsequence"]
        ci.update_data_in_db = MagicMock(return_value=True)
        ci.save_modification_to_db = MagicMock(return_value=999)
        return ci

    def test_happy_path_df_and_db_agree(self, df, ci):
        from src.utils.data_operations import perform_cell_edit
        updated_df, updated_log = perform_cell_edit(
            df, [], 0, "Gene_names", "BRCA1", "MUTANT", config_instance=ci
        )
        assert updated_df.iloc[0]["Gene_names"] == "MUTANT"
        ci.update_data_in_db.assert_called_once()
        ci.save_modification_to_db.assert_called_once()

    def test_update_db_raises_df_not_mutated(self, df, ci):
        """DataFrame is NOT changed when update_data_in_db raises (fixed)."""
        ci.update_data_in_db.side_effect = RuntimeError("DB connection lost")

        from src.utils.data_operations import perform_cell_edit
        updated_df, updated_log = perform_cell_edit(
            df, [], 0, "Gene_names", "BRCA1", "MUTANT", config_instance=ci
        )
        # DataFrame NOT mutated because DB write failed first
        assert updated_df.iloc[0]["Gene_names"] == "BRCA1"
        ci.update_data_in_db.assert_called_once()
        # save_modification_to_db should NOT be called after update failure
        ci.save_modification_to_db.assert_not_called()

    def test_save_modification_raises_df_still_mutated(self, df, ci):
        """DB data table updated, but audit record failed – DF is still mutated
        since the primary UPDATE succeeded."""
        ci.save_modification_to_db.side_effect = RuntimeError("audit table locked")

        from src.utils.data_operations import perform_cell_edit
        updated_df, updated_log = perform_cell_edit(
            df, [], 0, "Gene_names", "BRCA1", "MUTANT", config_instance=ci
        )
        # DataFrame changed because update_data_in_db succeeded
        assert updated_df.iloc[0]["Gene_names"] == "MUTANT"
        # update_data_in_db succeeded
        ci.update_data_in_db.assert_called_once()
        # save_modification_to_db was called (and raised)
        ci.save_modification_to_db.assert_called_once()
        # Log entry exists but WITHOUT db_id (because save raised)
        assert len(updated_log) == 1
        assert "db_id" not in updated_log[0]  # no id returned from failed save

    def test_original_df_not_mutated(self, df, ci):
        """perform_cell_edit copies the DF; original must stay pristine."""
        ci.update_data_in_db.side_effect = RuntimeError("boom")
        original_value = df.iloc[0]["Gene_names"]

        from src.utils.data_operations import perform_cell_edit
        perform_cell_edit(df, [], 0, "Gene_names", "BRCA1", "MUT", config_instance=ci)

        assert df.iloc[0]["Gene_names"] == original_value

    def test_both_db_calls_raise_df_not_mutated(self, df, ci):
        """Both DB calls fail; DataFrame is NOT mutated, no phantom log entry (fixed)."""
        ci.update_data_in_db.side_effect = RuntimeError("down")
        ci.save_modification_to_db.side_effect = RuntimeError("down")

        from src.utils.data_operations import perform_cell_edit
        updated_df, updated_log = perform_cell_edit(
            df, [], 0, "Gene_names", "BRCA1", "X", config_instance=ci
        )
        # DataFrame NOT mutated because first DB call failed
        assert updated_df.iloc[0]["Gene_names"] == "BRCA1"
        # Log NOT mutated either — phantom log entry bug is fixed (Finding #30)
        assert len(updated_log) == 0


class TestPartialFailureUndo:
    """
    perform_undo now writes to DB BEFORE mutating the DataFrame.
    Any DB failure returns (None, None, None, error_message) without
    mutating the DataFrame, preventing inconsistent state.
    """

    @pytest.fixture
    def df(self):
        return pd.DataFrame({
            "PatientID_Mutsequence": ["PK001"],
            "Gene_names": ["MUTANT"],
        })

    @pytest.fixture
    def log(self):
        return [{
            "db_id": 100,
            "timestamp": "2026-01-01",
            "type": "field_modification",
            "details": {
                "row_pk": {"PatientID_Mutsequence": "PK001"},
                "column": "Gene_names",
                "old_value": "BRCA1",
                "new_value": "MUTANT",
            }
        }]

    @pytest.fixture
    def ci(self):
        ci = MagicMock()
        ci.app_config.table.primary_key = ["PatientID_Mutsequence"]
        ci.update_data_in_db = MagicMock(return_value=True)
        ci.mark_modification_undone_in_db = MagicMock()
        ci.save_modification_to_db = MagicMock(return_value=200)
        return ci

    def test_happy_path_undo(self, df, log, ci):
        from src.utils.data_operations import perform_undo
        udf, ulog, msg, err = perform_undo(df, log, 0, config_instance=ci)
        assert err is None
        assert udf.iloc[0]["Gene_names"] == "BRCA1"
        assert ulog[0]["undone"] is True
        ci.update_data_in_db.assert_called_once()
        ci.mark_modification_undone_in_db.assert_called_once_with(100)
        ci.save_modification_to_db.assert_called_once()

    def test_update_db_raises_returns_error(self, df, log, ci):
        """DB revert failure returns error, DataFrame NOT reverted."""
        ci.update_data_in_db.side_effect = RuntimeError("DB down")

        from src.utils.data_operations import perform_undo
        udf, ulog, msg, err = perform_undo(df, log, 0, config_instance=ci)
        assert udf is None
        assert err is not None
        assert "Database error" in err

    def test_mark_undone_raises_returns_error(self, df, log, ci):
        """update_data_in_db succeeds, mark_undone raises → error returned, no DF mutation."""
        ci.mark_modification_undone_in_db.side_effect = RuntimeError("lock timeout")

        from src.utils.data_operations import perform_undo
        udf, ulog, msg, err = perform_undo(df, log, 0, config_instance=ci)
        assert udf is None
        assert "Database error" in err
        # The data table call WAS attempted
        ci.update_data_in_db.assert_called_once()

    def test_save_undo_record_raises_returns_error(self, df, log, ci):
        """update + mark succeed, save undo record raises → error returned."""
        ci.save_modification_to_db.side_effect = RuntimeError("disk full")

        from src.utils.data_operations import perform_undo
        udf, ulog, msg, err = perform_undo(df, log, 0, config_instance=ci)
        assert udf is None
        assert "Database error" in err
        ci.update_data_in_db.assert_called_once()
        ci.mark_modification_undone_in_db.assert_called_once()

    def test_original_df_not_mutated_on_failure(self, df, log, ci):
        """perform_undo copies df; original must be unchanged on DB failure."""
        ci.save_modification_to_db.side_effect = RuntimeError("fail")
        original = df.iloc[0]["Gene_names"]

        from src.utils.data_operations import perform_undo
        udf, ulog, msg, err = perform_undo(df, log, 0, config_instance=ci)
        assert err is not None
        assert df.iloc[0]["Gene_names"] == original

    def test_undo_no_db_id_skips_mark_undone(self, df, ci):
        """When log entry has no db_id, mark_modification_undone is skipped."""
        log_no_id = [{
            "timestamp": "2026-01-01",
            "type": "field_modification",
            "details": {
                "row_pk": {"PatientID_Mutsequence": "PK001"},
                "column": "Gene_names",
                "old_value": "BRCA1",
                "new_value": "MUTANT",
            }
        }]
        from src.utils.data_operations import perform_undo
        udf, ulog, msg, err = perform_undo(df, log_no_id, 0, config_instance=ci)
        assert err is None
        ci.mark_modification_undone_in_db.assert_not_called()
        ci.save_modification_to_db.assert_called_once()


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  4.  COMPREHENSIVE SQL INJECTION HARDENING TESTS                      ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestEscapeIdentifier:
    """Unit tests for the _escape_identifier module-level helper."""

    def test_plain_name(self):
        assert _escape_identifier("column_name") == "column_name"

    def test_double_quote_doubled(self):
        assert _escape_identifier('evil"col') == 'evil""col'

    def test_multiple_quotes(self):
        assert _escape_identifier('a"b"c') == 'a""b""c'

    def test_empty_string(self):
        with pytest.raises(ValueError):
            _escape_identifier("")

    def test_semicolon_untouched(self):
        """Semicolons are harmless inside double-quoted identifiers."""
        assert _escape_identifier("col;DROP") == "col;DROP"


class TestEscapeLiteral:
    """Unit tests for the _escape_literal module-level helper."""

    def test_none_returns_null(self):
        assert _escape_literal(None) == "NULL"

    def test_bool_true(self):
        assert _escape_literal(True) == "TRUE"

    def test_bool_false(self):
        assert _escape_literal(False) == "FALSE"

    def test_integer(self):
        assert _escape_literal(42) == "42"

    def test_float(self):
        assert _escape_literal(3.14) == "3.14"

    def test_plain_string(self):
        assert _escape_literal("hello") == "'hello'"

    def test_single_quote_doubled(self):
        assert _escape_literal("O'Brien") == "'O''Brien'"

    def test_nul_byte_stripped(self):
        result = _escape_literal("a\x00b")
        assert "\x00" not in result
        assert result == "'ab'"

    def test_injection_payload(self):
        result = _escape_literal("'; DROP TABLE users; --")
        assert result == "'''; DROP TABLE users; --'"


class TestEscapeSqlValueNulByte:
    """_escape_sql_value should now strip NUL bytes."""

    @pytest.fixture
    def fetcher(self):
        return _make_fetcher()

    def test_nul_byte_stripped(self, fetcher):
        result = fetcher._escape_sql_value("a\x00b")
        assert "\x00" not in result
        assert result == "'ab'"


class TestBuildWhereClauseColumnInjection:
    """Column name injection in _build_where_clause (both modes)."""

    @pytest.fixture
    def fetcher(self):
        return _make_fetcher(columns=["id", "name", "status"])

    def test_column_with_double_quote_escaped_datum(self, fetcher):
        """Column name with embedded " must be escaped for f-string SQL."""
        params = QueryParams(filters={'col"injection': "safe_value"})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        # The double-quote inside the column name must be doubled
        assert 'col""injection' in clause
        assert 'col"injection' not in clause.replace('col""injection', '')

    def test_column_with_double_quote_escaped_parameterized(self, fetcher):
        """Column name with embedded " must be escaped even in parameterized mode."""
        params = QueryParams(filters={'col"injection': "safe_value"})
        clause, sql_params = fetcher._build_where_clause(params, use_params=True)
        assert 'col""injection' in clause

    def test_search_column_escaped(self, fetcher):
        """Search term columns must be escaped."""
        params = QueryParams(search_term="test", search_column="all")
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        # Normal columns should appear as-is (no quotes in name)
        assert '"id"' in clause or '"name"' in clause

    def test_operator_not_empty_column_escaped_datum(self, fetcher):
        params = QueryParams(filters={'col"x': {"op": "not_empty", "value": True}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert 'col""x' in clause

    def test_operator_regex_column_escaped_datum(self, fetcher):
        params = QueryParams(filters={'col"x': {"op": "regex", "value": ".*test.*"}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert 'col""x' in clause

    def test_operator_between_column_escaped(self, fetcher):
        params = QueryParams(filters={'col"x': {"op": "between", "value": ["1", "10"]}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert 'col""x' in clause

    def test_operator_in_column_escaped(self, fetcher):
        params = QueryParams(filters={'col"x': {"op": "in", "value": ["a", "b"]}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert 'col""x' in clause

    def test_operator_not_in_column_escaped(self, fetcher):
        params = QueryParams(filters={'col"x': {"op": "not_in", "value": ["a"]}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert 'col""x' in clause

    def test_operator_contains_column_escaped(self, fetcher):
        params = QueryParams(filters={'col"x': {"op": "contains", "value": "test"}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert 'col""x' in clause

    def test_operator_not_contains_column_escaped(self, fetcher):
        params = QueryParams(filters={'col"x': {"op": "not_contains", "value": "test"}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert 'col""x' in clause

    def test_operator_gt_column_escaped(self, fetcher):
        params = QueryParams(filters={'col"x': {"op": "gt", "value": "5"}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert 'col""x' in clause

    def test_operator_last_n_days_column_escaped(self, fetcher):
        params = QueryParams(filters={'col"x': {"op": "last_n_days", "value": 7}})
        clause, _ = fetcher._build_where_clause(params, use_params=False)
        assert 'col""x' in clause


class TestBuildStatusFilterClauseWhitelist:
    """_build_status_filter_clause must whitelist status values."""

    @pytest.fixture
    def fetcher(self):
        return _make_fetcher()

    def test_valid_statuses_passed(self, fetcher):
        params = QueryParams(status_filters=["edited", "approved"])
        result = fetcher._build_status_filter_clause(params)
        assert "edited" in result
        assert "approved" in result

    def test_injection_payload_dropped(self, fetcher):
        """Malicious status value must be dropped by the whitelist."""
        params = QueryParams(status_filters=["edited", "') OR 1=1 --"])
        result = fetcher._build_status_filter_clause(params)
        assert "OR 1=1" not in result
        assert "edited" in result

    def test_all_invalid_returns_empty(self, fetcher):
        """If ALL values are invalid, clause is empty (no filter)."""
        params = QueryParams(status_filters=["'; DROP TABLE x; --"])
        result = fetcher._build_status_filter_clause(params)
        assert result == ""

    def test_all_four_statuses_returns_empty(self, fetcher):
        """Full set of statuses -> no filter needed."""
        params = QueryParams(status_filters=["unprocessed", "edited", "approved", "rejected"])
        result = fetcher._build_status_filter_clause(params)
        assert result == ""


class TestBuildModStatusExprEscaping:
    """_build_mod_status_expr must escape status_labels keys and values."""

    def test_label_with_single_quote(self):
        """Status label containing a single quote must be escaped."""
        result = _build_mod_status_expr("status", {"approved": "it's approved"})
        # The quote in "it's approved" must be doubled
        assert "it''s approved" in result
        # Should NOT contain unescaped single-quote in the label
        assert "it's approved" not in result.replace("it''s approved", "")

    def test_key_with_single_quote(self):
        """Internal key with embedded quote gets escaped."""
        result = _build_mod_status_expr("status", {"test'key": "label"})
        assert "test''key" in result

    def test_no_status_column(self):
        result = _build_mod_status_expr(None, {"approved": "Approved"})
        assert result == "COALESCE(ms.mod_type, 'unprocessed')"

    def test_no_labels(self):
        result = _build_mod_status_expr("status", None)
        assert "unprocessed" in result


class TestGetUniqueValuesColumnEscaping:
    """get_unique_values must escape the column identifier."""

    @pytest.fixture
    def fetcher(self):
        mock_client = MagicMock()
        mock_client.execute_sql.return_value = MagicMock(data=[])
        return _make_fetcher(mode="datum", datum_client=mock_client)

    def test_column_with_quote_escaped_in_sql(self, fetcher):
        """Column name with double-quote must be escaped."""
        fetcher.get_unique_values('evil"col')
        sql_sent = fetcher._datum_client.execute_sql.call_args[1]["sql"]
        assert 'evil""col' in sql_sent
        assert '"evil"col"' not in sql_sent  # unescaped form must not appear
