"""Playwright E2E tests for the holistic workout chart."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_workout_chart_renders(logged_in_page, server_url, seeded_run_id):
    """The workout chart grid is visible on a parsed run detail page."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    page.wait_for_load_state("networkidle")

    grid = page.locator(".wc-grid")
    expect(grid).to_be_visible()

    cols = page.locator(".wc-col")
    assert cols.count() >= 2, "Expected at least 2 segment columns"


def test_power_bars_visible(logged_in_page, server_url, seeded_run_id):
    """Each segment column contains a power bar and an HR zone strip."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    page.wait_for_load_state("networkidle")

    power_bars = page.locator(".wc-power")
    assert power_bars.count() >= 2

    hr_strips = page.locator(".wc-hr")
    assert hr_strips.count() >= 2


def test_tooltip_appears_on_hover(logged_in_page, server_url, seeded_run_id):
    """Hovering a segment column shows the tooltip with segment data."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    page.wait_for_load_state("networkidle")

    tooltip = page.locator("#wc-tooltip")

    # Move mouse to top-left to ensure no column is hovered
    page.mouse.move(0, 0)
    expect(tooltip).not_to_be_visible()

    first_col = page.locator(".wc-col").first
    first_col.hover()

    expect(tooltip).to_be_visible()

    content = tooltip.text_content()
    assert content and len(content.strip()) > 5


def test_tooltip_shows_running_dynamics(logged_in_page, server_url, seeded_run_id):
    """Hovering a segment that has running_dynamics shows dynamics in the tooltip."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    page.wait_for_load_state("networkidle")

    cols = page.locator(".wc-col").all()
    found = False
    for col in cols:
        col.hover()
        tooltip = page.locator("#wc-tooltip")
        expect(tooltip).to_be_visible()
        if "Cadence" in (tooltip.text_content() or ""):
            found = True
            break

    assert found, "No segment tooltip showed running dynamics (Cadence)"


def test_old_chart_elements_absent(logged_in_page, server_url, seeded_run_id):
    """The old block cards, HR zone canvas chart, and block timeline are gone."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    page.wait_for_load_state("networkidle")

    expect(page.locator("#hrZoneChart")).to_have_count(0)
    expect(page.locator(".block-grid")).to_have_count(0)
    expect(page.locator(".block-card")).to_have_count(0)
