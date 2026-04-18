"""E2E tests: login, logout, redirect behaviour."""
import pytest

pytestmark = pytest.mark.e2e

E2E_PASSWORD = "testpassword123"


def test_login_page_renders(page, server_url):
    page.goto(f"{server_url}/login")
    assert page.locator("input[name='password']").is_visible()
    assert "RunCoach" in page.title() or "RunCoach" in page.content()


def test_unauthenticated_redirects_to_login(page, server_url):
    page.goto(f"{server_url}/")
    assert "/login" in page.url


def test_wrong_password_shows_error(page, server_url):
    page.goto(f"{server_url}/login")
    page.fill("input[name='password']", "wrongpassword")
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    assert "/login" in page.url
    content = page.content()
    assert "Incorrect" in content or "incorrect" in content or "Invalid" in content


def test_correct_password_lands_on_dashboard(page, server_url):
    page.goto(f"{server_url}/login")
    page.fill("input[name='password']", E2E_PASSWORD)
    page.click("button[type='submit']")
    page.wait_for_url(f"{server_url}/")
    assert page.url == f"{server_url}/"


def test_logout_clears_session(logged_in_page, server_url):
    page = logged_in_page
    page.locator("form[action*='logout'] button").click()
    page.wait_for_load_state("networkidle")
    page.goto(f"{server_url}/")
    assert "/login" in page.url
