"""
Tests for session book - in-memory data structure for local-first row ordering.
"""
import pytest
import pandas as pd
from datetime import datetime


class TestRowEntry:
    """Tests for RowEntry dataclass."""
    
    def test_create_row_entry(self):
        """Test creating a row entry."""
        from src.db.session_book import RowEntry
        
        entry = RowEntry(
            pk_values={"id": 1},
            data={"id": 1, "name": "Test"},
            page_number=1,
            load_order=0
        )
        
        assert entry.pk_values == {"id": 1}
        assert entry.page_number == 1
    
    def test_get_pk_tuple(self):
        """Test getting hashable PK tuple."""
        from src.db.session_book import RowEntry
        
        entry = RowEntry(
            pk_values={"col_a": "A", "col_b": "B"},
            data={},
            page_number=1,
            load_order=0
        )
        
        pk_tuple = entry.get_pk_tuple()
        
        # Should be sorted and hashable
        assert isinstance(pk_tuple, tuple)
        assert ("col_a", "A") in pk_tuple
        assert ("col_b", "B") in pk_tuple
    
    def test_get_pk_json(self):
        """Test getting JSON string of PK."""
        from src.db.session_book import RowEntry
        import json
        
        entry = RowEntry(
            pk_values={"id": 123},
            data={},
            page_number=1,
            load_order=0
        )
        
        pk_json = entry.get_pk_json()
        parsed = json.loads(pk_json)
        
        assert parsed == {"id": 123}


class TestPageInfo:
    """Tests for PageInfo dataclass."""
    
    def test_create_page_info(self):
        """Test creating page info."""
        from src.db.session_book import PageInfo
        
        info = PageInfo(page_number=1, row_count=25, has_more=True)
        
        assert info.page_number == 1
        assert info.row_count == 25
        assert info.has_more is True


class TestSessionBook:
    """Tests for SessionBook class."""
    
    @pytest.fixture
    def book(self):
        from src.db.session_book import SessionBook
        return SessionBook(primary_key=["id"])
    
    @pytest.fixture
    def multi_pk_book(self):
        from src.db.session_book import SessionBook
        return SessionBook(primary_key=["patient_id", "variant_id"])
    
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "id": [1, 2, 3],
            "name": ["A", "B", "C"],
            "value": [10, 20, 30]
        })
    
    def test_initial_state(self, book):
        """Test initial empty state."""
        assert book.row_count == 0
        assert book.page_count == 0
        assert book.known_pks == set()
    
    def test_set_context_new(self, book):
        """Setting new context should return True."""
        changed = book.set_context("hash123")
        
        assert changed is True
    
    def test_set_context_same(self, book):
        """Setting same context should return False."""
        book.set_context("hash123")
        changed = book.set_context("hash123")
        
        assert changed is False
    
    def test_set_context_different_clears_book(self, book, sample_df):
        """Changing context should clear the book."""
        book.set_context("hash1")
        book.append_page(sample_df, page_number=1)
        
        assert book.row_count == 3
        
        changed = book.set_context("hash2")
        
        assert changed is True
        assert book.row_count == 0
    
    def test_clear(self, book, sample_df):
        """Test clearing the book."""
        book.append_page(sample_df, page_number=1)
        book.clear()
        
        assert book.row_count == 0
        assert book.page_count == 0
    
    def test_append_page(self, book, sample_df):
        """Test appending a page of data."""
        new_count = book.append_page(sample_df, page_number=1, has_more=True)
        
        assert new_count == 3
        assert book.row_count == 3
        assert book.page_count == 1
    
    def test_append_page_skips_duplicates(self, book, sample_df):
        """Appending same page should skip known PKs."""
        book.append_page(sample_df, page_number=1)
        new_count = book.append_page(sample_df, page_number=2)
        
        # Should add 0 new rows (all duplicates)
        assert new_count == 0
        assert book.row_count == 3
    
    def test_append_page_adds_new_rows(self, book, sample_df):
        """Appending page with new rows should add them."""
        book.append_page(sample_df, page_number=1)
        
        new_df = pd.DataFrame({
            "id": [4, 5],
            "name": ["D", "E"],
            "value": [40, 50]
        })
        new_count = book.append_page(new_df, page_number=2)
        
        assert new_count == 2
        assert book.row_count == 5
    
    def test_known_pks(self, book, sample_df):
        """Test known PKs set."""
        book.append_page(sample_df, page_number=1)
        
        known = book.known_pks
        
        assert len(known) == 3
        assert (("id", 1),) in known
        assert (("id", 2),) in known
        assert (("id", 3),) in known
    
    def test_get_pk_exclusion_list(self, book, sample_df):
        """Test getting PK exclusion list for SQL."""
        book.append_page(sample_df, page_number=1)
        
        exclusion_list = book.get_pk_exclusion_list()
        
        assert len(exclusion_list) == 3
        assert {"id": 1} in exclusion_list
    
    def test_to_dataframe(self, book, sample_df):
        """Test converting to DataFrame."""
        book.append_page(sample_df, page_number=1)
        
        result_df = book.to_dataframe()
        
        assert len(result_df) == 3
        assert list(result_df["id"]) == [1, 2, 3]
    
    def test_to_dataframe_empty(self, book):
        """Test converting empty book to DataFrame."""
        result_df = book.to_dataframe()
        
        assert len(result_df) == 0
    
    def test_reconcile_data_preserves_order(self, book):
        """Test that reconcile preserves session book order."""
        # Add rows in specific order
        df1 = pd.DataFrame({"id": [3, 1, 2], "value": ["C", "A", "B"]})
        book.append_page(df1, page_number=1)
        
        # Fresh data in different order with updated values
        fresh_df = pd.DataFrame({"id": [1, 2, 3], "value": ["A_new", "B_new", "C_new"]})
        
        result = book.reconcile_data(fresh_df)
        
        # Order should be preserved (3, 1, 2)
        assert list(result["id"]) == [3, 1, 2]
        # Values should be fresh
        assert list(result["value"]) == ["C_new", "A_new", "B_new"]
    
    def test_reconcile_data_marks_deleted(self, book):
        """Test that reconcile marks deleted rows."""
        df1 = pd.DataFrame({"id": [1, 2, 3], "value": ["A", "B", "C"]})
        book.append_page(df1, page_number=1)
        
        # Fresh data missing id=2
        fresh_df = pd.DataFrame({"id": [1, 3], "value": ["A_new", "C_new"]})
        
        result = book.reconcile_data(fresh_df)
        
        # Should have 3 rows, with row 2 marked as deleted
        assert len(result) == 3
        deleted_row = result[result["id"] == 2].iloc[0]
        assert deleted_row.get("_deleted") is True
    
    def test_multi_pk_book(self, multi_pk_book):
        """Test session book with composite primary key."""
        df = pd.DataFrame({
            "patient_id": ["P1", "P1", "P2"],
            "variant_id": ["V1", "V2", "V1"],
            "value": [10, 20, 30]
        })
        
        new_count = multi_pk_book.append_page(df, page_number=1)
        
        assert new_count == 3
        assert multi_pk_book.row_count == 3


class TestSessionBookManager:
    """Tests for SessionBookManager class."""
    
    def test_get_book_creates_new(self):
        """Getting book for new session should create it."""
        from src.db.session_book import SessionBookManager
        
        manager = SessionBookManager(primary_key=["id"])
        book = manager.get_book("session1")
        
        assert book is not None
        assert book.row_count == 0
    
    def test_get_book_returns_same(self):
        """Getting book for same session should return same instance."""
        from src.db.session_book import SessionBookManager
        
        manager = SessionBookManager(primary_key=["id"])
        book1 = manager.get_book("session1")
        book2 = manager.get_book("session1")
        
        assert book1 is book2
    
    def test_get_book_different_sessions(self):
        """Different sessions should have different books."""
        from src.db.session_book import SessionBookManager
        
        manager = SessionBookManager(primary_key=["id"])
        book1 = manager.get_book("session1")
        book2 = manager.get_book("session2")
        
        assert book1 is not book2
    
    def test_clear_book(self):
        """Clearing book should reset its data but keep instance."""
        from src.db.session_book import SessionBookManager
        
        manager = SessionBookManager(primary_key=["id"])
        book1 = manager.get_book("session1")
        
        # Add some data
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        book1.append_page(df, page_number=1)
        assert book1.row_count == 2
        
        manager.clear_book("session1")
        
        # Same book instance should now be empty
        assert book1.row_count == 0
    
    def test_remove_book(self):
        """Removing book should delete it entirely."""
        from src.db.session_book import SessionBookManager
        
        manager = SessionBookManager(primary_key=["id"])
        manager.get_book("session1")
        assert manager.session_count == 1
        
        manager.remove_book("session1")
        
        # Session should be gone
        assert manager.session_count == 0
        
        # Getting it again creates a new book
        new_book = manager.get_book("session1")
        assert new_book.row_count == 0
    
    def test_clear_all_sessions(self):
        """Clearing all sessions should remove all books."""
        from src.db.session_book import SessionBookManager
        
        manager = SessionBookManager(primary_key=["id"])
        manager.get_book("session1")
        manager.get_book("session2")
        
        manager.clear_all()
        
        # Books should be fresh
        book1 = manager.get_book("session1")
        book2 = manager.get_book("session2")
        assert book1.row_count == 0
        assert book2.row_count == 0

class TestSessionBookGetStats:
    """Tests for session book statistics."""
    
    @pytest.fixture
    def book(self):
        from src.db.session_book import SessionBook
        return SessionBook(primary_key=["id"])
    
    def test_get_stats_empty(self, book):
        """Empty book should have zero stats."""
        stats = book.get_stats()
        
        assert stats["row_count"] == 0
        assert stats["page_count"] == 0
        assert stats["has_more"] is True
        assert stats["next_page"] == 1
        assert stats["oldest_refresh"] is None
        assert stats["newest_refresh"] is None
    
    def test_get_stats_with_data(self, book):
        """Book with data should have proper stats."""
        df = pd.DataFrame({"id": [1, 2, 3], "value": ["A", "B", "C"]})
        book.append_page(df, page_number=1, has_more=True)
        
        stats = book.get_stats()
        
        assert stats["row_count"] == 3
        assert stats["page_count"] == 1
        assert stats["has_more"] is True
        assert stats["next_page"] == 2
        assert stats["oldest_refresh"] is not None
        assert stats["newest_refresh"] is not None


class TestSessionBookHasMorePages:
    """Tests for has_more_pages method."""
    
    @pytest.fixture
    def book(self):
        from src.db.session_book import SessionBook
        return SessionBook(primary_key=["id"])
    
    def test_has_more_empty(self, book):
        """Empty book should indicate more pages."""
        assert book.has_more_pages() is True
    
    def test_has_more_with_more(self, book):
        """Book with more pages should return True."""
        df = pd.DataFrame({"id": [1, 2], "value": ["A", "B"]})
        book.append_page(df, page_number=1, has_more=True)
        
        assert book.has_more_pages() is True
    
    def test_has_more_no_more(self, book):
        """Book at last page should return False."""
        df = pd.DataFrame({"id": [1, 2], "value": ["A", "B"]})
        book.append_page(df, page_number=1, has_more=False)
        
        assert book.has_more_pages() is False


class TestSessionBookGetNextPageNumber:
    """Tests for get_next_page_number method."""
    
    @pytest.fixture
    def book(self):
        from src.db.session_book import SessionBook
        return SessionBook(primary_key=["id"])
    
    def test_next_page_empty(self, book):
        """Empty book should return page 1."""
        assert book.get_next_page_number() == 1
    
    def test_next_page_after_one(self, book):
        """After page 1, should return page 2."""
        df = pd.DataFrame({"id": [1], "value": ["A"]})
        book.append_page(df, page_number=1)
        
        assert book.get_next_page_number() == 2
    
    def test_next_page_after_multiple(self, book):
        """After multiple pages, should return correct next."""
        for i in range(3):
            df = pd.DataFrame({"id": [i * 10 + 1, i * 10 + 2], "value": ["A", "B"]})
            book.append_page(df, page_number=i + 1)
        
        assert book.get_next_page_number() == 4


class TestSessionBookGetRowByPk:
    """Tests for get_row_by_pk method."""
    
    @pytest.fixture
    def book(self):
        from src.db.session_book import SessionBook
        return SessionBook(primary_key=["id"])
    
    def test_get_row_found(self, book):
        """Should return row data when found."""
        df = pd.DataFrame({"id": [1, 2, 3], "value": ["A", "B", "C"]})
        book.append_page(df, page_number=1)
        
        row = book.get_row_by_pk({"id": 2})
        
        assert row is not None
        assert row["id"] == 2
        assert row["value"] == "B"
    
    def test_get_row_not_found(self, book):
        """Should return None when row not found."""
        df = pd.DataFrame({"id": [1, 2], "value": ["A", "B"]})
        book.append_page(df, page_number=1)
        
        row = book.get_row_by_pk({"id": 999})
        
        assert row is None


class TestSessionBookUpdateRow:
    """Tests for update_row method."""
    
    @pytest.fixture
    def book(self):
        from src.db.session_book import SessionBook
        return SessionBook(primary_key=["id"])
    
    def test_update_row_success(self, book):
        """Should update row and return True."""
        df = pd.DataFrame({"id": [1, 2], "value": ["A", "B"]})
        book.append_page(df, page_number=1)
        
        result = book.update_row({"id": 1}, {"value": "A_updated"})
        
        assert result is True
        row = book.get_row_by_pk({"id": 1})
        assert row["value"] == "A_updated"
    
    def test_update_row_not_found(self, book):
        """Should return False when row not found."""
        df = pd.DataFrame({"id": [1, 2], "value": ["A", "B"]})
        book.append_page(df, page_number=1)
        
        result = book.update_row({"id": 999}, {"value": "X"})
        
        assert result is False


class TestSessionBookReconcileEmpty:
    """Tests for reconcile_data with empty book."""
    
    @pytest.fixture
    def book(self):
        from src.db.session_book import SessionBook
        return SessionBook(primary_key=["id"])
    
    def test_reconcile_empty_book(self, book):
        """Reconciling empty book should return input df."""
        fresh_df = pd.DataFrame({"id": [1, 2], "value": ["A", "B"]})
        
        result = book.reconcile_data(fresh_df)
        
        # Should return the fresh_df unchanged (empty book case)
        pd.testing.assert_frame_equal(result, fresh_df)