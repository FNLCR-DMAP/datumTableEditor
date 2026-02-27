"""
Tests for database query builder.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestFilterCondition:
    """Tests for FilterCondition class."""
    
    def test_equals_operator(self):
        """Test equals operator SQL generation."""
        from src.db.query_builder import FilterCondition
        
        f = FilterCondition(column="Status", operator="=", value="approved")
        sql, params = f.to_sql("p")
        
        assert '"Status" =' in sql
        assert ":p_Status" in sql
        assert params["p_Status"] == "approved"
    
    def test_not_equals_operator(self):
        """Test not equals operator."""
        from src.db.query_builder import FilterCondition
        
        f = FilterCondition(column="Status", operator="!=", value="rejected")
        sql, params = f.to_sql("p")
        
        assert '"Status" !=' in sql
        assert params["p_Status"] == "rejected"
    
    def test_greater_than_operator(self):
        """Test greater than operator."""
        from src.db.query_builder import FilterCondition
        
        f = FilterCondition(column="Age", operator=">", value=18)
        sql, params = f.to_sql("p")
        
        assert '"Age" >' in sql
        assert params["p_Age"] == 18
    
    def test_less_than_operator(self):
        """Test less than operator."""
        from src.db.query_builder import FilterCondition
        
        f = FilterCondition(column="Score", operator="<", value=100)
        sql, params = f.to_sql("p")
        
        assert '"Score" <' in sql
    
    def test_like_operator(self):
        """Test LIKE operator with wildcards."""
        from src.db.query_builder import FilterCondition
        
        f = FilterCondition(column="Name", operator="LIKE", value="John")
        sql, params = f.to_sql("p")
        
        assert '"Name" LIKE' in sql
        assert params["p_Name"] == "%John%"
    
    def test_ilike_operator(self):
        """Test ILIKE operator (case-insensitive)."""
        from src.db.query_builder import FilterCondition
        
        f = FilterCondition(column="Name", operator="ILIKE", value="john")
        sql, params = f.to_sql("p")
        
        assert '"Name" ILIKE' in sql
        assert params["p_Name"] == "%john%"
    
    def test_in_operator_with_list(self):
        """Test IN operator with list of values."""
        from src.db.query_builder import FilterCondition
        
        f = FilterCondition(column="Status", operator="IN", value=["approved", "edited"])
        sql, params = f.to_sql("p")
        
        assert '"Status" IN' in sql
        assert ":p_Status_0" in sql
        assert ":p_Status_1" in sql
        assert params["p_Status_0"] == "approved"
        assert params["p_Status_1"] == "edited"
    
    def test_not_in_operator(self):
        """Test NOT IN operator."""
        from src.db.query_builder import FilterCondition
        
        f = FilterCondition(column="Status", operator="NOT IN", value=["rejected"])
        sql, params = f.to_sql("p")
        
        assert '"Status" NOT IN' in sql
    
    def test_is_null_operator(self):
        """Test IS NULL operator (no value needed)."""
        from src.db.query_builder import FilterCondition
        
        f = FilterCondition(column="Notes", operator="IS NULL")
        sql, params = f.to_sql("p")
        
        assert '"Notes" IS NULL' in sql
        assert params == {}
    
    def test_is_not_null_operator(self):
        """Test IS NOT NULL operator."""
        from src.db.query_builder import FilterCondition
        
        f = FilterCondition(column="Notes", operator="IS NOT NULL")
        sql, params = f.to_sql("p")
        
        assert '"Notes" IS NOT NULL' in sql
        assert params == {}


class TestSortConfig:
    """Tests for SortConfig class."""
    
    def test_ascending_sort(self):
        """Test ascending sort SQL."""
        from src.db.query_builder import SortConfig
        
        s = SortConfig(column="Name", ascending=True)
        sql = s.to_sql()
        
        assert '"Name" ASC' in sql
    
    def test_descending_sort(self):
        """Test descending sort SQL."""
        from src.db.query_builder import SortConfig
        
        s = SortConfig(column="Date", ascending=False)
        sql = s.to_sql()
        
        assert '"Date" DESC' in sql


class TestQueryContext:
    """Tests for QueryContext class."""
    
    def test_empty_context_hash(self):
        """Empty context should generate consistent hash."""
        from src.db.query_builder import QueryContext
        
        ctx1 = QueryContext()
        ctx2 = QueryContext()
        
        assert ctx1.get_hash() == ctx2.get_hash()
    
    def test_different_filters_different_hash(self):
        """Different filters should produce different hashes."""
        from src.db.query_builder import QueryContext, FilterCondition
        
        ctx1 = QueryContext(filters=[FilterCondition("A", "=", "1")])
        ctx2 = QueryContext(filters=[FilterCondition("A", "=", "2")])
        
        assert ctx1.get_hash() != ctx2.get_hash()
    
    def test_same_filters_same_hash(self):
        """Same filters should produce same hash."""
        from src.db.query_builder import QueryContext, FilterCondition
        
        ctx1 = QueryContext(filters=[FilterCondition("A", "=", "1")])
        ctx2 = QueryContext(filters=[FilterCondition("A", "=", "1")])
        
        assert ctx1.get_hash() == ctx2.get_hash()
    
    def test_context_equality(self):
        """Test context equality comparison."""
        from src.db.query_builder import QueryContext, FilterCondition
        
        ctx1 = QueryContext(filters=[FilterCondition("A", "=", "1")])
        ctx2 = QueryContext(filters=[FilterCondition("A", "=", "1")])
        
        assert ctx1 == ctx2
    
    def test_context_inequality_non_context(self):
        """Comparing to non-context should return False."""
        from src.db.query_builder import QueryContext
        
        ctx = QueryContext()
        
        assert ctx != "not a context"
        assert ctx != 123


class TestQueryBuilder:
    """Tests for QueryBuilder class."""
    
    @pytest.fixture
    def builder(self):
        from src.db.query_builder import QueryBuilder
        return QueryBuilder(
            data_table="test_table",
            mods_table="test_mods",
            primary_key=["id"],
            status_column="Status"
        )
    
    def test_simple_select_query(self, builder):
        """Test basic select query generation."""
        sql, params = builder.build_select_query(page=1, limit=25)
        
        assert "SELECT" in sql
        assert "test_table" in sql
        assert "LIMIT" in sql
        assert params["limit"] == 25
        assert params["offset"] == 0
    
    def test_select_with_filters(self, builder):
        """Test select with filter conditions."""
        from src.db.query_builder import FilterCondition
        
        filters = [FilterCondition("Status", "=", "approved")]
        sql, params = builder.build_select_query(filters=filters, page=1)
        
        assert "WHERE" in sql
        assert '"Status"' in sql
    
    def test_select_with_sort(self, builder):
        """Test select with sort configuration."""
        from src.db.query_builder import SortConfig
        
        sort = SortConfig("Name", ascending=True)
        sql, params = builder.build_select_query(sort=sort, page=1)
        
        assert "ORDER BY" in sql
        assert '"Name" ASC' in sql
    
    def test_pagination_offset_calculation(self, builder):
        """Test pagination offset calculation."""
        sql, params = builder.build_select_query(page=3, limit=10)
        
        assert params["offset"] == 20  # (3-1) * 10
        assert params["limit"] == 10
    
    def test_limit_capped_at_max(self, builder):
        """Test that limit is capped at MAX_ROWS_PER_PAGE (default 100)."""
        sql, params = builder.build_select_query(page=1, limit=500)
        
        assert params["limit"] == 100  # default MAX_ROWS_PER_PAGE

    def test_limit_capped_at_custom_max(self):
        """Test that limit honours a custom max_rows_per_page."""
        from src.db.query_builder import QueryBuilder
        custom_builder = QueryBuilder("t", max_rows_per_page=500)
        sql, params = custom_builder.build_select_query(page=1, limit=1000)
        assert params["limit"] == 500

        # Within the custom cap
        _, p2 = custom_builder.build_select_query(page=1, limit=300)
        assert p2["limit"] == 300

    def test_custom_max_does_not_mutate_class_default(self):
        """Instance-level max_rows_per_page must not leak to the class."""
        from src.db.query_builder import QueryBuilder
        custom = QueryBuilder("t", max_rows_per_page=500)
        default = QueryBuilder("t")
        # Custom instance has 500
        assert custom.MAX_ROWS_PER_PAGE == 500
        # Default instance still has the class-level 100
        assert default.MAX_ROWS_PER_PAGE == 100
        # Class attribute itself is untouched
        assert QueryBuilder.MAX_ROWS_PER_PAGE == 100
    
    def test_count_query(self, builder):
        """Test count query generation."""
        sql, params = builder.build_count_query()
        
        assert "SELECT COUNT(*)" in sql
        assert "test_table" in sql
    
    def test_count_query_with_filters(self, builder):
        """Test count query with filters."""
        from src.db.query_builder import FilterCondition
        
        filters = [FilterCondition("Status", "IN", ["approved", "edited"])]
        sql, params = builder.build_count_query(filters=filters)
        
        assert "WHERE" in sql
        assert "COUNT(*)" in sql
    
    def test_default_pk_sort(self, builder):
        """Test default sorting by primary key when no sort specified."""
        sql, params = builder.build_select_query(page=1)
        
        assert "ORDER BY" in sql
        assert '"id" ASC' in sql
    
    def test_select_without_mods_status(self, builder):
        """Test select without modifications status."""
        sql, params = builder.build_select_query(page=1, include_mods_status=False)
        
        assert "SELECT *" in sql
        assert "_mod_status" not in sql


class TestParseFiltersFromList:
    """Tests for parse_filters_from_list function."""
    
    def test_parse_simple_filter(self):
        """Test parsing simple filter dict."""
        from src.db.query_builder import parse_filters_from_list
        
        filters = [{"column": "Status", "operator": "=", "value": "approved"}]
        result = parse_filters_from_list(filters)
        
        assert len(result) == 1
        assert result[0].column == "Status"
        assert result[0].operator == "="
        assert result[0].value == "approved"
    
    def test_parse_multiple_filters(self):
        """Test parsing multiple filters."""
        from src.db.query_builder import parse_filters_from_list
        
        filters = [
            {"column": "Status", "operator": "=", "value": "approved"},
            {"column": "Gene", "operator": "LIKE", "value": "TP53"}
        ]
        result = parse_filters_from_list(filters)
        
        assert len(result) == 2
    
    def test_parse_empty_list(self):
        """Test parsing empty filter list."""
        from src.db.query_builder import parse_filters_from_list
        
        result = parse_filters_from_list([])
        
        assert result == []
    
    def test_parse_none_raises_error(self):
        """Test parsing None raises TypeError (function expects list)."""
        from src.db.query_builder import parse_filters_from_list
        
        with pytest.raises(TypeError):
            parse_filters_from_list(None)


class TestQuoteIdentifier:
    """Tests for quote_identifier function."""

    def test_simple_name(self):
        """Test quoting a simple identifier."""
        from src.db.query_builder import quote_identifier

        assert quote_identifier("users") == '"users"'

    def test_schema_qualified(self):
        """Test quoting a schema-qualified identifier."""
        from src.db.query_builder import quote_identifier

        assert quote_identifier("public.my_table") == '"public"."my_table"'

    def test_three_parts(self):
        """Test quoting a three-part identifier."""
        from src.db.query_builder import quote_identifier

        assert quote_identifier("a.b.c") == '"a"."b"."c"'

    def test_single_char(self):
        """Test quoting a single character identifier."""
        from src.db.query_builder import quote_identifier

        assert quote_identifier("x") == '"x"'


class TestBuildSearchFilter:
    """Tests for build_search_filter function."""

    def test_returns_filter_per_column(self):
        """Should return one FilterCondition per column."""
        from src.db.query_builder import build_search_filter

        result = build_search_filter("test", ["A", "B", "C"])

        assert len(result) == 3
        assert all(f.column in ("A", "B", "C") for f in result)
        assert all(f.value == "test" for f in result)

    def test_default_case_insensitive(self):
        """Default should use ILIKE (case-insensitive)."""
        from src.db.query_builder import build_search_filter

        result = build_search_filter("test", ["Col"])

        assert result[0].operator == "ILIKE"

    def test_case_sensitive(self):
        """Case-sensitive search should use LIKE."""
        from src.db.query_builder import build_search_filter

        result = build_search_filter("test", ["Col"], case_sensitive=True)

        assert result[0].operator == "LIKE"

    def test_empty_columns(self):
        """Empty columns list should return empty result."""
        from src.db.query_builder import build_search_filter

        result = build_search_filter("test", [])

        assert result == []

    def test_search_term_preserved(self):
        """Search term should be passed through unchanged."""
        from src.db.query_builder import build_search_filter

        result = build_search_filter("Hello World", ["Col"])

        assert result[0].value == "Hello World"


class TestParseFilterFromDict:
    """Tests for parse_filter_from_dict function."""

    def test_basic_parse(self):
        """Should parse a basic filter dict."""
        from src.db.query_builder import parse_filter_from_dict

        result = parse_filter_from_dict({"column": "Status", "operator": "=", "value": "active"})

        assert result.column == "Status"
        assert result.operator == "="
        assert result.value == "active"

    def test_default_operator(self):
        """Should default to '=' operator."""
        from src.db.query_builder import parse_filter_from_dict

        result = parse_filter_from_dict({"column": "Status", "value": "active"})

        assert result.operator == "="

    def test_no_value(self):
        """Should handle missing value (None)."""
        from src.db.query_builder import parse_filter_from_dict

        result = parse_filter_from_dict({"column": "Status", "operator": "IS NULL"})

        assert result.value is None
