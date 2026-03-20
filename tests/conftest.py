"""Shared pytest fixtures for RunCoach tests."""

from __future__ import annotations

import pytest
from pathlib import Path
from runcoach.config import Config
from runcoach.db import RunCoachDB


@pytest.fixture
def sample_fit_file():
    """Path to a small sample FIT file."""
    return Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")


@pytest.fixture
def sample_yaml_file():
    """Path to a sample parsed YAML file."""
    return Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.yaml")


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    db = RunCoachDB(db_path)
    # Ensure a default user exists (mirrors production setup)
    from runcoach.auth import hash_password
    db.ensure_default_user("athlete", hash_password("test-password"))
    return db


@pytest.fixture
def test_config(tmp_path):
    """Test configuration with dummy values."""
    return Config(
        openai_api_key="test-key",
        openai_model="gpt-4o",
        data_dir=tmp_path / "data",
        timezone="Europe/London",
        stryd_email="test@example.com",
        stryd_password="test-password",
    )


@pytest.fixture
def mock_openai_client(mocker):
    """Mock OpenAI client that returns predictable responses."""
    mock_response = mocker.Mock()
    mock_response.choices = [mocker.Mock(message=mocker.Mock(content="Test commentary"))]
    mock_response.usage = mocker.Mock(prompt_tokens=100, completion_tokens=50, total_tokens=150)

    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = mock_response

    mocker.patch("runcoach.analyzer.OpenAI", return_value=mock_client)
    return mock_client
