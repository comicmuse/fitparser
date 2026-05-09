"""E2E tests: offline page and service worker registration."""
import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def test_offline_page_reachable(page: Page, server_url: str):
    """The /offline page loads without auth and contains expected text."""
    page.goto(f"{server_url}/offline")
    assert "offline" in page.content().lower()


def test_service_worker_registers(logged_in_page: Page, server_url: str):
    """After loading the app, the service worker is registered."""
    logged_in_page.goto(f"{server_url}/")
    logged_in_page.wait_for_timeout(2000)  # allow SW registration to complete

    sw_registered = logged_in_page.evaluate(
        """async () => {
            if (!('serviceWorker' in navigator)) return false;
            const regs = await navigator.serviceWorker.getRegistrations();
            return regs.length > 0;
        }"""
    )
    assert sw_registered
