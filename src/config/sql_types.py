"""
Type-safe SQL fragment wrappers for Datum mode.

Instead of relying on developers to remember:
    f'"{_escape_identifier(col)}"'
    f"'{val.replace(chr(39), chr(39)*2)}'"

... at every interpolation site, these types enforce escaping at construction:
    f'{SqlIdentifier(col)}'
    f'{SqlLiteral(val)}'

The __str__() of each type produces the final, safely-quoted SQL fragment.
If you see a raw string in an f-string SQL expression, it's a bug.
If you see SqlIdentifier(...) or SqlLiteral(...), it's safe by construction.

Grep audit: `grep -rn 'f".*{' | grep -v SqlIdentifier | grep -v SqlLiteral`
will find any un-wrapped interpolation in SQL strings.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, List


class SqlIdentifier:
    """A SQL identifier (column name, single-part name) that is safely double-quoted.

    Usage in f-strings:
        f'SELECT {SqlIdentifier(col)} FROM ...'
        # produces: SELECT "my_column" FROM ...

        f'ORDER BY {SqlIdentifier(col)} ASC'
        # produces: ORDER BY "my_column" ASC

    Security:
        - Embedded " are doubled ("" in PostgreSQL identifier quoting)
        - NUL bytes are stripped
        - Empty strings raise ValueError
    """

    __slots__ = ("_raw", "_escaped")

    def __init__(self, name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"SqlIdentifier requires a non-empty string, got {name!r}")
        self._raw = name
        # Strip NUL bytes, double embedded double-quotes
        self._escaped = name.replace("\x00", "").replace('"', '""')

    def __str__(self) -> str:
        """Produces: "escaped_name" (with outer double-quotes)."""
        return f'"{self._escaped}"'

    def __repr__(self) -> str:
        return f"SqlIdentifier({self._raw!r})"

    @property
    def raw(self) -> str:
        """The original unescaped name (for dict lookups, etc.)."""
        return self._raw

    @property
    def escaped(self) -> str:
        """The escaped name WITHOUT outer quotes (for embedding in composite expressions)."""
        return self._escaped

    def as_literal_key(self) -> "SqlLiteral":
        """Return the identifier as a single-quoted SQL literal (for jsonb_build_object keys)."""
        return SqlLiteral(self._raw)


class SqlTableName:
    """A schema-qualified table name with proper PostgreSQL quoting.

    Usage in f-strings:
        f'SELECT * FROM {SqlTableName("epitopes.epitopes_data")}'
        # produces: SELECT * FROM "epitopes"."epitopes_data"

    Security:
        - Splits on '.' and quotes each part separately
        - Embedded " in each part are doubled
        - NUL bytes are stripped
    """

    __slots__ = ("_raw", "_parts")

    def __init__(self, table_name: str) -> None:
        if not isinstance(table_name, str) or not table_name.strip():
            raise ValueError(f"SqlTableName requires a non-empty string, got {table_name!r}")
        self._raw = table_name
        self._parts = table_name.replace("\x00", "").split(".")

    def __str__(self) -> str:
        """Produces: "schema"."table" (each part double-quoted with escaping)."""
        return ".".join(f'"{part.replace(chr(34), chr(34)*2)}"' for part in self._parts)

    def __repr__(self) -> str:
        return f"SqlTableName({self._raw!r})"

    @property
    def raw(self) -> str:
        return self._raw


class SqlLiteral:
    """A SQL literal value that is safely single-quoted (or NULL/TRUE/FALSE/number).

    Usage in f-strings:
        f'WHERE name = {SqlLiteral(user_input)}'
        # produces: WHERE name = 'escaped_value'

        f'WHERE id = {SqlLiteral(42)}'
        # produces: WHERE id = 42

        f'WHERE x = {SqlLiteral(None)}'
        # produces: WHERE x = NULL

    Security:
        - None  → NULL (no quotes)
        - bool  → TRUE / FALSE (no quotes)
        - int/float → str(value) (no quotes)
        - str   → single-quoted with ' doubled and NUL bytes stripped
    """

    __slots__ = ("_value", "_sql")

    def __init__(self, value: Any) -> None:
        self._value = value
        self._sql = self._escape(value)

    @staticmethod
    def _escape(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, Decimal):
            # Decimal must be checked before int/float because Decimal is not a subclass
            if value.is_infinite() or value.is_nan():
                raise ValueError(
                    f"SqlLiteral does not accept inf/nan Decimals (got {value!r}). "
                    f"Use 'Infinity'::double precision or 'NaN'::double precision explicitly."
                )
            return str(value)
        if isinstance(value, (int, float)):
            if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
                raise ValueError(
                    f"SqlLiteral does not accept inf/nan floats (got {value!r}). "
                    f"Use 'Infinity'::double precision or 'NaN'::double precision explicitly."
                )
            return str(value)
        if isinstance(value, str):
            # Strip NUL bytes and escape single quotes by doubling
            s = value.replace("\x00", "").replace("'", "''")
            return f"'{s}'"
        # Reject types that would silently produce garbage SQL
        raise TypeError(
            f"SqlLiteral does not accept {type(value).__name__} (got {value!r}). "
            f"Convert to str, int, float, bool, or None first."
        )

    def __str__(self) -> str:
        return self._sql

    def __repr__(self) -> str:
        return f"SqlLiteral({self._value!r})"


def build_pk_json_expr(pk_columns: List[str]) -> str:
    """Build the jsonb_build_object(...) expression for PK matching.

    This is the most complex SQL fragment — it appears in 6+ places.
    Centralizing it here ensures consistent, type-safe construction.

    Produces:
        jsonb_build_object('pk1', d."pk1"::text, 'pk2', d."pk2"::text)

    Raises:
        ValueError: If pk_columns is empty (would produce a vacuous match).
    """
    if not pk_columns:
        raise ValueError("build_pk_json_expr requires at least one PK column")
    parts = []
    for pk in pk_columns:
        ident = SqlIdentifier(pk)
        # The key is a single-quoted string literal, the value is a column reference
        parts.append(f"{ident.as_literal_key()}, d.{ident}::text")
    return "jsonb_build_object(" + ", ".join(parts) + ")"


def build_pk_array(pk_json_values: List[str]) -> str:
    """Build an ARRAY[...::jsonb] expression from serialized PK JSON strings.

    Used in _apply_field_modifications and _apply_field_modifications_datum
    to create the ANY(...) filter for batch PK lookups.
    """
    elements = []
    for pv in pk_json_values:
        elements.append(f"{SqlLiteral(pv)}::jsonb")
    return "ARRAY[" + ",".join(elements) + "]"
