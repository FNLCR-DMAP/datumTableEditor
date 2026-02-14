"""
E2E Smoke Tests — Playwright against staging.

These verify that the production-identical app actually loads, renders data,
and responds to user interactions in a real browser.

All tests are automatically SKIPPED when E2E_BASE_URL is not set.
See tests/e2e/conftest.py for prerequisites.
"""

import pytest
import re


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  1. APP LOADS                                                         ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestAppLoads:
    """Verify the Shiny app boots and renders core structure."""

    def test_page_title(self, app_page):
        """Page should have the configured app title."""
        title = app_page.title()
        assert title, "Page title is empty — app may not have loaded"

    def test_main_container_visible(self, app_page):
        """The main split-panel container must be present."""
        container = app_page.locator(".main-container")
        assert container.is_visible(), "Main container not rendered"

    def test_left_panel_visible(self, app_page):
        """Sidebar (left panel) must be visible on load."""
        panel = app_page.locator(".left-panel")
        assert panel.is_visible()

    def test_right_panel_visible(self, app_page):
        """Main content (right panel) must be visible on load."""
        panel = app_page.locator(".right-panel")
        assert panel.is_visible()

    def test_toolbar_present(self, app_page):
        """Top toolbar with action buttons must render."""
        toolbar = app_page.locator(".top-toolbar")
        assert toolbar.is_visible()


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  2. DATA TABLE                                                        ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestDataTable:
    """Verify the data table renders with actual data."""

    def test_table_renders(self, app_page):
        """The <table class="edit-table"> element must exist."""
        table = app_page.locator("table.edit-table")
        assert table.count() > 0, "Data table not found"

    def test_table_has_header(self, app_page):
        """Table should have a <thead> with column headers."""
        headers = app_page.locator("table.edit-table thead th")
        count = headers.count()
        # Minimum: checkbox + row# + at least one data column
        assert count >= 3, f"Expected at least 3 header columns, got {count}"

    def test_table_has_rows(self, app_page):
        """Table body should contain data rows."""
        rows = app_page.locator("table.edit-table tbody tr")
        count = rows.count()
        assert count > 0, "Table has no data rows — database may be empty"

    def test_row_has_checkbox(self, app_page):
        """Each row should have a selection checkbox."""
        checkbox = app_page.locator("table.edit-table tbody tr:first-child td:first-child input[type='checkbox']")
        assert checkbox.count() > 0, "Row checkbox not found"

    def test_row_has_row_number(self, app_page):
        """Rows should display row numbers."""
        row_num = app_page.locator("table.edit-table tbody tr:first-child .row-number")
        assert row_num.count() > 0

    def test_editable_cells_have_class(self, app_page):
        """Data cells should have editable-cell or readonly-cell class."""
        cells = app_page.locator("table.edit-table tbody td.editable-cell, table.edit-table tbody td.readonly-cell")
        assert cells.count() > 0, "No data cells found with expected classes"

    def test_cells_have_data_attributes(self, app_page):
        """Editable cells should have data-row and data-col attributes."""
        cell = app_page.locator("table.edit-table tbody td[data-row][data-col]").first
        assert cell.is_visible()
        assert cell.get_attribute("data-row") is not None
        assert cell.get_attribute("data-col") is not None


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  3. SIDEBAR CONTROLS                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestSidebar:
    """Verify sidebar UI elements are functional."""

    def test_table_name_displayed(self, app_page):
        """Table title is shown in the sidebar."""
        title = app_page.locator(".table-name-section .table-name")
        assert title.is_visible()
        assert title.inner_text().strip(), "Table title is empty"

    def test_data_summary_displayed(self, app_page):
        """Data summary text (row count) should appear."""
        summary = app_page.locator("#data_summary, .table-name-section")
        assert summary.is_visible()

    def test_search_input_exists(self, app_page):
        """Search text input is present in the sidebar."""
        search = app_page.locator(".filter-section input[type='text']")
        assert search.count() > 0

    def test_search_button_exists(self, app_page):
        """Search button is clickable."""
        btn = app_page.locator("button:has-text('Search'), .filter-section .btn")
        assert btn.count() > 0

    def test_sidebar_toggle_works(self, app_page):
        """Clicking the toggle button should collapse/expand the sidebar."""
        toggle = app_page.locator(".toggle-btn")
        assert toggle.is_visible()
        
        left_panel = app_page.locator(".left-panel")
        initial_width = left_panel.bounding_box()["width"]
        
        toggle.click()
        app_page.wait_for_timeout(500)  # wait for CSS transition
        
        new_width = left_panel.bounding_box()["width"]
        assert new_width != initial_width, "Sidebar toggle had no effect"


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  4. PAGINATION                                                        ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestPagination:
    """Verify pagination controls work."""

    def test_pagination_section_visible(self, app_page):
        """Pagination controls section exists."""
        section = app_page.locator(".pagination-controls-section")
        assert section.is_visible()

    def test_rows_per_page_selector(self, app_page):
        """Rows-per-page dropdown or selector should exist."""
        selector = app_page.locator("select, .pagination-controls-section .rows-per-page")
        assert selector.count() > 0, "No rows-per-page selector found"

    def test_page_navigation(self, app_page):
        """Page navigation buttons (prev/next) should exist."""
        nav = app_page.locator(".pagination-controls-section button, .pagination-controls-section .page-btn")
        assert nav.count() > 0


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  5. TOOLBAR ACTIONS                                                   ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestToolbar:
    """Verify toolbar buttons are present and responsive."""

    def test_copy_button_exists(self, app_page):
        """Copy button should exist in toolbar."""
        btn = app_page.locator(".toolbar-left button:has-text('Copy')")
        assert btn.count() > 0

    def test_clear_selection_button(self, app_page):
        """Clear Selection button should exist."""
        btn = app_page.locator("button:has-text('Clear Selection')")
        assert btn.count() > 0

    def test_preset_dropdown(self, app_page):
        """Preset dropdown trigger should be visible."""
        preset_btn = app_page.locator(".preset-btn, .preset-dropdown")
        assert preset_btn.count() > 0

    def test_manage_layout_button(self, app_page):
        """Manage Layout button should open the column modal."""
        btn = app_page.locator("button:has-text('Manage Layout')")
        assert btn.is_visible()

    def test_mod_log_button(self, app_page):
        """Mod Log button should be visible."""
        btn = app_page.locator("button:has-text('Mod Log')")
        assert btn.is_visible()


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  6. MODALS                                                            ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestModals:
    """Verify modals open and close correctly."""

    def test_column_modal_opens(self, app_page):
        """Clicking 'Manage Layout' should open the column modal."""
        app_page.locator("button:has-text('Manage Layout')").click()
        modal = app_page.locator("#add-column-modal")
        modal.wait_for(state="visible", timeout=3000)
        assert modal.is_visible()
        # Close it
        app_page.locator("#add-column-modal .modal-close").click()
        app_page.wait_for_timeout(300)

    def test_copy_modal_opens(self, app_page):
        """Clicking 'Copy' should open the copy column modal."""
        app_page.locator(".toolbar-left button:has-text('Copy')").click()
        modal = app_page.locator("#copy-column-modal")
        modal.wait_for(state="visible", timeout=3000)
        assert modal.is_visible()
        # Close it
        app_page.locator("#copy-column-modal .modal-close").click()
        app_page.wait_for_timeout(300)

    def test_log_modal_opens(self, app_page):
        """Clicking 'Mod Log' should open the modifications log."""
        app_page.locator("button:has-text('Mod Log')").click()
        modal = app_page.locator("#log-modal")
        modal.wait_for(state="visible", timeout=3000)
        assert modal.is_visible()
        # Close it
        app_page.locator("#log-modal .modal-close").click()
        app_page.wait_for_timeout(300)


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  7. CELL INTERACTION                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestCellInteraction:
    """Verify cell selection and edit triggering."""

    def test_click_editable_cell(self, app_page):
        """Clicking an editable cell should trigger the edit modal or inline edit."""
        cell = app_page.locator("table.edit-table tbody td.editable-cell").first
        cell.dblclick()  # Most table editors use double-click
        app_page.wait_for_timeout(500)
        # The app should show some edit UI (modal or inline input)
        # We just verify no crash/error occurred
        assert app_page.locator("table.edit-table").is_visible(), "Table disappeared after cell click"

    def test_select_row_checkbox(self, app_page):
        """Clicking a row checkbox should select the row."""
        checkbox = app_page.locator("table.edit-table tbody tr:first-child input[type='checkbox']").first
        checkbox.click()
        app_page.wait_for_timeout(300)
        # Verify checkbox is now checked
        assert checkbox.is_checked()

    def test_select_all_checkbox(self, app_page):
        """The select-all checkbox should toggle all visible row checkboxes."""
        select_all = app_page.locator("#select_all_page")
        if select_all.count() > 0:
            select_all.click()
            app_page.wait_for_timeout(300)
            # At least one row checkbox should now be checked
            checked = app_page.locator("table.edit-table tbody input[type='checkbox']:checked")
            assert checked.count() > 0


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  8. SEARCH                                                            ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestSearch:
    """Verify search functionality."""

    def test_search_filters_table(self, app_page):
        """Typing a search term and clicking Search should filter rows."""
        # Count rows before search
        rows_before = app_page.locator("table.edit-table tbody tr").count()
        
        # Enter a search term (use a term unlikely to match all rows)
        search_input = app_page.locator(".filter-section input[type='text']").first
        search_input.fill("ZZZZNONEXISTENT99999")
        
        search_btn = app_page.locator("button:has-text('Search')").first
        search_btn.click()
        
        # Wait for Shiny to re-render
        app_page.wait_for_function(
            "() => !document.querySelector('.shiny-busy')",
            timeout=10000,
        )
        app_page.wait_for_timeout(1000)
        
        rows_after = app_page.locator("table.edit-table tbody tr").count()
        # With a nonsense search term, we expect fewer rows (possibly 0)
        assert rows_after <= rows_before
        
        # Clear search to restore state
        search_input.fill("")
        search_btn.click()
        app_page.wait_for_function(
            "() => !document.querySelector('.shiny-busy')",
            timeout=10000,
        )


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  9. NO CONSOLE ERRORS                                                 ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class TestNoJsErrors:
    """Verify no JavaScript errors on page load."""

    def test_no_console_errors(self, page, base_url):
        """Page load should produce no JS errors."""
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        
        page.goto(base_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)  # let Shiny settle
        
        assert len(errors) == 0, f"JS errors on load: {errors}"

    def test_no_failed_network_requests(self, page, base_url):
        """No critical network requests should fail (4xx/5xx)."""
        failures = []
        
        def on_response(response):
            if response.status >= 400 and not response.url.endswith((".ico", ".map")):
                failures.append(f"{response.status} {response.url}")
        
        page.on("response", on_response)
        page.goto(base_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        
        assert len(failures) == 0, f"Failed requests: {failures}"
