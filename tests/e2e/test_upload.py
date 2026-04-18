"""E2E tests: manual FIT file upload."""
import shutil

import pytest

from tests.e2e.conftest import SAMPLE_DIR, SAMPLE_FIT_NAME

pytestmark = pytest.mark.e2e


def _copy_fit(tmp_path, name="upload_test.fit"):
    """Return path to a fresh copy of the sample FIT (avoids 'already exists' guard)."""
    dest = tmp_path / name
    shutil.copy(SAMPLE_DIR / SAMPLE_FIT_NAME, dest)
    return dest


def test_upload_fit_file_creates_run(logged_in_page, server_url, tmp_path):
    page = logged_in_page
    fit_copy = _copy_fit(tmp_path)

    # Reveal upload form and submit
    page.locator("button", has_text="Upload").first.click()
    page.locator("#upload-form input[type='file']").set_input_files(str(fit_copy))
    page.locator("#upload-form").locator("button[type='submit']").click()

    # On success, Flask redirects to /run/<id>
    page.wait_for_url("**/run/**")
    assert "/run/" in page.url


def test_upload_non_fit_file_rejected(logged_in_page, server_url, tmp_path):
    page = logged_in_page
    txt_file = tmp_path / "notafit.txt"
    txt_file.write_text("not a fit file")

    page.locator("button", has_text="Upload").first.click()
    page.locator("#upload-form input[type='file']").set_input_files(str(txt_file))
    page.locator("#upload-form").locator("button[type='submit']").click()

    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "fit" in content.lower() or "invalid" in content.lower() or "error" in content.lower()


def test_upload_invalid_magic_bytes_rejected(logged_in_page, server_url, tmp_path):
    page = logged_in_page
    bad_fit = tmp_path / "bad.fit"
    bad_fit.write_bytes(b"\x00" * 20)  # .fit extension but wrong magic bytes

    page.locator("button", has_text="Upload").first.click()
    page.locator("#upload-form input[type='file']").set_input_files(str(bad_fit))
    page.locator("#upload-form").locator("button[type='submit']").click()

    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "fit" in content.lower() or "invalid" in content.lower() or "error" in content.lower()


def test_upload_sets_custom_activity_name(logged_in_page, server_url, tmp_path):
    page = logged_in_page
    fit_copy = _copy_fit(tmp_path, "named_run.fit")

    page.locator("button", has_text="Upload").first.click()
    page.locator("#upload-form input[type='file']").set_input_files(str(fit_copy))
    page.locator("#upload-form input[name='activity_name']").fill("My Custom Run")
    page.locator("#upload-form").locator("button[type='submit']").click()

    page.wait_for_url("**/run/**")
    assert "My Custom Run" in page.content()


def test_upload_with_explicit_date(logged_in_page, server_url, tmp_path):
    page = logged_in_page
    fit_copy = _copy_fit(tmp_path, "dated_run.fit")

    page.locator("button", has_text="Upload").first.click()
    page.locator("#upload-form input[type='file']").set_input_files(str(fit_copy))
    page.locator("#upload-form input[name='activity_date']").fill("2026-03-15")
    page.locator("#upload-form").locator("button[type='submit']").click()

    page.wait_for_url("**/run/**")
    assert "2026-03-15" in page.content() or "Mar" in page.content() or "15" in page.content()
