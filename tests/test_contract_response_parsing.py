"""
Factor 3 Contract Tests: SQL Response → DataFrame

Tests the contract that governs how raw SQL responses (from Datum or
SQLAlchemy) are transformed into the pd.DataFrame that the rendering
layer consumes.

Key invariants verified:
  1. Datum response.data (List[Dict]) → DataFrame preserves column order / values
  2. SQLAlchemy result (fetchall + keys) → DataFrame preserves types / shape
  3. _apply_field_modifications overwrites matching cells in-place
  4. _mod_status column always present in output
  5. Empty response → empty DataFrame (no crash)
  6. PK serialization handles numpy int / NaN / normal values
  7. Field modification ordering (created_at ASC) means last edit wins
"""

import pytest
import json
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import List, Any


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — Mock AppConfig matching the real shape
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class _MockQuery:
    searchable_columns: list = field(default_factory=list)
    default_filters: dict = field(default_factory=dict)


@dataclass
class _MockTable:
    primary_key: List[str] = field(default_factory=lambda: ["id"])


@dataclass
class _MockDB:
    enabled: bool = True
    mode: str = "datum"
    data_table: str = "test_data"
    mods_table: str = "test_mods"
    connection_string: str = ""
    datum_base_url: str = "http://fake"
    datum_token: str = "tok"
    datum_database: str = "db"
    datum_schema: str = "public"
    datum_service_name: str = "svc"
    page_buffer_size: int = 5000
    max_rows: int = 0
    status_column: str = ""
    state_table: str = "test_state"


@dataclass
class _MockAppConfig:
    table: _MockTable = field(default_factory=_MockTable)
    database: _MockDB = field(default_factory=_MockDB)
    query: _MockQuery = field(default_factory=_MockQuery)
    status_labels: dict = field(default_factory=lambda: {
        "unprocessed": "New",
        "edited": "Edited",
        "approved": "Approved",
        "rejected": "Rejected",
    })
    enable_approval_workflow: bool = True


# ═══════════════════════════════════════════════════════════════════════════════
# Datum response → DataFrame
# ═══════════════════════════════════════════════════════════════════════════════


class TestDatumResponseToDataFrame:
    """Contract: pd.DataFrame(response.data) from Datum List[Dict]."""

    def test_simple_dict_list_becomes_dataframe(self):
        """The fundamental Datum→DF conversion."""
        data = [
            {"id": 1, "gene": "BRCA1", "_mod_status": "unprocessed"},
            {"id": 2, "gene": "TP53", "_mod_status": "edited"},
        ]
        df = pd.DataFrame(data)
        assert list(df.columns) == ["id", "gene", "_mod_status"]
        assert len(df) == 2
        assert df.loc[0, "gene"] == "BRCA1"
        assert df.loc[1, "_mod_status"] == "edited"

    def test_empty_data_becomes_empty_dataframe(self):
        """Empty response.data → empty DataFrame (not None, not crash)."""
        df = pd.DataFrame([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_mod_status_column_always_present(self):
        """Every row from the main query must carry _mod_status."""
        data = [{"id": 1, "gene": "X", "_mod_status": "approved"}]
        df = pd.DataFrame(data)
        assert "_mod_status" in df.columns

    def test_column_order_preserved_from_dict_keys(self):
        """DataFrame column order matches key insertion order in dicts."""
        data = [{"z": 1, "a": 2, "m": 3}]
        df = pd.DataFrame(data)
        assert list(df.columns) == ["z", "a", "m"]

    def test_null_values_become_nan(self):
        """JSON null values become NaN in the DataFrame."""
        data = [{"id": 1, "gene": None, "_mod_status": "unprocessed"}]
        df = pd.DataFrame(data)
        assert pd.isna(df.loc[0, "gene"])

    def test_mixed_types_preserved(self):
        """Integers, strings, booleans stay as their Python types."""
        data = [{"int_col": 42, "str_col": "hello", "bool_col": True}]
        df = pd.DataFrame(data)
        assert df.loc[0, "int_col"] == 42
        assert df.loc[0, "str_col"] == "hello"
        assert df.loc[0, "bool_col"] == True  # noqa: E712 — numpy bool


# ═══════════════════════════════════════════════════════════════════════════════
# SQLAlchemy response → DataFrame
# ═══════════════════════════════════════════════════════════════════════════════


class TestSQLAlchemyResponseToDataFrame:
    """Contract: pd.DataFrame(rows, columns=keys) from SQLAlchemy result."""

    def test_tuples_and_keys_become_dataframe(self):
        """result.fetchall() tuples + result.keys() → DataFrame."""
        rows = [(1, "BRCA1", "unprocessed"), (2, "TP53", "edited")]
        columns = ["id", "gene", "_mod_status"]
        df = pd.DataFrame(rows, columns=columns)
        assert list(df.columns) == columns
        assert len(df) == 2
        assert df.loc[0, "gene"] == "BRCA1"

    def test_empty_rows_produce_empty_df_with_columns(self):
        """No rows but valid keys → empty DataFrame with column names."""
        rows = []
        columns = ["id", "gene", "_mod_status"]
        df = pd.DataFrame(rows, columns=columns)
        assert len(df) == 0
        assert list(df.columns) == columns

    def test_column_names_from_keys_not_data(self):
        """Column names come from result.keys(), not from row content."""
        rows = [(1, "X")]
        columns = ["my_id", "my_gene"]
        df = pd.DataFrame(rows, columns=columns)
        assert list(df.columns) == ["my_id", "my_gene"]

    def test_none_in_tuple_becomes_nan(self):
        rows = [(1, None, "unprocessed")]
        columns = ["id", "gene", "_mod_status"]
        df = pd.DataFrame(rows, columns=columns)
        assert pd.isna(df.loc[0, "gene"])


# ═══════════════════════════════════════════════════════════════════════════════
# _apply_field_modifications contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestApplyFieldModifications:
    """
    Contract: _apply_field_modifications overwrites cells in-place
    for any matching field_modification records.
    
    We test the in-memory logic that the DataFetcher._apply_field_modifications
    performs, without calling a real DB. The algorithm is:
    1. Build pk_json → row_index mapping
    2. For each mod: find rows with matching pk, overwrite df[col] = new_value
    """

    @staticmethod
    def _apply_mods(df: pd.DataFrame, mods: list, pk_columns: list) -> pd.DataFrame:
        """
        Replicates the core logic of DataFetcher._apply_field_modifications
        for contract testing without needing a DB connection.
        """
        if df.empty:
            return df

        pk_index = {}
        for idx, row in df.iterrows():
            pk_dict = {pk: row[pk] for pk in pk_columns if pk in df.columns}
            serializable_pk = {}
            for k, v in pk_dict.items():
                if hasattr(v, 'item'):
                    serializable_pk[k] = v.item()
                elif pd.isna(v):
                    serializable_pk[k] = None
                else:
                    serializable_pk[k] = v
            pk_json = json.dumps(serializable_pk, sort_keys=True)
            if pk_json not in pk_index:
                pk_index[pk_json] = []
            pk_index[pk_json].append(idx)

        for mod in mods:
            row_pk = mod["row_pk"]
            if isinstance(row_pk, str):
                row_pk = json.loads(row_pk)
            pk_json = json.dumps(row_pk, sort_keys=True)
            if pk_json in pk_index:
                col = mod["column_name"]
                new_val = mod["new_value"]
                for idx in pk_index[pk_json]:
                    if col in df.columns:
                        df.at[idx, col] = new_val
        return df

    def test_single_cell_overwrite(self):
        """One modification overwrites exactly one cell."""
        df = pd.DataFrame({"id": [1, 2], "gene": ["BRCA1", "TP53"]})
        mods = [{"row_pk": {"id": 1}, "column_name": "gene", "new_value": "BRCA1_edited"}]
        result = self._apply_mods(df, mods, ["id"])
        assert result.loc[0, "gene"] == "BRCA1_edited"
        assert result.loc[1, "gene"] == "TP53"  # untouched

    def test_no_mods_returns_unchanged(self):
        df = pd.DataFrame({"id": [1], "gene": ["BRCA1"]})
        result = self._apply_mods(df, [], ["id"])
        assert result.loc[0, "gene"] == "BRCA1"

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame({"id": [], "gene": []})
        mods = [{"row_pk": {"id": 1}, "column_name": "gene", "new_value": "X"}]
        result = self._apply_mods(df, mods, ["id"])
        assert result.empty

    def test_mod_for_nonexistent_pk_is_ignored(self):
        """Modifications for PKs not in the current data are silently skipped."""
        df = pd.DataFrame({"id": [1], "gene": ["BRCA1"]})
        mods = [{"row_pk": {"id": 999}, "column_name": "gene", "new_value": "ghost"}]
        result = self._apply_mods(df, mods, ["id"])
        assert result.loc[0, "gene"] == "BRCA1"

    def test_mod_for_nonexistent_column_is_ignored(self):
        """Modifications for columns not in the DataFrame are silently skipped."""
        df = pd.DataFrame({"id": [1], "gene": ["BRCA1"]})
        mods = [{"row_pk": {"id": 1}, "column_name": "missing_col", "new_value": "X"}]
        result = self._apply_mods(df, mods, ["id"])
        assert "missing_col" not in result.columns

    def test_multiple_mods_same_cell_last_wins(self):
        """Mods ordered by created_at ASC → last mod wins."""
        df = pd.DataFrame({"id": [1], "gene": ["original"]})
        mods = [
            {"row_pk": {"id": 1}, "column_name": "gene", "new_value": "first_edit"},
            {"row_pk": {"id": 1}, "column_name": "gene", "new_value": "second_edit"},
        ]
        result = self._apply_mods(df, mods, ["id"])
        assert result.loc[0, "gene"] == "second_edit"

    def test_composite_pk(self):
        """Multi-column PKs produce correct JSON for matching."""
        df = pd.DataFrame({
            "org": ["A", "A", "B"],
            "seq": [1, 2, 1],
            "gene": ["X", "Y", "Z"],
        })
        mods = [{"row_pk": {"org": "A", "seq": 1}, "column_name": "gene", "new_value": "X_edited"}]
        result = self._apply_mods(df, mods, ["org", "seq"])
        assert result.loc[0, "gene"] == "X_edited"
        assert result.loc[1, "gene"] == "Y"  # same org, different seq
        assert result.loc[2, "gene"] == "Z"  # different org

    def test_row_pk_as_json_string(self):
        """row_pk can arrive as a JSON string (from Datum) — it gets parsed."""
        df = pd.DataFrame({"id": [1], "gene": ["orig"]})
        mods = [{"row_pk": '{"id": 1}', "column_name": "gene", "new_value": "edited"}]
        result = self._apply_mods(df, mods, ["id"])
        assert result.loc[0, "gene"] == "edited"

    def test_numpy_int_pk_handled(self):
        """numpy int64 PK values are serialized via .item() for matching."""
        df = pd.DataFrame({"id": np.array([1, 2], dtype=np.int64), "gene": ["A", "B"]})
        mods = [{"row_pk": {"id": 1}, "column_name": "gene", "new_value": "A_edited"}]
        result = self._apply_mods(df, mods, ["id"])
        assert result.loc[0, "gene"] == "A_edited"

    def test_nan_pk_serialized_as_null(self):
        """NaN PKs become None in JSON (edge case — shouldn't match normal mods)."""
        df = pd.DataFrame({"id": [np.nan, 2], "gene": ["A", "B"]})
        mods = [{"row_pk": {"id": None}, "column_name": "gene", "new_value": "null_pk_edited"}]
        result = self._apply_mods(df, mods, ["id"])
        assert result.loc[0, "gene"] == "null_pk_edited"
        assert result.loc[1, "gene"] == "B"

    def test_mods_across_multiple_rows(self):
        """Multiple rows each get their own modification."""
        df = pd.DataFrame({"id": [1, 2, 3], "gene": ["A", "B", "C"]})
        mods = [
            {"row_pk": {"id": 1}, "column_name": "gene", "new_value": "A_new"},
            {"row_pk": {"id": 3}, "column_name": "gene", "new_value": "C_new"},
        ]
        result = self._apply_mods(df, mods, ["id"])
        assert result.loc[0, "gene"] == "A_new"
        assert result.loc[1, "gene"] == "B"
        assert result.loc[2, "gene"] == "C_new"

    def test_mods_across_multiple_columns(self):
        """Single row, two different columns modified."""
        df = pd.DataFrame({"id": [1], "gene": ["A"], "status": ["Pending"]})
        mods = [
            {"row_pk": {"id": 1}, "column_name": "gene", "new_value": "A_edit"},
            {"row_pk": {"id": 1}, "column_name": "status", "new_value": "Reviewed"},
        ]
        result = self._apply_mods(df, mods, ["id"])
        assert result.loc[0, "gene"] == "A_edit"
        assert result.loc[0, "status"] == "Reviewed"

    def test_duplicate_pk_rows_both_updated(self):
        """If df has duplicate PKs (shouldn't happen normally), both rows get updated."""
        df = pd.DataFrame({"id": [1, 1], "gene": ["A", "A"]})
        mods = [{"row_pk": {"id": 1}, "column_name": "gene", "new_value": "both_updated"}]
        result = self._apply_mods(df, mods, ["id"])
        assert result.loc[0, "gene"] == "both_updated"
        assert result.loc[1, "gene"] == "both_updated"


# ═══════════════════════════════════════════════════════════════════════════════
# PK Serialization Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestPKSerialization:
    """Contract: PK values are serialized consistently for lookup.
    
    The pk_json key must be identical between:
    - The indexing pass (over DataFrame rows) 
    - The modification pass (over mod dicts)
    This is the core data-integrity contract for field mods.
    """

    @staticmethod
    def serialize_pk(pk_dict: dict) -> str:
        """Mirrors the pk serialization logic in _apply_field_modifications."""
        serializable = {}
        for k, v in pk_dict.items():
            if hasattr(v, 'item'):
                serializable[k] = v.item()
            elif isinstance(v, float) and pd.isna(v):
                serializable[k] = None
            else:
                serializable[k] = v
        return json.dumps(serializable, sort_keys=True)

    def test_string_pk(self):
        assert self.serialize_pk({"id": "PK001"}) == '{"id": "PK001"}'

    def test_int_pk(self):
        assert self.serialize_pk({"id": 42}) == '{"id": 42}'

    def test_numpy_int_pk(self):
        val = np.int64(42)
        assert self.serialize_pk({"id": val}) == '{"id": 42}'

    def test_nan_pk(self):
        assert self.serialize_pk({"id": float("nan")}) == '{"id": null}'

    def test_composite_pk_sorted_keys(self):
        """sort_keys=True ensures consistent JSON regardless of dict order."""
        pk1 = self.serialize_pk({"z_col": "1", "a_col": "2"})
        pk2 = self.serialize_pk({"a_col": "2", "z_col": "1"})
        assert pk1 == pk2

    def test_composite_pk_with_mixed_types(self):
        result = self.serialize_pk({"org": "ACME", "seq": 42})
        parsed = json.loads(result)
        assert parsed == {"org": "ACME", "seq": 42}

    def test_none_pk_value(self):
        assert self.serialize_pk({"id": None}) == '{"id": null}'

    def test_boolean_pk_value(self):
        """Boolean PKs serialize as JSON booleans."""
        result = self.serialize_pk({"flag": True})
        assert json.loads(result) == {"flag": True}

    def test_numpy_float_pk(self):
        val = np.float64(3.14)
        result = self.serialize_pk({"score": val})
        parsed = json.loads(result)
        assert abs(parsed["score"] - 3.14) < 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# End-to-End Response Pipeline Snapshot
# ═══════════════════════════════════════════════════════════════════════════════


class TestResponsePipelineSnapshot:
    """
    Snapshot test: given a typical Datum response + matching mods,
    verify the final DataFrame shape and content exactly.
    """

    def test_full_pipeline_datum_mode(self):
        """Datum response.data → DataFrame → apply_mods → final shape."""
        # Phase 1: response.data → DataFrame
        response_data = [
            {"pk": "PK1", "gene": "BRCA1", "score": 95, "_mod_status": "unprocessed"},
            {"pk": "PK2", "gene": "TP53", "score": 80, "_mod_status": "edited"},
            {"pk": "PK3", "gene": "EGFR", "score": 70, "_mod_status": "approved"},
        ]
        df = pd.DataFrame(response_data)

        # Phase 2: apply_field_modifications
        mods = [
            {"row_pk": {"pk": "PK2"}, "column_name": "gene", "new_value": "TP53_FIXED"},
            {"row_pk": {"pk": "PK3"}, "column_name": "score", "new_value": 99},
        ]
        result = TestApplyFieldModifications._apply_mods(df, mods, ["pk"])

        # Verify final shape
        assert list(result.columns) == ["pk", "gene", "score", "_mod_status"]
        assert len(result) == 3

        # Verify modifications applied
        assert result.loc[0, "gene"] == "BRCA1"      # untouched
        assert result.loc[1, "gene"] == "TP53_FIXED"  # modified
        assert result.loc[2, "score"] == 99            # modified

        # Verify unmodified columns preserved
        assert result.loc[1, "score"] == 80
        assert result.loc[0, "_mod_status"] == "unprocessed"

    def test_full_pipeline_sqla_mode(self):
        """SQLAlchemy result → DataFrame → apply_mods → final shape."""
        rows = [("PK1", "BRCA1", "unprocessed"), ("PK2", "TP53", "edited")]
        columns = ["pk", "gene", "_mod_status"]
        df = pd.DataFrame(rows, columns=columns)

        mods = [{"row_pk": {"pk": "PK1"}, "column_name": "gene", "new_value": "BRCA1_v2"}]
        result = TestApplyFieldModifications._apply_mods(df, mods, ["pk"])

        assert result.loc[0, "gene"] == "BRCA1_v2"
        assert result.loc[1, "gene"] == "TP53"

    def test_empty_response_returns_empty_df(self):
        """Empty response from either mode → empty DataFrame."""
        # Datum mode
        df_datum = pd.DataFrame([])
        assert df_datum.empty

        # SQLAlchemy mode
        df_sqla = pd.DataFrame([], columns=["pk", "gene", "_mod_status"])
        assert df_sqla.empty
        assert list(df_sqla.columns) == ["pk", "gene", "_mod_status"]

    def test_pipeline_with_no_mods_preserves_data(self):
        """No modifications → DataFrame is returned unchanged."""
        data = [{"pk": "PK1", "gene": "BRCA1", "_mod_status": "unprocessed"}]
        df = pd.DataFrame(data)
        result = TestApplyFieldModifications._apply_mods(df.copy(), [], ["pk"])
        pd.testing.assert_frame_equal(result, df)
