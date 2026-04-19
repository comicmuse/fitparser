"""E2E tests: admin user management screen."""
import pytest

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

def test_admin_page_accessible_to_admin(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/admin/users")
    assert page.url == f"{server_url}/admin/users"
    assert page.locator("table").is_visible()


def test_admin_page_blocked_for_regular_user(regular_user_page, server_url):
    page = regular_user_page
    page.goto(f"{server_url}/admin/users")
    # Should be redirected away (to / or /login) — not allowed to stay on admin page
    assert "/admin/users" not in page.url


def test_admin_nav_link_visible_to_admin(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/")
    assert page.locator("a[href*='/admin/users']").is_visible()


def test_admin_nav_link_hidden_from_regular_user(regular_user_page, server_url):
    page = regular_user_page
    page.goto(f"{server_url}/")
    assert not page.locator("a[href*='/admin/users']").is_visible()


# ---------------------------------------------------------------------------
# Users shown in table
# ---------------------------------------------------------------------------

def test_admin_page_lists_users(logged_in_page, server_url, regular_user):
    page = logged_in_page
    page.goto(f"{server_url}/admin/users")
    content = page.content()
    assert "athlete" in content
    assert regular_user["username"] in content


def test_admin_shows_admin_badge_for_admin_user(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/admin/users")
    assert page.locator(".badge-blue", has_text="admin").count() >= 1


# ---------------------------------------------------------------------------
# Deactivate / reactivate
# ---------------------------------------------------------------------------

def test_deactivate_user_blocks_login(logged_in_page, server_url, deactivation_victim, page):
    admin = logged_in_page
    admin.goto(f"{server_url}/admin/users")
    # Find the deactivate button for this user's row
    row = admin.locator("tr", has_text=deactivation_victim["username"])
    row.locator("button", has_text="Deactivate").click()
    admin.wait_for_load_state("networkidle")

    # Now try to log in as that user in a fresh page
    page.goto(f"{server_url}/login")
    page.fill("input[name='username']", deactivation_victim["username"])
    page.fill("input[name='password']", deactivation_victim["password"])
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    assert "/login" in page.url
    assert "deactivated" in page.content().lower()


def test_reactivate_user_restores_login(logged_in_page, server_url, deactivation_victim, page):
    admin = logged_in_page
    admin.goto(f"{server_url}/admin/users")

    # Deactivate first (victim fixture resets to active, so we deactivate here)
    row = admin.locator("tr", has_text=deactivation_victim["username"])
    if row.locator("button", has_text="Deactivate").count() > 0:
        row.locator("button", has_text="Deactivate").click()
        admin.wait_for_load_state("networkidle")
        admin.goto(f"{server_url}/admin/users")

    # Reactivate
    row = admin.locator("tr", has_text=deactivation_victim["username"])
    row.locator("button", has_text="Reactivate").click()
    admin.wait_for_load_state("networkidle")

    # Victim should now be able to log in
    page.goto(f"{server_url}/login")
    page.fill("input[name='username']", deactivation_victim["username"])
    page.fill("input[name='password']", deactivation_victim["password"])
    page.click("button[type='submit']")
    page.wait_for_url(f"{server_url}/")
    assert page.url == f"{server_url}/"


# ---------------------------------------------------------------------------
# Promote / demote
# ---------------------------------------------------------------------------

def test_promote_and_demote_user(logged_in_page, server_url, regular_user):
    page = logged_in_page
    page.goto(f"{server_url}/admin/users")

    row = page.locator("tr", has_text=regular_user["username"])
    row.locator("button", has_text="Make admin").click()
    page.wait_for_load_state("networkidle")

    # User should now show admin badge
    row = page.locator("tr", has_text=regular_user["username"])
    assert row.locator(".badge-blue", has_text="admin").count() == 1

    # Demote them again
    row.locator("button", has_text="Remove admin").click()
    page.wait_for_load_state("networkidle")

    row = page.locator("tr", has_text=regular_user["username"])
    assert row.locator(".badge-blue", has_text="admin").count() == 0


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_wrong_username_does_not_delete(logged_in_page, server_url, deletion_victim):
    page = logged_in_page
    page.goto(f"{server_url}/admin/users")

    row = page.locator("tr", has_text=deletion_victim["username"])
    row.locator("button", has_text="Delete").click()

    page.fill("input[name='confirm_username']", "wrong_username")
    page.locator("#delete-form button[type='submit']").click()
    page.wait_for_load_state("networkidle")

    # User still exists — their row is still in the table
    assert page.locator("tr", has_text=deletion_victim["username"]).count() > 0


def test_delete_user_with_correct_confirmation(logged_in_page, server_url, deletion_victim):
    page = logged_in_page
    page.goto(f"{server_url}/admin/users")

    row = page.locator("tr", has_text=deletion_victim["username"])
    row.locator("button", has_text="Delete").click()

    page.fill("input[name='confirm_username']", deletion_victim["username"])
    page.locator("#delete-form button[type='submit']").click()
    page.wait_for_load_state("networkidle")

    # Navigate back to clear flash message, confirm row is gone from table
    page.goto(f"{server_url}/admin/users")
    assert page.locator("tr", has_text=deletion_victim["username"]).count() == 0
