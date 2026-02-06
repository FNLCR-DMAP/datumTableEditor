"""
Session Book for Epitopes Data Editor

In-memory only data structure that maintains:
- Local-first row ordering (preserve user's view stability)
- Append-only pages (new data appended at end)
- Skip known PKs (avoid duplicates when paginating)
- Data reconciliation (merge DB-fresh values with local order)
- Clear on sort/filter change (context has changed)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import pandas as pd


@dataclass
class RowEntry:
    """A single row entry in the session book."""
    pk_values: dict[str, Any]  # Primary key column -> value
    data: dict[str, Any]       # Full row data
    page_number: int           # Which page this was loaded from
    load_order: int            # Order within the session book
    last_refreshed: datetime = field(default_factory=datetime.now)
    
    def get_pk_tuple(self) -> tuple:
        """Get hashable PK tuple for lookups."""
        return tuple(sorted(self.pk_values.items()))
    
    def get_pk_json(self) -> str:
        """Get JSON string of PK for database storage."""
        return json.dumps(self.pk_values, sort_keys=True)


@dataclass
class PageInfo:
    """Information about a loaded page."""
    page_number: int
    row_count: int
    loaded_at: datetime = field(default_factory=datetime.now)
    has_more: bool = True


class SessionBook:
    """
    In-memory session book for maintaining local row ordering.
    
    Key principles:
    - Never persisted to disk or database
    - Maintains stable row ordering for UI consistency
    - Appends new pages at the end
    - Skips already-known PKs when loading new pages
    - Clears when sort/filter context changes
    """
    
    def __init__(self, primary_key: list[str]):
        """
        Initialize session book.
        
        Args:
            primary_key: List of column names that form the primary key
        """
        self.primary_key = primary_key
        self._rows: list[RowEntry] = []
        self._pk_index: dict[tuple, int] = {}  # PK tuple -> index in _rows
        self._pages: list[PageInfo] = []
        self._context_hash: Optional[str] = None
        self._load_counter = 0
    
    @property
    def row_count(self) -> int:
        """Total rows in session book."""
        return len(self._rows)
    
    @property
    def page_count(self) -> int:
        """Number of pages loaded."""
        return len(self._pages)
    
    @property
    def known_pks(self) -> set[tuple]:
        """Set of all known PK tuples."""
        return set(self._pk_index.keys())
    
    def set_context(self, context_hash: str) -> bool:
        """
        Set the query context hash. Returns True if context changed (book cleared).
        
        Args:
            context_hash: Hash representing current filter/sort context
            
        Returns:
            True if context changed and book was cleared
        """
        if self._context_hash != context_hash:
            self.clear()
            self._context_hash = context_hash
            return True
        return False
    
    def clear(self) -> None:
        """Clear all data (called when sort/filter changes)."""
        self._rows.clear()
        self._pk_index.clear()
        self._pages.clear()
        self._load_counter = 0
        self._context_hash = None
    
    def append_page(
        self,
        df: pd.DataFrame,
        page_number: int,
        has_more: bool = True
    ) -> int:
        """
        Append a page of data, skipping already-known PKs.
        
        Args:
            df: DataFrame with new rows
            page_number: The page number this data came from
            has_more: Whether there are more pages available
            
        Returns:
            Number of new rows added (excluding duplicates)
        """
        new_count = 0
        
        for _, row in df.iterrows():
            # Extract PK values
            pk_values = {pk: row[pk] for pk in self.primary_key}
            pk_tuple = tuple(sorted(pk_values.items()))
            
            # Skip if already known
            if pk_tuple in self._pk_index:
                # Update data but keep original position (data reconciliation)
                idx = self._pk_index[pk_tuple]
                self._rows[idx].data = row.to_dict()
                self._rows[idx].last_refreshed = datetime.now()
                continue
            
            # Add new row
            entry = RowEntry(
                pk_values=pk_values,
                data=row.to_dict(),
                page_number=page_number,
                load_order=self._load_counter
            )
            self._pk_index[pk_tuple] = len(self._rows)
            self._rows.append(entry)
            self._load_counter += 1
            new_count += 1
        
        # Record page info
        self._pages.append(PageInfo(
            page_number=page_number,
            row_count=len(df),
            has_more=has_more
        ))
        
        return new_count
    
    def get_pk_exclusion_list(self) -> list[dict[str, Any]]:
        """
        Get list of PKs to exclude when fetching next page.
        
        Returns:
            List of PK dicts for SQL IN clause construction
        """
        return [entry.pk_values for entry in self._rows]
    
    def reconcile_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Reconcile fresh DB data with local ordering.
        
        Takes fresh data from DB and returns it in session book order,
        preserving local-first ordering while using DB-fresh values.
        
        Args:
            df: Fresh DataFrame from database
            
        Returns:
            DataFrame in session book order with fresh values
        """
        if self.row_count == 0:
            return df
        
        # Build lookup from fresh data
        fresh_data: dict[tuple, dict] = {}
        for _, row in df.iterrows():
            pk_values = {pk: row[pk] for pk in self.primary_key}
            pk_tuple = tuple(sorted(pk_values.items()))
            fresh_data[pk_tuple] = row.to_dict()
        
        # Build result in session book order
        result_rows = []
        for entry in self._rows:
            pk_tuple = entry.get_pk_tuple()
            if pk_tuple in fresh_data:
                # Use fresh data
                result_rows.append(fresh_data[pk_tuple])
                entry.data = fresh_data[pk_tuple]
                entry.last_refreshed = datetime.now()
            else:
                # Row was deleted from DB - use cached data with marker
                row_data = entry.data.copy()
                row_data["_deleted"] = True
                result_rows.append(row_data)
        
        return pd.DataFrame(result_rows)
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert session book to DataFrame in local order."""
        if not self._rows:
            return pd.DataFrame()
        return pd.DataFrame([entry.data for entry in self._rows])
    
    def get_row_by_pk(self, pk_values: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Get a single row by its primary key values."""
        pk_tuple = tuple(sorted(pk_values.items()))
        if pk_tuple in self._pk_index:
            return self._rows[self._pk_index[pk_tuple]].data
        return None
    
    def update_row(self, pk_values: dict[str, Any], updates: dict[str, Any]) -> bool:
        """
        Update a row's data in the session book.
        
        Args:
            pk_values: Primary key values identifying the row
            updates: Column -> new value updates
            
        Returns:
            True if row was found and updated
        """
        pk_tuple = tuple(sorted(pk_values.items()))
        if pk_tuple not in self._pk_index:
            return False
        
        idx = self._pk_index[pk_tuple]
        self._rows[idx].data.update(updates)
        self._rows[idx].last_refreshed = datetime.now()
        return True
    
    def has_more_pages(self) -> bool:
        """Check if there are more pages to load."""
        if not self._pages:
            return True  # Haven't loaded anything yet
        return self._pages[-1].has_more
    
    def get_next_page_number(self) -> int:
        """Get the next page number to request."""
        if not self._pages:
            return 1
        return self._pages[-1].page_number + 1
    
    def get_stats(self) -> dict:
        """Get session book statistics."""
        return {
            "row_count": self.row_count,
            "page_count": self.page_count,
            "context_hash": self._context_hash,
            "has_more": self.has_more_pages(),
            "next_page": self.get_next_page_number(),
            "oldest_refresh": min((r.last_refreshed for r in self._rows), default=None),
            "newest_refresh": max((r.last_refreshed for r in self._rows), default=None),
        }


class SessionBookManager:
    """
    Manages session books for multiple users/sessions.
    
    Each user session gets its own session book.
    """
    
    def __init__(self, primary_key: list[str]):
        """
        Initialize manager.
        
        Args:
            primary_key: Primary key columns for all session books
        """
        self.primary_key = primary_key
        self._books: dict[str, SessionBook] = {}
    
    def get_book(self, session_id: str) -> SessionBook:
        """
        Get or create session book for a session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            SessionBook for that session
        """
        if session_id not in self._books:
            self._books[session_id] = SessionBook(self.primary_key)
        return self._books[session_id]
    
    def clear_book(self, session_id: str) -> None:
        """Clear a session's book."""
        if session_id in self._books:
            self._books[session_id].clear()
    
    def remove_book(self, session_id: str) -> None:
        """Remove a session's book entirely."""
        self._books.pop(session_id, None)
    
    def clear_all(self) -> None:
        """Clear all session books."""
        self._books.clear()
    
    @property
    def session_count(self) -> int:
        """Number of active sessions."""
        return len(self._books)
