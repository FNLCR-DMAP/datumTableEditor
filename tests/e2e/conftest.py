`"""
E2E Test Configuration — Playwright against a live staging environment.

PREREQUISITES (all must be true for E2E tests to run):
  1. A staging PostgreSQL instance seeded with demo data
  2. A staging Datum proxy pointing at that database
  3. The Shiny app deployed to staging WITHOUT SSO (basic auth or open)
  4. Environment variable E2E_BASE_URL set to the staging app URL
  5. (Optional) E2E_USERNAME / E2E_PASSWORD if basic auth is enabled

These tests are automatically SKIPPED when E2E_BASE_URL is not set,
so they will never block the existing unit/integration test suite.

To run E2E tests once staging is available:
    E2E_BASE_URL=https://staging.example.com/app \\
    E2E_USERNAME=testuser \\
    E2E_PASSWORD=testpass \\
    python -m pytest tests/e2e/ -v --headed
"""

import os
import pytest

# ---------------------------------------------------------------------------
# Skip entire directory if staging env is not configured
# ---------------------------------------------------------------------------

E2E_BASE_URL = os.environ.get("E2E_BASE_URL", "").rstrip("/")
E2E_USERNAME = os.environ.get("E2E_USERNAME", "")
E2E_PASSWORD = os.environ.get("E2E_PASSWORD", "")

STAGING_NOT_CONFIGURED = not E2E_BASE_URL

SKIP_REASON = (
    "E2E tests require a staging environment. "
    "Set E2E_BASE_URL to the staging Shiny app URL. "
    "See tests/e2e/conftest.py for full prerequisites: "
    "staging PostgreSQL + Datum proxy + Shiny app (no SSO)."
)


def pytest_collection_modifyitems(config, items):
    """Auto-skip all e2e tests when staging is not available."""
    if STAGING_NOT_CONFIGURED:
        skip_marker = pytest.mark.skip(reason=SKIP_REASON)
        for item in items:
            if "e2e" in str(item.fspath):
                item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# Playwright fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def browser_context_args():
    """Default Playwright browser context settings."""
    return {
        "viewport": {"width": 1440, "height": 900},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def base_url():
    """The staging app base URL."""
    return E2E_BASE_URL


@pytest.fixture(scope="function")
def authenticated_page(page, base_url):
    """
    Navigate to the app and handle basic auth if credentials are provided.
    
    For RStudio Connect with basic auth (non-SSO staging):
    - Fills the login form if detected
    - Returns the page ready for interaction
    """
    page.goto(base_url, wait_until="networkidle", timeout=30000)
    
    # Handle basic auth login form if present
    if E2E_USERNAME and E2E_PASSWORD:
        login_form = page.locator("input[name='username'], input[type='email']")
        if login_form.count() > 0:
            login_form.first.fill(E2E_USERNAME)
            page.locator("input[name='password'], input[type='password']").first.fill(E2E_PASSWORD)
            page.locator("button[type='submit'], input[type='submit']").first.click()
            page.wait_for_load_state("networkidle", timeout=15000)
    
    return page


@pytest.fixture(scope="function")
def app_page(authenticated_page):
    """
    Wait for the Shiny app to fully initialize.
    
    The app is ready when:
    - The data table container is visible
    - Shiny has finished its initial reactive flush
    """
    page = authenticated_page
    
    # Wait for the main table container to appear (Shiny renders it reactively)
    page.wait_for_selector(".table-container, .data-table, table", timeout=30000)
    
    # Wait for Shiny to settle (no more busy indicator)
    page.wait_for_function(
        "() => !document.querySelector('.shiny-busy')",
        timeout=15000,
    )
    
    return page
