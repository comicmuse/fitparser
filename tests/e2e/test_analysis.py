"""E2E tests: AI analysis trigger, Ollama integration, and polling."""
import pytest

from runcoach.db import RunCoachDB
from tests.e2e.conftest import SAMPLE_FIT_REL, SAMPLE_YAML_REL

pytestmark = pytest.mark.e2e


@pytest.fixture
def parsed_run(e2e_data_dir):
    """Fresh parsed run for each analysis test (avoid state bleed from seeded_run_id).

    Uses a unique fit_path per call so get_run_by_fit_path won't collide with
    the session-scoped seeded_run_id fixture which also uses SAMPLE_FIT_REL.
    """
    import time

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    # Unique fit_path so it never conflicts with seeded_run_id's SAMPLE_FIT_REL
    unique_fit = f"activities/e2e/analysis_test_{int(time.time() * 1000)}/test.fit"
    run_id = db.insert_manual_run(
        "Analysis Test Run", "2026-02-15", unique_fit, 5000, 1500
    )
    db.update_parsed(run_id, SAMPLE_YAML_REL, 176.0, 145, "Analysis Test Run")
    yield run_id


def test_analyze_now_triggers_analysis_and_shows_commentary(
    logged_in_page, server_url, parsed_run
):
    """
    Click Analyze Now → background thread calls mock Ollama → page polls
    /run/<id>/status → JS reloads → .commentary div appears.
    """
    page = logged_in_page
    page.goto(f"{server_url}/run/{parsed_run}")
    page.locator("button", has_text="Analyze Now").click()

    # The page polls /run/<id>/status every 5s and reloads on 'analyzed'.
    # With mock Ollama the background thread completes in <1s.
    # Give 30s to account for slow CI environments.
    page.wait_for_selector(".commentary", timeout=30_000)

    commentary_text = page.text_content(".commentary")
    # Commentary should be substantive — works for both mock and real Ollama
    assert len(commentary_text.strip()) > 20


def test_reanalyze_button_visible_after_analysis(
    logged_in_page, server_url, parsed_run
):
    """After analysis completes, Re-analyze button replaces Analyze Now."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{parsed_run}")
    page.locator("button", has_text="Analyze Now").click()
    page.wait_for_selector(".commentary", timeout=30_000)

    assert page.locator("button", has_text="Re-analyze").is_visible()
    assert not page.locator("button", has_text="Analyze Now").is_visible()


def test_reanalyze_replaces_commentary(logged_in_page, server_url, parsed_run, e2e_data_dir):
    """Re-analyze on an already-analyzed run updates the commentary."""
    # First analysis
    page = logged_in_page
    page.goto(f"{server_url}/run/{parsed_run}")
    page.locator("button", has_text="Analyze Now").click()
    page.wait_for_selector(".commentary", timeout=30_000)

    # Trigger re-analysis
    page.locator("button", has_text="Re-analyze").click()
    # Polling reloads the page; wait for commentary to reappear
    page.wait_for_selector(".commentary", timeout=30_000)

    assert len(page.text_content(".commentary").strip()) > 20


def test_run_status_endpoint_returns_analyzed(
    logged_in_page, server_url, parsed_run, e2e_data_dir
):
    """After triggering analysis, /run/<id>/status returns stage=analyzed."""
    import time

    page = logged_in_page
    page.goto(f"{server_url}/run/{parsed_run}")
    page.locator("button", has_text="Analyze Now").click()

    # Wait for analysis to complete via UI
    page.wait_for_selector(".commentary", timeout=30_000)

    # Verify the status endpoint directly
    response = page.request.get(f"{server_url}/run/{parsed_run}/status")
    data = response.json()
    assert data["stage"] == "analyzed"
    assert data["analyzed_at"] is not None
