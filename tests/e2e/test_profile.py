"""E2E tests: athlete profile page."""
import pytest

pytestmark = pytest.mark.e2e

SAVE = "#save-profile"


def test_profile_page_loads(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    assert page.locator("textarea[name='profile']").is_visible()


def test_page_has_single_save_button(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    assert page.locator("#profile-form").count() == 1
    assert page.locator("#profile-form button[type='submit']").count() == 1


def test_save_coaching_profile(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("textarea[name='profile']", "I run 60 miles per week.")
    page.click(SAVE)
    page.wait_for_load_state("networkidle")
    assert "profile saved" in page.content().lower()


def test_profile_text_persists(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("textarea[name='profile']", "Persistent profile text.")
    page.click(SAVE)
    page.wait_for_load_state("networkidle")

    page.goto(f"{server_url}/athlete-profile")
    assert "Persistent profile text." in page.locator("textarea[name='profile']").input_value()


def test_profile_and_race_goal_saved_together(logged_in_page, server_url):
    """Issue #61: editing the profile and race goal, then saving, keeps both."""
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("textarea[name='profile']", "Edited alongside race goal.")
    page.fill("input[name='race_date']", "2099-05-10")
    page.select_option("select[name='race_distance']", "Half Marathon")
    page.click(SAVE)
    page.wait_for_load_state("networkidle")

    page.goto(f"{server_url}/athlete-profile")
    assert page.locator("textarea[name='profile']").input_value() == "Edited alongside race goal."
    assert page.locator("input[name='race_date']").input_value() == "2099-05-10"
    assert page.locator("select[name='race_distance']").input_value() == "Half Marathon"


def test_save_race_goal_valid(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("input[name='race_date']", "2099-04-26")
    page.select_option("select[name='race_distance']", "Marathon")
    page.click(SAVE)
    page.wait_for_load_state("networkidle")
    assert "marathon" in page.content().lower()


def test_race_goal_past_date_rejected_keeps_edits(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("textarea[name='profile']", "Unsaved edit survives error.")
    page.fill("input[name='race_date']", "2020-01-01")
    page.select_option("select[name='race_distance']", "Marathon")
    page.click(SAVE)
    page.wait_for_load_state("networkidle")
    assert "future" in page.content().lower()
    assert page.locator("textarea[name='profile']").input_value() == "Unsaved edit survives error."


def test_clear_race_goal(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("input[name='race_date']", "2099-06-01")
    page.select_option("select[name='race_distance']", "10K")
    page.click(SAVE)
    page.wait_for_load_state("networkidle")

    page.goto(f"{server_url}/athlete-profile")
    page.click("#clear-race-goal")
    assert page.locator("input[name='race_date']").input_value() == ""
    page.click(SAVE)
    page.wait_for_load_state("networkidle")

    page.goto(f"{server_url}/athlete-profile")
    assert page.locator("input[name='race_date']").input_value() == ""
    assert page.locator("select[name='race_distance']").input_value() == ""


def test_save_display_name(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/athlete-profile")
    page.fill("input[name='display_name']", "Test Athlete")
    page.click(SAVE)
    page.wait_for_load_state("networkidle")
    assert "Test Athlete" in page.content()
