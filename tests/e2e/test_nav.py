"""Playwright E2E tests for the hamburger navigation menu."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_hamburger_visible(logged_in_page, server_url):
    """The hamburger button is visible on all screen sizes."""
    page = logged_in_page
    page.goto(server_url)
    page.wait_for_load_state("networkidle")
    expect(page.locator("#hamburger-btn")).to_be_visible()


def test_hamburger_opens_menu(logged_in_page, server_url):
    """Clicking the hamburger opens the slide-in menu panel."""
    page = logged_in_page
    page.goto(server_url)
    page.wait_for_load_state("networkidle")

    expect(page.locator("#menu-panel")).not_to_be_visible()

    page.locator("#hamburger-btn").click()
    page.wait_for_timeout(300)

    expect(page.locator("#menu-panel")).to_be_visible()
    expect(page.locator("#hamburger-btn")).to_have_attribute("aria-expanded", "true")


def test_close_button_dismisses_menu(logged_in_page, server_url):
    """The ✕ close button inside the panel dismisses the menu."""
    page = logged_in_page
    page.goto(server_url)
    page.wait_for_load_state("networkidle")

    page.locator("#hamburger-btn").click()
    page.wait_for_timeout(300)
    expect(page.locator("#menu-panel")).to_be_visible()

    page.locator("#menu-close-btn").click()
    page.wait_for_timeout(300)
    expect(page.locator("#menu-panel")).not_to_be_visible()
    expect(page.locator("#hamburger-btn")).to_have_attribute("aria-expanded", "false")


def test_backdrop_closes_menu(logged_in_page, server_url):
    """Clicking the backdrop (outside the panel) dismisses the menu."""
    page = logged_in_page
    page.set_viewport_size({"width": 800, "height": 600})
    page.goto(server_url)
    page.wait_for_load_state("networkidle")

    page.locator("#hamburger-btn").click()
    page.wait_for_timeout(300)
    expect(page.locator("#menu-panel")).to_be_visible()

    # Click on the left side of the viewport, outside the 260px panel on the right
    page.mouse.click(100, 300)
    page.wait_for_timeout(300)
    expect(page.locator("#menu-panel")).not_to_be_visible()


def test_menu_navigates_to_athlete_profile(logged_in_page, server_url):
    """Clicking Athlete Profile in the menu navigates to that page."""
    page = logged_in_page
    page.goto(server_url)
    page.wait_for_load_state("networkidle")

    page.locator("#hamburger-btn").click()
    page.wait_for_timeout(300)
    page.locator("#menu-panel").get_by_text("Athlete Profile").click()
    page.wait_for_load_state("networkidle")

    assert "/athlete-profile" in page.url
