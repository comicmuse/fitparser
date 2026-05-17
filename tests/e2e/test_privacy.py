"""Playwright E2E tests for the privacy policy page."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_privacy_page_returns_200(page, server_url):
    """GET /privacy returns 200 with expected heading."""
    page.goto(f"{server_url}/privacy")
    page.wait_for_load_state("networkidle")
    expect(page.locator("h1")).to_contain_text("Privacy Policy")


def test_privacy_page_no_login_required(page, server_url):
    """/privacy is accessible without authentication."""
    page.goto(f"{server_url}/privacy")
    # Should not be redirected to /login
    assert "/login" not in page.url
    assert page.url.endswith("/privacy")
