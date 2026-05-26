"""E2E tests: LLM rate limiting flash messages."""
import time

import pytest

from runcoach.db import RunCoachDB
from tests.e2e.conftest import SAMPLE_FIT_REL

pytestmark = pytest.mark.e2e


@pytest.fixture
def rate_limit_run(e2e_data_dir):
    """Fresh parsed run for rate-limit tests (unique fit_path each call)."""
    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    unique_fit = f"activities/e2e/rate_limit_test_{int(time.time() * 1000)}/test.fit"
    run_id = db.insert_manual_run("Rate Limit Test", "2026-05-26", unique_fit, 5000, 1500)
    db.update_parsed(run_id, None, 176.0, 145, "Rate Limit Test")
    return run_id


def test_analyze_rate_limited_shows_flash(
    logged_in_page, server_url, e2e_data_dir, rate_limit_run
):
    """Enabling the rate limit with cap=0 shows the flash message on analyze."""
    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    user_id = db.get_default_user_id()

    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", "0")
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))

    try:
        page = logged_in_page
        page.goto(f"{server_url}/run/{rate_limit_run}")
        page.locator("button", has_text="Analyze Now").click()

        page.wait_for_selector(".flash", timeout=5_000)
        flash_text = page.text_content(".flash")
        assert "Daily analysis limit reached" in flash_text
    finally:
        # Always restore to avoid bleeding into other tests
        db.set_site_setting("llm_limiting_enabled", "0")
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
