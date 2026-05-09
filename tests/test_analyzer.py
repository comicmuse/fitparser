"""Unit tests for runcoach.analyzer module."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import yaml

from runcoach.analyzer import (
    analyze_run,
    analyze_and_write,
    _load_athlete_profile,
    _load_schema,
    _call_claude,
    _call_ollama,
)
from runcoach.config import Config


class TestLoadAthleteProfile:
    """Tests for loading athlete profile."""

    def test_load_athlete_profile_with_db(self, temp_db):
        """Test loading profile from database."""
        user_id = temp_db.get_default_user_id()
        assert user_id is not None
        temp_db.update_athlete_profile(user_id, "My custom athlete profile")

        profile = _load_athlete_profile(temp_db, user_id=user_id)
        assert profile == "My custom athlete profile"

    def test_load_athlete_profile_no_db(self):
        """Test loading profile without database returns empty string."""
        profile = _load_athlete_profile(None)
        assert profile == ""

    def test_load_athlete_profile_empty_profile(self, temp_db):
        """Test loading profile when profile is empty in DB."""
        user_id = temp_db.get_default_user_id()
        temp_db.update_athlete_profile(user_id, "")

        profile = _load_athlete_profile(temp_db, user_id=user_id)
        assert profile == ""


class TestLoadSchema:
    """Tests for loading workout schema."""

    def test_load_schema_default(self):
        """Test loading schema from default location."""
        schema = _load_schema()
        # Should return a string (JSON)
        assert isinstance(schema, str)
        # Should be valid JSON (or empty)
        if schema:
            import json
            try:
                json.loads(schema)
            except json.JSONDecodeError:
                pytest.fail("Schema is not valid JSON")

    def test_load_schema_custom_root(self, tmp_path):
        """Test loading schema from custom project root."""
        schema_path = tmp_path / "workout_yaml_schema.json"
        schema_path.write_text('{"test": "schema"}')

        schema = _load_schema(tmp_path)
        assert '{"test": "schema"}' in schema


class TestAnalyzeRun:
    """Tests for the analyze_run function."""

    def test_analyze_run_basic(self, test_config, mock_openai_client):
        """Test basic run analysis."""
        yaml_content = """
date: '2026-03-01'
name: Test Run
distance_km: 10.0
duration_min: 50.0
avg_power: 200
avg_hr: 150
"""

        result = analyze_run(yaml_content, test_config)

        assert "commentary" in result
        assert "prompt_tokens" in result
        assert "completion_tokens" in result

        # Check mock was called
        mock_openai_client.chat.completions.create.assert_called_once()

        # Verify the call structure
        call_args = mock_openai_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == test_config.openai_model

        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert yaml_content in messages[1]["content"]

    def test_analyze_run_with_context(self, test_config, mock_openai_client):
        """Test run analysis with training context."""
        yaml_content = """
date: '2026-03-01'
name: Test Run
distance_km: 10.0
"""

        context_yaml = """
training_context:
  period: '2026-02-23 to 2026-02-29'
  summary:
    total_runs: 3
    total_distance_km: 25.0
"""

        result = analyze_run(yaml_content, test_config, context_yaml=context_yaml)

        # Check that context was prepended
        call_args = mock_openai_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]

        assert context_yaml.strip() in user_msg
        assert "---" in user_msg
        assert yaml_content in user_msg

    def test_analyze_run_manual_upload(self, test_config, mock_openai_client):
        """Manual upload flag triggers special system prompt note."""
        yaml_content = "date: '2026-03-01'\nname: Manual Upload\ndistance_km: 10.0\n"

        result = analyze_run(yaml_content, test_config, is_manual_upload=True)

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        assert "manual upload" in system_msg.lower()
        assert "power data" in system_msg.lower()

    def test_analyze_run_prompt_construction(self, test_config, mock_openai_client):
        """Test that prompt is constructed correctly."""
        yaml_content = "date: '2026-03-01'"

        result = analyze_run(yaml_content, test_config)

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        # Check for key prompt elements
        assert "running trainer" in system_msg.lower()
        assert "YAML" in system_msg
        assert "training context" in system_msg.lower()

    def test_analyze_run_returns_tokens(self, test_config, mock_openai_client):
        """Test that token counts are returned."""
        yaml_content = "date: '2026-03-01'"

        result = analyze_run(yaml_content, test_config)

        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
        assert result["commentary"] == "Test commentary"


class TestAnalyzeAndWrite:
    """Tests for the analyze_and_write function."""

    def _make_run(self, data: dict | None = None) -> dict:
        import json as _json
        if data is None:
            data = {"date": "2026-03-01", "name": "Test Run", "distance_km": 10.0}
        return {
            "id": 1,
            "date": data.get("date", "2026-03-01"),
            "is_manual_upload": 0,
            "parsed_data": _json.dumps(data),
        }

    def test_analyze_and_write_returns_result_dict(self, test_config, mock_openai_client):
        """analyze_and_write returns a dict, not a tuple."""
        run = self._make_run()
        result = analyze_and_write(run, test_config, db=None)
        assert isinstance(result, dict)
        assert "commentary" in result
        assert "prompt_tokens" in result

    def test_analyze_and_write_no_md_file(self, test_config, mock_openai_client, tmp_path):
        """analyze_and_write does not write a .md file."""
        run = self._make_run()
        analyze_and_write(run, test_config, db=None)
        # No .md files should exist anywhere in tmp_path
        assert list(tmp_path.rglob("*.md")) == []

    def test_analyze_and_write_raises_without_parsed_data(self, test_config, mock_openai_client):
        """analyze_and_write raises ValueError when both parsed_data and yaml_path are missing."""
        run = {"id": 99, "date": "2026-03-01", "is_manual_upload": 0, "parsed_data": None, "yaml_path": None}
        with pytest.raises(ValueError, match="no parsed_data"):
            analyze_and_write(run, test_config, db=None)

    def test_analyze_and_write_manual_upload_flag(self, test_config, mock_openai_client):
        """is_manual_upload from the run dict controls the manual upload note in the system prompt."""
        import json as _json
        run = {
            "id": 2,
            "date": "2026-03-01",
            "is_manual_upload": 1,
            "parsed_data": _json.dumps({"date": "2026-03-01", "name": "Manual"}),
        }
        analyze_and_write(run, test_config, db=None)
        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "manual upload" in system_msg.lower()

    def test_analyze_and_write_with_context(self, test_config, mock_openai_client, temp_db, tmp_path):
        """analyze_and_write passes training context to the LLM when db is provided."""
        import json as _json
        test_config.data_dir = tmp_path
        run = {
            "id": 3,
            "date": "2026-03-01",
            "is_manual_upload": 0,
            "parsed_data": _json.dumps({
                "date": "2026-03-01",
                "name": "Test",
                "distance_km": 10.0,
                "duration_min": 50.0,
                "avg_power": 200,
                "critical_power": 250,
            }),
        }
        analyze_and_write(run, test_config, db=temp_db, user_id=1)
        # LLM was called
        mock_openai_client.chat.completions.create.assert_called_once()


class TestAnalyzerIntegration:
    """Integration tests for the analyzer module."""

    def test_full_analysis_workflow(self, test_config, mock_openai_client, tmp_path, sample_yaml_file):
        """Test complete analysis workflow with real YAML structure."""
        import json as _json
        if not sample_yaml_file.exists():
            pytest.skip(f"Sample YAML file not found: {sample_yaml_file}")

        # Load the sample YAML and build a run dict with parsed_data
        sample_data = yaml.safe_load(sample_yaml_file.read_text(encoding="utf-8"))
        run = {
            "id": 1,
            "date": sample_data.get("date", "2026-03-01"),
            "is_manual_upload": 0,
            "parsed_data": _json.dumps(sample_data),
        }

        # Analyze it
        result = analyze_and_write(run, test_config, db=None)

        # Verify output
        assert result["commentary"] is not None
        assert result["prompt_tokens"] > 0
        assert result["completion_tokens"] > 0

        # Verify the actual YAML was sent to OpenAI
        call_args = mock_openai_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]

        # Should contain workout data from the sample
        assert "distance_km" in user_msg or "duration_min" in user_msg


class TestLLMProviderSelection:
    """Tests for multi-provider configuration and dispatch."""

    def test_single_openai_provider(self, tmp_path):
        cfg = Config(openai_api_key="sk-test", data_dir=tmp_path)
        assert cfg.llm_provider == "openai"

    def test_single_claude_provider(self, tmp_path):
        cfg = Config(anthropic_api_key="sk-ant-test", data_dir=tmp_path)
        assert cfg.llm_provider == "claude"

    def test_single_ollama_provider(self, tmp_path):
        cfg = Config(ollama_base_url="http://localhost:11434", data_dir=tmp_path)
        assert cfg.llm_provider == "ollama"

    def test_no_provider_defaults_to_openai(self, tmp_path):
        cfg = Config(data_dir=tmp_path)
        assert cfg.llm_provider == "openai"

    def test_multiple_providers_defaults_to_openai_with_warning(self, tmp_path, caplog):
        import logging
        cfg = Config(
            openai_api_key="sk-test",
            anthropic_api_key="sk-ant-test",
            data_dir=tmp_path,
        )
        with caplog.at_level(logging.WARNING, logger="runcoach.config"):
            provider = cfg.llm_provider
        assert provider == "openai"
        assert "MULTIPLE LLM PROVIDERS" in caplog.text
        assert "openai" in caplog.text
        assert "claude" in caplog.text

    def test_all_three_providers_warns_and_uses_openai(self, tmp_path, caplog):
        import logging
        cfg = Config(
            openai_api_key="sk-test",
            anthropic_api_key="sk-ant-test",
            ollama_base_url="http://localhost:11434",
            data_dir=tmp_path,
        )
        with caplog.at_level(logging.WARNING, logger="runcoach.config"):
            provider = cfg.llm_provider
        assert provider == "openai"
        assert "ollama" in caplog.text


class TestClaudeProvider:
    """Tests for the Claude/Anthropic LLM backend."""

    def test_analyze_run_uses_claude(self, claude_config, mock_anthropic_client):
        yaml_content = "date: '2026-03-01'\nname: Test Run\n"
        result = analyze_run(yaml_content, claude_config)

        assert result["commentary"] == "Test commentary"
        assert result["prompt_tokens"] == 80
        assert result["completion_tokens"] == 40
        mock_anthropic_client.messages.create.assert_called_once()

    def test_claude_passes_system_and_user_messages(self, claude_config, mock_anthropic_client):
        yaml_content = "date: '2026-03-01'\nname: Test Run\n"
        analyze_run(yaml_content, claude_config)

        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-6"
        assert "running trainer" in call_kwargs["system"].lower()
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"
        assert yaml_content in call_kwargs["messages"][0]["content"]

    def test_claude_missing_package_raises_import_error(self, claude_config, mocker):
        mocker.patch.dict("sys.modules", {"anthropic": None})
        with pytest.raises(ImportError, match="anthropic"):
            _call_claude("system", "user", claude_config)


class TestOllamaProvider:
    """Tests for the Ollama LLM backend."""

    def test_analyze_run_uses_ollama(self, ollama_config, mock_openai_client):
        yaml_content = "date: '2026-03-01'\nname: Test Run\n"
        result = analyze_run(yaml_content, ollama_config)

        assert result["commentary"] == "Test commentary"
        mock_openai_client.chat.completions.create.assert_called_once()

    def test_ollama_uses_correct_base_url(self, ollama_config, mocker):
        captured = {}

        def fake_openai(base_url=None, api_key=None):
            captured["base_url"] = base_url
            captured["api_key"] = api_key
            mock_response = mocker.Mock()
            mock_response.choices = [mocker.Mock(message=mocker.Mock(content="ok"))]
            mock_response.usage = mocker.Mock(prompt_tokens=10, completion_tokens=5)
            mock_client = mocker.Mock()
            mock_client.chat.completions.create.return_value = mock_response
            return mock_client

        mocker.patch("runcoach.analyzer.OpenAI", side_effect=fake_openai)
        _call_ollama("system", "user", ollama_config)

        assert captured["base_url"] == "http://localhost:11434/v1"
        assert captured["api_key"] == "ollama"

    def test_ollama_uses_configured_model(self, ollama_config, mock_openai_client):
        yaml_content = "date: '2026-03-01'\nname: Test Run\n"
        analyze_run(yaml_content, ollama_config)

        call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "llama3.2"

    def test_ollama_strips_trailing_slash_from_base_url(self, mocker, tmp_path):
        cfg = Config(
            ollama_base_url="http://localhost:11434/",
            ollama_model="mistral",
            data_dir=tmp_path,
        )
        captured = {}

        def fake_openai(base_url=None, api_key=None):
            captured["base_url"] = base_url
            mock_response = mocker.Mock()
            mock_response.choices = [mocker.Mock(message=mocker.Mock(content="ok"))]
            mock_response.usage = mocker.Mock(prompt_tokens=1, completion_tokens=1)
            mock_client = mocker.Mock()
            mock_client.chat.completions.create.return_value = mock_response
            return mock_client

        mocker.patch("runcoach.analyzer.OpenAI", side_effect=fake_openai)
        _call_ollama("system", "user", cfg)
        assert captured["base_url"] == "http://localhost:11434/v1"


class TestTrainingPhase:
    """Tests for the _training_phase function."""

    def test_base_building(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(17 * 7) == "Base Building"
        assert _training_phase(16 * 7 + 1) == "Base Building"

    def test_build_phase(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(16 * 7) == "Build Phase"
        assert _training_phase(8 * 7 + 1) == "Build Phase"

    def test_peak_training(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(8 * 7) == "Peak Training"
        assert _training_phase(2 * 7 + 1) == "Peak Training"

    def test_taper(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(2 * 7) == "Taper"
        assert _training_phase(8) == "Taper"

    def test_race_week(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(7) == "Race Week"
        assert _training_phase(0) == "Race Week"

    def test_recovery(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(-1) == "Recovery"
        assert _training_phase(-28) == "Recovery"

    def test_post_race(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(-29) == "Post-race"


class TestBuildChatContext:
    def _make_run(self, data: dict | None = None, is_manual: int = 0) -> dict:
        import json as _json
        if data is None:
            data = {"date": "2026-04-01", "critical_power": 200, "blocks": []}
        return {
            "id": 1,
            "date": data.get("date", "2026-04-01"),
            "is_manual_upload": is_manual,
            "parsed_data": _json.dumps(data),
        }

    def test_returns_system_and_user_message(self, tmp_path):
        from unittest.mock import MagicMock
        from runcoach.analyzer import build_chat_context
        from runcoach.config import Config

        run = self._make_run()
        config = Config(data_dir=tmp_path)
        db = MagicMock()
        db.get_athlete_profile.return_value = "Test athlete profile"
        db.get_race_goal.return_value = {"race_date": None, "race_distance": None}

        with patch("runcoach.analyzer._build_context_yaml", return_value=None):
            system_msg, user_msg = build_chat_context(
                run=run,
                user_id=1,
                history=[],
                new_message="What was my average power?",
                config=config,
                db=db,
            )

        assert isinstance(system_msg, str)
        assert "Test athlete profile" in system_msg
        assert "Athlete: What was my average power?" in user_msg

    def test_history_included_in_user_message(self, tmp_path):
        from unittest.mock import MagicMock
        from runcoach.analyzer import build_chat_context
        from runcoach.config import Config

        run = self._make_run()
        config = Config(data_dir=tmp_path)
        db = MagicMock()
        db.get_athlete_profile.return_value = ""
        db.get_race_goal.return_value = {"race_date": None, "race_distance": None}

        history = [
            {"role": "user", "message": "How was my heart rate?"},
            {"role": "assistant", "message": "Your HR averaged 145 bpm."},
        ]

        with patch("runcoach.analyzer._build_context_yaml", return_value=None):
            _, user_msg = build_chat_context(
                run=run, user_id=1, history=history,
                new_message="And my power?", config=config, db=db,
            )

        assert "How was my heart rate?" in user_msg
        assert "Your HR averaged 145 bpm." in user_msg
        assert "And my power?" in user_msg
        assert user_msg.index("Athlete: How was my heart rate?") < user_msg.index("Coach: Your HR averaged 145 bpm.") < user_msg.index("Athlete: And my power?")

    def test_manual_upload_flag_in_system_prompt(self, tmp_path):
        from unittest.mock import MagicMock
        from runcoach.analyzer import build_chat_context
        from runcoach.config import Config

        run = self._make_run(is_manual=1)
        config = Config(data_dir=tmp_path)
        db = MagicMock()
        db.get_athlete_profile.return_value = ""
        db.get_race_goal.return_value = {"race_date": None, "race_distance": None}

        with patch("runcoach.analyzer._build_context_yaml", return_value=None):
            system_msg, _ = build_chat_context(
                run=run, user_id=1, history=[], new_message="Test", config=config, db=db
            )

        assert "manually uploaded" in system_msg.lower()

    def test_raises_when_parsed_data_missing(self):
        from unittest.mock import MagicMock, patch
        from runcoach.analyzer import build_chat_context
        from runcoach.config import Config
        import pytest

        run = {"id": 1, "date": "2026-04-01", "parsed_data": None, "yaml_path": None, "is_manual_upload": 0}
        db = MagicMock()
        db.get_athlete_profile.return_value = ""
        db.get_race_goal.return_value = {"race_date": None, "race_distance": None}

        with pytest.raises(ValueError, match="parsed_data"):
            build_chat_context(run=run, user_id=1, history=[], new_message="Q", config=MagicMock(), db=db)

    def test_context_yaml_included_when_available(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from runcoach.analyzer import build_chat_context
        from runcoach.config import Config

        run = self._make_run()
        config = Config(data_dir=tmp_path)
        db = MagicMock()
        db.get_athlete_profile.return_value = ""
        db.get_race_goal.return_value = {"race_date": None, "race_distance": None}

        fake_context = "atl: 45.0\nctl: 50.0\n"
        with patch("runcoach.analyzer._build_context_yaml", return_value=fake_context):
            _, user_msg = build_chat_context(
                run=run, user_id=1, history=[], new_message="Test question",
                config=config, db=db,
            )

        assert "atl: 45.0" in user_msg
        assert "---" in user_msg
        assert "Test question" in user_msg


class TestAnalyzeRunWithRaceContext:
    """Tests for race context injection in analyze_run."""

    def test_race_context_included_when_goal_set(self, test_config, mock_openai_client, temp_db):
        """Race context appears in system prompt when race goal is set."""
        user_id = temp_db.get_default_user_id()
        temp_db.update_race_goal(user_id, "2026-10-04", "Marathon")

        yaml_content = "date: '2026-04-15'\nname: Test Run\n"
        analyze_run(yaml_content, test_config, db=temp_db, run_date="2026-04-15", user_id=user_id)

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        assert "Marathon" in system_msg
        assert "2026-10-04" in system_msg
        assert "training phase" in system_msg.lower()

    def test_race_context_omitted_when_no_goal(self, test_config, mock_openai_client, temp_db):
        """Race context block is absent when no race goal is set."""
        yaml_content = "date: '2026-04-15'\nname: Test Run\n"
        analyze_run(yaml_content, test_config, db=temp_db, run_date="2026-04-15")

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        assert "Current race goal" not in system_msg

    def test_race_context_omitted_when_no_db(self, test_config, mock_openai_client):
        """Race context is absent when no DB is provided."""
        yaml_content = "date: '2026-04-15'\nname: Test Run\n"
        analyze_run(yaml_content, test_config, db=None, run_date="2026-04-15")

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        assert "Current race goal" not in system_msg

    def test_race_context_days_calculation(self, test_config, mock_openai_client, temp_db):
        """Correct days until race are computed and included."""
        user_id = temp_db.get_default_user_id()
        temp_db.update_race_goal(user_id, "2026-05-15", "Half Marathon")

        yaml_content = "date: '2026-04-15'\nname: Test Run\n"
        analyze_run(yaml_content, test_config, db=temp_db, run_date="2026-04-15")

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        # 30 days from 2026-04-15 to 2026-05-15
        assert "30" in system_msg

    def test_malformed_race_date_does_not_crash(self, test_config, mock_openai_client, temp_db):
        """Malformed race_date in DB is silently ignored."""
        user_id = temp_db.get_default_user_id()
        # Force a bad value directly into the DB
        with temp_db._connect() as conn:
            conn.execute(
                "UPDATE users SET race_date = ?, race_distance = ? WHERE id = ?",
                ("not-a-date", "Marathon", user_id),
            )

        yaml_content = "date: '2026-04-15'\nname: Test Run\n"
        result = analyze_run(yaml_content, test_config, db=temp_db, run_date="2026-04-15")

        assert result["commentary"] == "Test commentary"
        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "Current race goal" not in system_msg
