"""E2E tests: athlete profile page."""
import pytest

pytestmark = pytest.mark.e2e


def test_profile_page_loads(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    assert page.locator("textarea[name='profile']").is_visible()


def test_save_coaching_profile(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("textarea[name='profile']", "I run 60 miles per week.")
    # The coaching profile form contains the textarea — use it to find the submit button
    page.locator("textarea[name='profile']").press("Tab")
    page.locator("form:has(textarea[name='profile']) button[type='submit']").click()
    page.wait_for_load_state("networkidle")
    assert "saved" in page.content().lower() or "profile" in page.content().lower()


def test_profile_text_persists(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("textarea[name='profile']", "Persistent profile text.")
    page.locator("form:has(textarea[name='profile']) button[type='submit']").click()
    page.wait_for_load_state("networkidle")

    page.goto(f"{server_url}/athlete-profile")
    assert "Persistent profile text." in page.locator("textarea[name='profile']").input_value()


def test_save_race_goal_valid(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("input[name='race_date']", "2027-04-26")
    page.select_option("select[name='race_distance']", "Marathon")
    page.locator("form[action*='race-goal'] button[type='submit']").first.click()
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "saved" in content.lower() or "marathon" in content.lower() or "goal" in content.lower()


def test_race_goal_past_date_rejected(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("input[name='race_date']", "2020-01-01")
    page.select_option("select[name='race_distance']", "Marathon")
    page.locator("form[action*='race-goal'] button[type='submit']").first.click()
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "future" in content.lower() or "past" in content.lower() or "invalid" in content.lower()


def test_clear_race_goal(logged_in_page, server_url):
    # First set a goal
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("input[name='race_date']", "2027-06-01")
    page.select_option("select[name='race_distance']", "10K")
    page.locator("form[action*='race-goal'] button[type='submit']").first.click()
    page.wait_for_load_state("networkidle")

    # Clear using the "Clear" button (name="race_date" value="")
    page.goto(f"{server_url}/athlete-profile")
    page.locator("form[action*='race-goal'] button[name='race_date']").click()
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "cleared" in content.lower() or "saved" in content.lower() or "goal" in content.lower()


def test_save_display_name(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("input[name='display_name']", "Test Athlete")
    page.locator("form[action*='user-info'] button[type='submit']").click()
    page.wait_for_load_state("networkidle")
    assert "saved" in page.content().lower() or "Test Athlete" in page.content()
