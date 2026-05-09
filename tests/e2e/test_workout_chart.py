"""Playwright E2E tests for the holistic workout chart."""
from __future__ import annotations

import json

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


def test_flip_card_appears_on_click(logged_in_page, server_url, seeded_run_id):
    """Clicking a segment column flips to the detail card."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    page.wait_for_load_state("networkidle")

    detail = page.locator("#wc-detail")
    expect(detail).not_to_be_visible()

    first_col = page.locator(".wc-col").first
    first_col.click()
    page.wait_for_timeout(500)

    expect(detail).to_be_visible()
    content = detail.text_content()
    assert content and len(content.strip()) > 5


def test_flip_card_shows_running_dynamics(logged_in_page, server_url, seeded_run_id):
    """Clicking a segment that has running_dynamics shows Cadence in the detail card."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    page.wait_for_load_state("networkidle")

    cols = page.locator(".wc-col").all()
    found = False
    for col in cols:
        col.click()
        page.wait_for_timeout(500)
        detail = page.locator("#wc-detail")
        expect(detail).to_be_visible()
        if "Cadence" in (detail.text_content() or ""):
            found = True
            break
        # Close and try next
        detail.click()
        page.wait_for_timeout(500)

    assert found, "No segment detail card showed running dynamics (Cadence)"


def test_old_chart_elements_absent(logged_in_page, server_url, seeded_run_id):
    """The old block cards, HR zone canvas chart, and block timeline are gone."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    page.wait_for_load_state("networkidle")

    expect(page.locator("#hrZoneChart")).to_have_count(0)
    expect(page.locator(".block-grid")).to_have_count(0)
    expect(page.locator(".block-card")).to_have_count(0)


def test_detail_avg_power_uses_target_compliance_color(logged_in_page, server_url, seeded_run_id):
    """Avg Power value in detail card is coloured by compliance with target range."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    page.wait_for_load_state("networkidle")

    found_targeted_segment = False
    cols = page.locator(".wc-col").all()
    for col in cols:
        segment_raw = col.get_attribute("data-segment")
        assert segment_raw is not None
        segment = json.loads(segment_raw)
        target = segment.get("target")
        avg_power = segment.get("avg_power")
        if not target or avg_power is None:
            continue

        found_targeted_segment = True
        if avg_power > target["max_w"]:
            expected = "above"
        elif avg_power < target["min_w"]:
            expected = "below"
        else:
            expected = "in"

        col.click()
        page.wait_for_timeout(500)

        avg_power_box = page.locator(".wc-stat-box", has_text="Avg Power")
        expect(avg_power_box).to_be_visible()
        avg_power_value = avg_power_box.locator(".wc-stat-val").first
        klass = avg_power_value.get_attribute("class") or ""
        assert f"wc-stat-val--{expected}" in klass

        # Close before checking the next segment
        page.locator("#wc-detail").click()
        page.wait_for_timeout(500)

    assert found_targeted_segment, "Expected at least one segment with target power and avg power"
