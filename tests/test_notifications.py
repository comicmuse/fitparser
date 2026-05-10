"""Tests for runcoach.notifications — FCM push notification sender."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.auth import hash_password


@pytest.fixture
def db_with_token(tmp_path):
    db = RunCoachDB(tmp_path / "db" / "runcoach.db")
    db.ensure_default_user("athlete", hash_password("x"))
    user_id = db.get_default_user_id()
    db.upsert_device_token(user_id, "device-token-111", "android")
    return db, user_id


@pytest.fixture
def fcm_config(tmp_path):
    fake_sa = tmp_path / "sa.json"
    fake_sa.write_text("{}")
    return Config(
        openai_api_key="test",
        data_dir=tmp_path / "data",
        fcm_service_account_path=str(fake_sa),
    )


class TestSendAnalysisNotification:
    def test_returns_zero_when_fcm_not_configured(self, tmp_path):
        from runcoach.notifications import send_analysis_notification
        db = RunCoachDB(tmp_path / "db" / "runcoach.db")
        db.ensure_default_user("athlete", hash_password("x"))
        user_id = db.get_default_user_id()
        config = Config(data_dir=tmp_path / "data")  # no fcm path

        result = send_analysis_notification(1, "Morning Run", user_id, db, config)
        assert result == 0

    def test_returns_zero_when_no_tokens_registered(self, tmp_path, fcm_config):
        from runcoach.notifications import send_analysis_notification
        db = RunCoachDB(tmp_path / "db" / "runcoach.db")
        db.ensure_default_user("athlete", hash_password("x"))
        user_id = db.get_default_user_id()

        result = send_analysis_notification(42, "Evening Run", user_id, db, fcm_config)
        assert result == 0

    def test_returns_zero_when_firebase_not_available(self, db_with_token, fcm_config):
        from runcoach.notifications import send_analysis_notification
        db, user_id = db_with_token

        with patch("runcoach.notifications._FIREBASE_AVAILABLE", False):
            result = send_analysis_notification(1, "Run", user_id, db, fcm_config)
        assert result == 0

    def test_sends_to_registered_token(self, db_with_token, fcm_config):
        from runcoach.notifications import send_analysis_notification
        db, user_id = db_with_token

        with patch("runcoach.notifications._init_firebase_app"), \
             patch("runcoach.notifications.messaging") as mock_messaging:
            mock_messaging.send.return_value = "projects/x/messages/123"
            result = send_analysis_notification(7, "Long Run", user_id, db, fcm_config)

        assert result == 1
        mock_messaging.send.assert_called_once()
        sent_msg = mock_messaging.send.call_args[0][0]
        assert sent_msg.data["run_id"] == "7"
        assert sent_msg.token == "device-token-111"
        assert sent_msg.notification.title == "New Analysis Ready"

    def test_removes_stale_token_on_unregistered_error(self, db_with_token, fcm_config):
        from runcoach.notifications import send_analysis_notification
        import firebase_admin.messaging as real_messaging
        db, user_id = db_with_token

        with patch("runcoach.notifications._init_firebase_app"), \
             patch("runcoach.notifications.messaging") as mock_messaging:
            mock_messaging.UnregisteredError = real_messaging.UnregisteredError
            mock_messaging.send.side_effect = real_messaging.UnregisteredError("stale")
            result = send_analysis_notification(7, "Run", user_id, db, fcm_config)

        assert result == 0
        assert db.get_device_tokens_for_user(user_id) == []
