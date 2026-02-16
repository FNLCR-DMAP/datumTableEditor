"""
Tests for SqlIdentifier, SqlTableName, SqlLiteral type-safe SQL wrappers.

These types replace the old manual _escape_identifier / _escape_literal / _format_table_name
pattern.  If __str__() produces the correct SQL fragment, all interpolation sites are safe.
"""

import pytest
from decimal import Decimal
from src.config.sql_types import (
    SqlIdentifier,
    SqlTableName,
    SqlLiteral,
    build_pk_json_expr,
    build_pk_array,
)


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  SqlIdentifier                                                        ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestSqlIdentifier:
    """Type-safe column/schema identifier quoting."""

    def test_simple_name(self):
        assert str(SqlIdentifier("name")) == '"name"'

    def test_str_includes_outer_quotes(self):
        """__str__ produces the final SQL fragment with double-quotes."""
        assert f'SELECT {SqlIdentifier("col")} FROM t' == 'SELECT "col" FROM t'

    def test_embedded_double_quote_doubled(self):
        assert str(SqlIdentifier('evil"name')) == '"evil""name"'

    def test_escaped_property_without_outer_quotes(self):
        """The .escaped property returns the inner text only."""
        ident = SqlIdentifier('col"x')
        assert ident.escaped == 'col""x'

    def test_raw_property(self):
        ident = SqlIdentifier("my_col")
        assert ident.raw == "my_col"

    def test_nul_byte_stripped(self):
        ident = SqlIdentifier("a\x00b")
        assert "\x00" not in str(ident)
        assert str(ident) == '"ab"'

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            SqlIdentifier("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            SqlIdentifier("   ")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            SqlIdentifier(None)

    def test_repr(self):
        assert repr(SqlIdentifier("col")) == "SqlIdentifier('col')"

    def test_as_literal_key(self):
        """as_literal_key() returns a SqlLiteral version for jsonb_build_object keys."""
        ident = SqlIdentifier("pk_col")
        lit = ident.as_literal_key()
        assert isinstance(lit, SqlLiteral)
        assert str(lit) == "'pk_col'"

    def test_injection_via_double_quote_breakout(self):
        """Embedded " cannot break out of the identifier quoting."""
        ident = SqlIdentifier('" OR 1=1 --')
        result = str(ident)
        # The " is doubled, so it stays inside the identifier
        assert result == '""" OR 1=1 --"'

    def test_semicolon_in_name(self):
        ident = SqlIdentifier("col; DROP TABLE")
        assert str(ident) == '"col; DROP TABLE"'


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  SqlTableName                                                         ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestSqlTableName:
    """Schema-qualified table name quoting."""

    def test_simple_name(self):
        assert str(SqlTableName("users")) == '"users"'

    def test_schema_qualified(self):
        assert str(SqlTableName("public.users")) == '"public"."users"'

    def test_three_part_name(self):
        assert str(SqlTableName("cat.schema.table")) == '"cat"."schema"."table"'

    def test_embedded_double_quote(self):
        result = str(SqlTableName('evil"name'))
        assert result == '"evil""name"'

    def test_schema_with_embedded_quote(self):
        result = str(SqlTableName('sch"ema.tab"le'))
        assert result == '"sch""ema"."tab""le"'

    def test_nul_byte_stripped(self):
        result = str(SqlTableName("a\x00b.c\x00d"))
        assert "\x00" not in result
        assert result == '"ab"."cd"'

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            SqlTableName("")

    def test_repr(self):
        assert repr(SqlTableName("public.t")) == "SqlTableName('public.t')"

    def test_raw_property(self):
        assert SqlTableName("schema.table").raw == "schema.table"

    def test_semicolon_in_name(self):
        result = str(SqlTableName("schema;DROP TABLE x"))
        assert result == '"schema;DROP TABLE x"'

    def test_f_string_interpolation(self):
        """Verify it works naturally in f-strings."""
        sql = f"SELECT * FROM {SqlTableName('epitopes.data')}"
        assert sql == 'SELECT * FROM "epitopes"."data"'


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  SqlLiteral                                                           ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestSqlLiteral:
    """Type-safe SQL value literal escaping."""

    # -- None / bool / numeric ------------------------------------------------

    def test_none_returns_null(self):
        assert str(SqlLiteral(None)) == "NULL"

    def test_bool_true(self):
        assert str(SqlLiteral(True)) == "TRUE"

    def test_bool_false(self):
        assert str(SqlLiteral(False)) == "FALSE"

    def test_int(self):
        assert str(SqlLiteral(42)) == "42"

    def test_float(self):
        assert str(SqlLiteral(3.14)) == "3.14"

    def test_zero(self):
        assert str(SqlLiteral(0)) == "0"

    def test_negative(self):
        assert str(SqlLiteral(-1)) == "-1"

    def test_float_inf_raises(self):
        with pytest.raises(ValueError, match="inf/nan"):
            SqlLiteral(float("inf"))

    def test_float_neg_inf_raises(self):
        with pytest.raises(ValueError, match="inf/nan"):
            SqlLiteral(float("-inf"))

    def test_float_nan_raises(self):
        with pytest.raises(ValueError, match="inf/nan"):
            SqlLiteral(float("nan"))

    # -- String escaping ------------------------------------------------------

    def test_plain_string(self):
        assert str(SqlLiteral("hello")) == "'hello'"

    def test_single_quote_doubled(self):
        assert str(SqlLiteral("O'Brien")) == "'O''Brien'"

    def test_double_single_quote(self):
        assert str(SqlLiteral("it''s")) == "'it''''s'"

    def test_empty_string(self):
        assert str(SqlLiteral("")) == "''"

    def test_nul_byte_stripped(self):
        result = str(SqlLiteral("a\x00b"))
        assert "\x00" not in result
        assert result == "'ab'"

    def test_newline_preserved(self):
        assert str(SqlLiteral("line1\nline2")) == "'line1\nline2'"

    def test_backslash_preserved(self):
        """PostgreSQL standard_conforming_strings=on treats \\ as literal."""
        assert str(SqlLiteral("back\\slash")) == "'back\\slash'"

    # -- Injection payloads ---------------------------------------------------

    def test_classic_injection(self):
        result = str(SqlLiteral("'; DROP TABLE users; --"))
        assert result == "'''; DROP TABLE users; --'"
        assert "''" in result  # The dangerous ' is doubled

    def test_unicode_injection(self):
        val = "val\u0027; DROP TABLE x; --"  # \u0027 is '
        result = str(SqlLiteral(val))
        assert "''" in result

    def test_multi_quote_injection(self):
        result = str(SqlLiteral("'''"))
        assert result == "''''''''"  # 3 quotes → each doubled → 6 inside outer quotes

    # -- repr -----------------------------------------------------------------

    def test_repr(self):
        assert repr(SqlLiteral("hi")) == "SqlLiteral('hi')"
        assert repr(SqlLiteral(None)) == "SqlLiteral(None)"

    # -- f-string interpolation -----------------------------------------------

    def test_f_string_where_clause(self):
        sql = f"WHERE name = {SqlLiteral('Alice')}"
        assert sql == "WHERE name = 'Alice'"

    def test_f_string_null(self):
        sql = f"SET col = {SqlLiteral(None)}"
        assert sql == "SET col = NULL"

    # -- Decimal support (Finding #6) -----------------------------------------

    def test_decimal_numeric(self):
        assert str(SqlLiteral(Decimal("3.14"))) == "3.14"

    def test_decimal_integer(self):
        assert str(SqlLiteral(Decimal("42"))) == "42"

    def test_decimal_negative(self):
        assert str(SqlLiteral(Decimal("-9.99"))) == "-9.99"

    def test_decimal_inf_raises(self):
        with pytest.raises(ValueError, match="inf/nan"):
            SqlLiteral(Decimal("Infinity"))

    def test_decimal_nan_raises(self):
        with pytest.raises(ValueError, match="inf/nan"):
            SqlLiteral(Decimal("NaN"))

    # -- Type rejection (Finding #8) ------------------------------------------

    def test_list_rejected(self):
        with pytest.raises(TypeError, match="list"):
            SqlLiteral([1, 2, 3])

    def test_dict_rejected(self):
        with pytest.raises(TypeError, match="dict"):
            SqlLiteral({"key": "value"})

    def test_bytes_rejected(self):
        with pytest.raises(TypeError, match="bytes"):
            SqlLiteral(b"raw bytes")


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  build_pk_json_expr                                                   ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestBuildPkJsonExpr:
    """The centralized jsonb_build_object helper."""

    def test_single_pk(self):
        result = build_pk_json_expr(["id"])
        assert result == "jsonb_build_object('id', d.\"id\"::text)"

    def test_composite_pk(self):
        result = build_pk_json_expr(["schema", "table_id"])
        assert "jsonb_build_object(" in result
        assert "'schema', d.\"schema\"::text" in result
        assert "'table_id', d.\"table_id\"::text" in result

    def test_pk_with_quote(self):
        """PK column name with embedded quote must be escaped in both key and identifier."""
        result = build_pk_json_expr(['col"x'])
        assert "'col''x'" in result or "'col\"x'" in result  # key is a SqlLiteral
        assert '"col""x"' in result  # identifier has doubled "

    def test_empty_pk_list(self):
        """Empty PK list raises ValueError to prevent vacuous matches."""
        with pytest.raises(ValueError, match="at least one PK column"):
            build_pk_json_expr([])


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  build_pk_array                                                       ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestBuildPkArray:
    """The centralized ARRAY[...::jsonb] builder."""

    def test_single_pk(self):
        result = build_pk_array(['{"id": 1}'])
        assert result == "ARRAY[''{\"id\": 1}''::jsonb]" or "ARRAY[" in result
        # Just verify structure
        assert result.startswith("ARRAY[")
        assert result.endswith("]")
        assert "::jsonb" in result

    def test_multiple_pks(self):
        result = build_pk_array(['{"id": 1}', '{"id": 2}'])
        assert result.count("::jsonb") == 2

    def test_pk_with_single_quote(self):
        """A PK JSON string containing a quote must be properly escaped."""
        result = build_pk_array(["{'name': \"O'Brien\"}"])
        assert "''" in result  # The embedded ' must be doubled

    def test_empty_list(self):
        result = build_pk_array([])
        assert result == "ARRAY[]"


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  Backward compatibility                                               ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestBackwardCompat:
    """Verify the old function wrappers still work."""

    def test_format_table_name_compat(self):
        from src.config.config_instance import _format_table_name
        assert _format_table_name("public.users") == '"public"."users"'

    def test_escape_identifier_compat(self):
        from src.config.config_instance import _escape_identifier
        assert _escape_identifier('col"x') == 'col""x'

    def test_escape_literal_compat(self):
        from src.config.config_instance import _escape_literal
        assert _escape_literal("O'Brien") == "'O''Brien'"
        assert _escape_literal(None) == "NULL"
        assert _escape_literal(True) == "TRUE"
        assert _escape_literal(42) == "42"

    def test_escape_sql_value_compat(self):
        """DataFetcher._escape_sql_value now delegates to SqlLiteral."""
        from src.config.config_instance import DataFetcher
        from unittest.mock import MagicMock
        fetcher = object.__new__(DataFetcher)
        fetcher._columns = []
        fetcher._total_count = 0
        fetcher._engine = None
        fetcher._datum_client = None
        fetcher.app_config = MagicMock()
        
        assert fetcher._escape_sql_value(None) == "NULL"
        assert fetcher._escape_sql_value("O'Brien") == "'O''Brien'"
        assert fetcher._escape_sql_value(42) == "42"
        assert fetcher._escape_sql_value(True) == "TRUE"
