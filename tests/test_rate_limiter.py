"""Unit tests for the LLM rate limiter."""
from __future__ import annotations

import pytest
from pathlib import Path
from runcoach.db import RunCoachDB
from runcoach.auth import hash_password
from runcoach.rate_limiter import check_and_consume


@pytest.fixture
def db(tmp_path):
    _db = RunCoachDB(tmp_path / "test.db")
    _db.ensure_default_user("athlete", hash_password("pw"))
    return _db


@pytest.fixture
def user_id(db):
    return db.get_default_user_id()


def _enable_limiting(db, limit: int = 5) -> None:
    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", str(limit))


def _make_non_admin(db, user_id: int) -> None:
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))


class TestCheckAndConsume:
    def test_allowed_when_limiting_disabled(self, db, user_id):
        # Default: limiting is off
        _make_non_admin(db, user_id)
        allowed, msg = check_and_consume(db, user_id)
        assert allowed is True
        assert msg is None

    def test_allowed_for_admin_regardless_of_count(self, db, user_id):
        _enable_limiting(db, limit=0)
        # Default user is admin — should always be allowed
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        allowed, msg = check_and_consume(db, user_id)
        assert allowed is True
        assert msg is None

    def test_allowed_under_limit_and_increments(self, db, user_id):
        _enable_limiting(db, limit=3)
        _make_non_admin(db, user_id)
        allowed, msg = check_and_consume(db, user_id)
        assert allowed is True
        assert msg is None

    def test_denied_at_limit_with_reset_message(self, db, user_id):
        _enable_limiting(db, limit=1)
        _make_non_admin(db, user_id)
        # Use up the one allowed call
        check_and_consume(db, user_id)
        # Second call should be denied
        allowed, msg = check_and_consume(db, user_id)
        assert allowed is False
        assert msg is not None
        assert "Daily analysis limit reached" in msg
        assert "00:00 UTC" in msg
        assert "in " in msg

    def test_denied_with_limit_zero(self, db, user_id):
        _enable_limiting(db, limit=0)
        _make_non_admin(db, user_id)
        allowed, msg = check_and_consume(db, user_id)
        assert allowed is False
        assert msg is not None

    def test_per_user_override_takes_precedence(self, db, user_id):
        _enable_limiting(db, limit=1)  # global limit = 1
        _make_non_admin(db, user_id)
        # Give user a higher personal limit
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET llm_daily_limit = 3 WHERE id = ?", (user_id,)
            )
        check_and_consume(db, user_id)
        check_and_consume(db, user_id)
        allowed, _ = check_and_consume(db, user_id)
        assert allowed is True  # 3rd call within personal limit of 3

    def test_no_usage_row_written_when_disabled(self, db, user_id):
        _make_non_admin(db, user_id)
        # Limiting disabled — no row should be written
        check_and_consume(db, user_id)
        with db._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0]
        assert count == 0

    def test_no_usage_row_written_for_admin(self, db, user_id):
        _enable_limiting(db, limit=5)
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        check_and_consume(db, user_id)
        with db._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0]
        assert count == 0
