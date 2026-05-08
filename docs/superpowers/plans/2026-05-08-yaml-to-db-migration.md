# YAML → DB Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace YAML files as the storage layer for parsed workout data; the `runs.parsed_data` JSON column becomes the single source of truth, with zero changes to the mobile API surface.

**Architecture:** New `parsed_data TEXT` column stores `json.dumps()` of `build_blocks_from_fit()` output. Parse callers stop writing YAML and write JSON instead. Analyzers reconstruct YAML strings from the JSON for the LLM prompt (identical format). A one-shot `runcoach-migrate` command back-fills historical runs from existing YAML files. YAML and MD files are left on disk; `yaml_path` and `md_path` columns are left in the schema for a follow-up cleanup PR.

**Tech Stack:** Python 3.11+, SQLite, pytest, Flask

---

## Files

- Modify: `runcoach/db.py` — add `parsed_data` column, migration guard, updated method signatures, new `store_parsed_data()`
- Modify: `runcoach/parser.py` — remove `parse_and_write()`, keep `parse_fit_file()`
- Modify: `runcoach/pipeline.py` — use `parse_fit_file()` + JSON in parse stage; pass run dict in analyze stage
- Modify: `runcoach/analyzer.py` — `analyze_and_write(run, ...)`, `build_chat_context` reads `parsed_data`, `analyze_run` reads `is_manual_upload` flag
- Modify: `runcoach/web/api.py` — `format_run_for_api()` reads `parsed_data`, analyze task passes run dict
- Modify: `runcoach/web/routes.py` — manual upload uses `parse_fit_file()`, re-analysis passes run dict, run detail reads `parsed_data`
- Modify: `runcoach/context.py` — read `parsed_data` from DB instead of YAML files on disk
- Modify: `runcoach/cli.py` — rewrite parse/analyze commands, add migrate command
- Modify: `pyproject.toml` — add `runcoach-migrate` entry point
- Modify: `tests/test_db.py` — add column presence test, `update_parsed` with `parsed_data`, `store_parsed_data`
- Modify: `tests/test_parser.py` — remove YAML-writing tests, add `parse_fit_file()` JSON-serialisable test
- Modify: `tests/test_pipeline.py` — update parse stage mock/assertions, update analyze stage mock/assertions
- Modify: `tests/test_analyzer.py` — pass run dict instead of YAML path, assert no `.md` written, assert return is dict not tuple
- Modify: `tests/test_context.py` — use `parsed_data` instead of writing YAML files to disk
- Modify: `tests/test_api.py` — fixtures use `parsed_data`, keep `yaml_data` key assertions
- Modify: `tests/test_web.py` — upload test uses `parsed_data`, run detail test uses `parsed_data`

---

### Task 1: DB layer — add `parsed_data` column and update signatures

Pure DB changes; no call-site behaviour change yet. After this task all existing tests must still pass.

**Files:**
- Modify: `runcoach/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Add `parsed_data` to `SCHEMA_SQL`**

In `runcoach/db.py`, after `stryd_rss REAL,` (line 37) in the `runs` table, add:

```python
    parsed_data TEXT,
```

So the runs block now includes:

```sql
    stryd_rss REAL,
    parsed_data TEXT,
    garmin_connect_id TEXT,
```

- [ ] **Step 2: Add migration guard for existing DBs**

In `_init_schema()`, after `conn.executescript(SCHEMA_SQL)`, add the `ALTER TABLE` guard so existing production databases gain the column on next startup:

```python
def _init_schema(self) -> None:
    with self._connect() as conn:
        conn.executescript(SCHEMA_SQL)
        # Add parsed_data column if upgrading from an older schema.
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "parsed_data" not in existing:
            conn.execute("ALTER TABLE runs ADD COLUMN parsed_data TEXT")
        # Always ensure the first-ever user is an admin (idempotent).
        conn.execute(
            """UPDATE users SET is_admin = 1
               WHERE id = (SELECT MIN(id) FROM users)
               AND NOT EXISTS (SELECT 1 FROM users WHERE is_admin = 1)"""
        )
        # Seed athlete_profile from coach_profile.txt on first startup if blank.
        seed_path = Path(__file__).resolve().parent.parent / "coach_profile.txt"
        try:
            seed_text = seed_path.read_text(encoding="utf-8").strip()
            if seed_text:
                conn.execute(
                    """UPDATE users SET athlete_profile = ?
                       WHERE athlete_profile IS NULL AND id = (SELECT MIN(id) FROM users)""",
                    (seed_text,),
                )
        except FileNotFoundError:
            pass
        except Exception:
            log.exception("Failed to seed athlete_profile from coach_profile.txt")
```

- [ ] **Step 3: Update `update_parsed()` signature**

Replace the current `update_parsed` method (lines 262–278) with:

```python
def update_parsed(
    self,
    run_id: int,
    yaml_path: str | None,
    avg_power_w: float | None,
    avg_hr: int | None,
    workout_name: str | None,
    parsed_data: str | None = None,
) -> None:
    now = _now_iso()
    with self._connect() as conn:
        conn.execute(
            """UPDATE runs
               SET stage='parsed', yaml_path=?, avg_power_w=?,
                   avg_hr=?, workout_name=?, parsed_data=?, parsed_at=?, updated_at=?
               WHERE id=?""",
            (yaml_path, avg_power_w, avg_hr, workout_name, parsed_data, now, now, run_id),
        )
```

- [ ] **Step 4: Update `update_analyzed()` to make `md_path` optional**

Replace the current `update_analyzed` method (lines 280–299) with:

```python
def update_analyzed(
    self,
    run_id: int,
    md_path: str | None = None,
    commentary: str = "",
    model_used: str = "",
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    now = _now_iso()
    with self._connect() as conn:
        conn.execute(
            """UPDATE runs
               SET stage='analyzed', md_path=?, commentary=?,
                   analyzed_at=?, model_used=?,
                   prompt_tokens=?, completion_tokens=?, updated_at=?
               WHERE id=?""",
            (md_path, commentary, now, model_used,
             prompt_tokens, completion_tokens, now, run_id),
        )
```

- [ ] **Step 5: Add `store_parsed_data()` method**

Add this method to `RunCoachDB` after `update_parsed`:

```python
def store_parsed_data(self, run_id: int, parsed_data: str) -> None:
    """Overwrite parsed_data for an existing run (used by migration command)."""
    with self._connect() as conn:
        conn.execute(
            "UPDATE runs SET parsed_data = ? WHERE id = ?",
            (parsed_data, run_id),
        )
```

- [ ] **Step 6: Update `EXPECTED_RUNS_COLUMNS` in test_db.py and add new tests**

In `tests/test_db.py`, update `TestDatabaseStartup.EXPECTED_RUNS_COLUMNS` to include `"parsed_data"`:

```python
EXPECTED_RUNS_COLUMNS = {
    "id", "stryd_activity_id", "name", "date", "distance_m", "moving_time_s",
    "fit_path", "yaml_path", "md_path", "stage", "error_message", "avg_power_w",
    "avg_hr", "workout_name", "commentary", "analyzed_at", "model_used",
    "prompt_tokens", "completion_tokens", "synced_at", "parsed_at",
    "created_at", "updated_at", "is_manual_upload", "stryd_rss", "parsed_data",
    "garmin_connect_id", "strava_activity_id", "strava_map_polyline", "user_id",
}
```

Then append these tests to `TestDatabaseStartup`:

```python
def test_update_parsed_stores_parsed_data(self, tmp_path):
    """update_parsed() stores the JSON blob in parsed_data."""
    import json
    db = RunCoachDB(tmp_path / "test.db")
    db.ensure_default_user("athlete", "hash")
    run_id = db.insert_run(
        stryd_activity_id=1, name="Run", date="2026-05-01",
        fit_path="test.fit", user_id=1,
    )
    payload = json.dumps({"avg_power": 250, "blocks": {}})
    db.update_parsed(
        run_id=run_id,
        yaml_path=None,
        avg_power_w=250,
        avg_hr=140,
        workout_name="Test",
        parsed_data=payload,
    )
    run = db.get_run(run_id)
    assert run["stage"] == "parsed"
    assert run["parsed_data"] == payload

def test_store_parsed_data_overwrites(self, tmp_path):
    """store_parsed_data() replaces the JSON blob for an existing run."""
    import json
    db = RunCoachDB(tmp_path / "test.db")
    db.ensure_default_user("athlete", "hash")
    run_id = db.insert_run(
        stryd_activity_id=2, name="Run2", date="2026-05-02",
        fit_path="test2.fit", user_id=1,
    )
    db.update_parsed(run_id=run_id, yaml_path=None,
                     avg_power_w=None, avg_hr=None, workout_name=None)
    assert db.get_run(run_id)["parsed_data"] is None

    db.store_parsed_data(run_id, json.dumps({"blocks": {}}))
    assert db.get_run(run_id)["parsed_data"] is not None

def test_update_analyzed_md_path_optional(self, tmp_path):
    """update_analyzed() accepts md_path=None without error."""
    db = RunCoachDB(tmp_path / "test.db")
    db.ensure_default_user("athlete", "hash")
    run_id = db.insert_run(
        stryd_activity_id=3, name="Run3", date="2026-05-03",
        fit_path="test3.fit", user_id=1,
    )
    db.update_parsed(run_id=run_id, yaml_path=None,
                     avg_power_w=None, avg_hr=None, workout_name=None)
    db.update_analyzed(run_id=run_id, md_path=None, commentary="Good run",
                       model_used="gpt-4o")
    run = db.get_run(run_id)
    assert run["stage"] == "analyzed"
    assert run["commentary"] == "Good run"
    assert run["md_path"] is None
```

- [ ] **Step 7: Run the tests**

```bash
source .venv/bin/activate
pytest tests/test_db.py -v
```

Expected: all tests PASS including the three new ones.

- [ ] **Step 8: Commit**

```bash
git add runcoach/db.py tests/test_db.py
git commit -m "feat: add parsed_data column and update DB method signatures"
```

---

### Task 2: Update parse callers — write `parsed_data` for new runs

From this point, new runs parsed via the pipeline or manual web upload store their data in `parsed_data`. Historical runs still have `parsed_data = NULL` until the migration command runs (Task 3).

**Files:**
- Modify: `runcoach/parser.py`
- Modify: `runcoach/pipeline.py`
- Modify: `runcoach/web/routes.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Remove `parse_and_write()` from `parser.py`**

`runcoach/parser.py` currently has two functions: `parse_fit_file()` (keep) and `parse_and_write()` (remove). Replace the entire file with:

```python
from __future__ import annotations

import logging
from pathlib import Path

from runcoach.fit_parser import build_blocks_from_fit

log = logging.getLogger(__name__)


def parse_fit_file(fit_path: Path, timezone: str = "Europe/London") -> dict:
    """Parse a FIT file and return the summary dict."""
    summary = build_blocks_from_fit(fit_path, tz_name=timezone)
    return summary
```

- [ ] **Step 2: Update `pipeline.py` parse stage**

In `runcoach/pipeline.py`, replace the import at the top:

```python
# Before
from runcoach.parser import parse_and_write

# After
import json as _json
from runcoach.parser import parse_fit_file
```

Replace the parse stage loop body. The outer pipeline result dict is named `summary` — use `parsed_summary` for the `parse_fit_file()` return value to avoid collision:

```python
        # 2. Parse all pending FIT files for this user
        for run in db.get_pending_runs("synced", user_id=user_id):
            try:
                fit_path = config.data_dir / run["fit_path"]
                stryd_rss = run.get("stryd_rss")

                planned_workout_title = None
                if run.get("date"):
                    planned_workouts = db.get_planned_workout_for_date(
                        run["date"], user_id=user_id
                    )
                    if planned_workouts:
                        planned_workout_title = planned_workouts[0]["title"]

                parsed_summary = parse_fit_file(fit_path, timezone=config.timezone)

                if planned_workout_title:
                    fit_name = parsed_summary.get("workout_name", "")
                    if fit_name and len(fit_name) == 32 and planned_workout_title.startswith(fit_name):
                        parsed_summary["workout_name"] = planned_workout_title
                        parsed_summary["workout_name_source"] = "planned_workout"
                    elif fit_name and planned_workout_title.startswith(fit_name[:31]):
                        parsed_summary["workout_name"] = planned_workout_title
                        parsed_summary["workout_name_source"] = "planned_workout"

                if stryd_rss is not None:
                    parsed_summary["stryd_rss"] = round(stryd_rss, 1)
                    parsed_summary["stryd_rss_note"] = "Running Stress Score from Stryd (official)"

                db.update_parsed(
                    run_id=run["id"],
                    yaml_path=None,
                    avg_power_w=parsed_summary.get("avg_power"),
                    avg_hr=parsed_summary.get("avg_hr"),
                    workout_name=parsed_summary.get("workout_name"),
                    parsed_data=_json.dumps(parsed_summary),
                )
                summary["parsed"] += 1
            except Exception as e:
                log.exception("Parse failed for run %s: %s", run["id"], e)
                db.update_error(run["id"], f"Parse error: {e}")
                summary["errors"] += 1
```

Leave the analyze stage call in `pipeline.py` unchanged for now — Task 4 updates both the function and all callers simultaneously.

- [ ] **Step 3: Update `web/routes.py` manual upload handler**

In `/upload` route (around line 509–645), replace the `parse_and_write` call and YAML read-back with `parse_fit_file` + `json.dumps`:

Remove the import at line 518:
```python
from runcoach.parser import parse_and_write
```

Add at the top of the file (with the other imports):
```python
import json as _json
from runcoach.parser import parse_fit_file
```

Replace the parse block (lines 592–629):

```python
        # Parse the FIT file immediately to get distance/duration
        try:
            planned_workout_title = None
            planned_workouts = db.get_planned_workout_for_date(date_str, user_id=user_id)
            if planned_workouts:
                planned_workout_title = planned_workouts[0]["title"]

            parsed_summary = parse_fit_file(fit_path, timezone=config.timezone)

            # Replace truncated workout name with full planned title if available
            if planned_workout_title:
                fit_name = parsed_summary.get("workout_name", "")
                if fit_name and len(fit_name) == 32 and planned_workout_title.startswith(fit_name):
                    parsed_summary["workout_name"] = planned_workout_title
                    parsed_summary["workout_name_source"] = "planned_workout"
                elif fit_name and planned_workout_title.startswith(fit_name[:31]):
                    parsed_summary["workout_name"] = planned_workout_title
                    parsed_summary["workout_name_source"] = "planned_workout"

            # Insert as manual run
            run_id = db.insert_manual_run(
                name=activity_name,
                date=date_str,
                fit_path=fit_path_rel,
                distance_m=parsed_summary.get("distance_km", 0) * 1000
                           if parsed_summary.get("distance_km") else None,
                moving_time_s=int(parsed_summary.get("duration_min", 0) * 60)
                              if parsed_summary.get("duration_min") else None,
                user_id=user_id,
            )

            db.update_parsed(
                run_id=run_id,
                yaml_path=None,
                avg_power_w=parsed_summary.get("avg_power"),
                avg_hr=parsed_summary.get("avg_hr"),
                workout_name=parsed_summary.get("workout_name"),
                parsed_data=_json.dumps(parsed_summary),
            )

            flash(f"Uploaded and parsed: {activity_name}")
            return redirect(url_for("main.run_detail", run_id=run_id))

        except Exception as e:
            log.exception("Failed to parse uploaded FIT file: %s", e)
            run_id = db.insert_manual_run(
                name=activity_name,
                date=date_str,
                fit_path=fit_path_rel,
                user_id=user_id,
            )
            db.update_error(run_id, f"Parse error: {e}")
            flash(f"Uploaded but failed to parse: {e}")
            return redirect(url_for("main.index"))
```

- [ ] **Step 4: Update `test_parser.py`**

`tests/test_parser.py` currently imports and tests `parse_and_write`, which is being removed. Replace the entire file with tests for `parse_fit_file`:

```python
"""Unit tests for runcoach.parser module."""

from __future__ import annotations

import json
import pytest
import shutil
from pathlib import Path

from runcoach.parser import parse_fit_file


class TestParseFitFile:
    """Tests for parse_fit_file function."""

    def test_parse_fit_file_returns_dict(self, tmp_path):
        """parse_fit_file returns a dict with expected top-level keys."""
        fit_file = Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        result = parse_fit_file(temp_fit)

        assert isinstance(result, dict)
        assert "workout_name" in result
        assert "distance_km" in result
        assert "duration_min" in result

    def test_parse_fit_file_no_yaml_written(self, tmp_path):
        """parse_fit_file does not write any files to disk."""
        fit_file = Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        parse_fit_file(temp_fit)

        # Only the .fit file should exist — no .yaml or other output
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".fit"

    def test_parse_fit_file_result_is_json_serialisable(self, tmp_path):
        """Result of parse_fit_file can be serialised to JSON without error."""
        fit_file = Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        result = parse_fit_file(temp_fit)

        serialised = json.dumps(result)
        assert isinstance(serialised, str)
        assert len(serialised) > 0
```

- [ ] **Step 5: Update `test_pipeline.py` parse stage**

In `tests/test_pipeline.py`, update `TestPipelineParseStage.test_parse_stage_processes_synced_runs` to mock `parse_fit_file` instead of `parse_and_write`:

```python
class TestPipelineParseStage:
    def test_parse_stage_processes_synced_runs(self, config, db, tmp_path):
        """Runs in 'synced' stage should be parsed."""
        fit_dir = config.data_dir / "activities"
        fit_dir.mkdir(parents=True, exist_ok=True)
        fit_path = fit_dir / "test.fit"
        fit_path.write_bytes(b"\x00" * 20)

        run_id = db.insert_run(
            stryd_activity_id=1,
            name="Sync'd Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
        )

        import json as _json
        fake_summary = {"workout_name": "Easy Run", "avg_power": 250, "avg_hr": 140}

        with patch("runcoach.pipeline.parse_fit_file", return_value=fake_summary):
            result = run_full_pipeline(config, db)

        assert result["parsed"] == 1
        assert result["errors"] == 0

        updated = db.get_run(run_id)
        assert updated["stage"] == "parsed"
        assert updated["workout_name"] == "Easy Run"
        assert updated["parsed_data"] is not None
        assert _json.loads(updated["parsed_data"])["avg_power"] == 250

    def test_parse_stage_records_error_on_failure(self, config, db):
        """A parse failure should increment errors and set stage to 'error'."""
        fit_dir = config.data_dir / "activities"
        fit_dir.mkdir(parents=True, exist_ok=True)
        (fit_dir / "bad.fit").write_bytes(b"\x00")

        run_id = db.insert_run(
            stryd_activity_id=2,
            name="Bad Run",
            date="2026-03-02",
            fit_path="activities/bad.fit",
        )

        with patch("runcoach.pipeline.parse_fit_file", side_effect=RuntimeError("parse boom")):
            result = run_full_pipeline(config, db)

        assert result["errors"] == 1
        assert db.get_run(run_id)["stage"] == "error"
```

- [ ] **Step 6: Run the tests**

```bash
pytest tests/test_pipeline.py tests/test_db.py tests/test_parser.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add runcoach/parser.py runcoach/pipeline.py runcoach/web/routes.py tests/test_pipeline.py tests/test_parser.py
git commit -m "feat: parse stage writes parsed_data JSON instead of YAML files"
```

---

### Task 3: Implement `runcoach-migrate` command

Back-fills `parsed_data` for all runs that have a `yaml_path` but no `parsed_data`. Safe to run multiple times.

**Files:**
- Modify: `runcoach/cli.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_db.py` (or a new `tests/test_migrate.py`)

- [ ] **Step 1: Write the migration function and entry point in `cli.py`**

Add at the top of `runcoach/cli.py` (with existing imports):

```python
import json as _json
import yaml as _yaml
```

Add the `migrate()` function before `main()`:

```python
def migrate(config: Config, db: RunCoachDB) -> None:
    """
    Back-fill parsed_data for all runs that have a yaml_path but no parsed_data.

    Idempotent — skips runs already having parsed_data populated.
    """
    with db._connect() as conn:
        rows = conn.execute(
            """SELECT id, name, date, yaml_path FROM runs
               WHERE yaml_path IS NOT NULL AND parsed_data IS NULL
               ORDER BY date""",
        ).fetchall()

    migrated = skipped = 0
    for row in rows:
        run_id, name, date, yaml_rel = row["id"], row["name"], row["date"], row["yaml_path"]
        yaml_path = config.data_dir / yaml_rel
        if not yaml_path.exists():
            log.warning("YAML not found for run %d (%s %s), skipping", run_id, date, name)
            skipped += 1
            continue

        try:
            parsed = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Could not read %s: %s", yaml_path, e)
            skipped += 1
            continue

        db.store_parsed_data(run_id, _json.dumps(parsed))
        log.info("Migrated run %d (%s %s)", run_id, date, name)
        migrated += 1

    log.info(
        "Migration complete: %d migrated, %d skipped (missing YAML)",
        migrated, skipped,
    )
    print(f"Done: {migrated} migrated, {skipped} skipped.")
```

Add a `migrate_main()` entry point function after `migrate()`:

```python
def migrate_main() -> None:
    """CLI entry point for the one-shot YAML→DB migration."""
    config = Config.from_env()
    db = RunCoachDB(config.db_path)
    migrate(config, db)
```

- [ ] **Step 2: Add `runcoach-migrate` to `pyproject.toml`**

In `pyproject.toml`, under `[project.scripts]`, add:

```toml
runcoach-migrate = "runcoach.cli:migrate_main"
```

So the section becomes:

```toml
[project.scripts]
runcoach = "runcoach.web:main"
runcoach-pipeline = "runcoach.pipeline:main"
runcoach-cli = "runcoach.cli:main"
runcoach-migrate = "runcoach.cli:migrate_main"
```

- [ ] **Step 3: Reinstall to register the new entry point**

```bash
source .venv/bin/activate
pip install -e .
```

- [ ] **Step 4: Write tests for the migration function**

Append a new class to `tests/test_db.py` (or create `tests/test_migrate.py`). Using `tests/test_db.py`:

```python
class TestMigrateCommand:
    """Tests for the runcoach-migrate back-fill command."""

    def test_migrate_populates_parsed_data_from_yaml(self, tmp_path):
        """Runs with yaml_path get parsed_data populated from the YAML file."""
        import json
        import yaml as _yaml
        from runcoach.config import Config
        from runcoach.db import RunCoachDB
        from runcoach.cli import migrate
        from runcoach.auth import hash_password

        config = Config(
            openai_api_key="x", openai_model="gpt-4o",
            data_dir=tmp_path / "data", timezone="Europe/London",
        )
        config.data_dir.mkdir(parents=True, exist_ok=True)

        db = RunCoachDB(config.db_path)
        db.ensure_default_user("athlete", hash_password("pass"))

        # Write a YAML file
        yaml_rel = "activities/20260501_run.yaml"
        yaml_abs = config.data_dir / yaml_rel
        yaml_abs.parent.mkdir(parents=True, exist_ok=True)
        payload = {"workout_name": "Easy Run", "avg_power": 250}
        yaml_abs.write_text(_yaml.safe_dump(payload), encoding="utf-8")

        # Insert a run with yaml_path but no parsed_data
        run_id = db.insert_run(
            stryd_activity_id=1, name="Run", date="2026-05-01",
            fit_path="activities/20260501_run.fit", user_id=1,
        )
        db.update_parsed(
            run_id=run_id, yaml_path=yaml_rel,
            avg_power_w=250, avg_hr=None, workout_name="Easy Run",
        )
        assert db.get_run(run_id)["parsed_data"] is None

        migrate(config, db)

        run = db.get_run(run_id)
        assert run["parsed_data"] is not None
        assert json.loads(run["parsed_data"])["avg_power"] == 250

    def test_migrate_skips_missing_yaml(self, tmp_path):
        """Runs whose YAML file is missing are skipped (not errored)."""
        from runcoach.config import Config
        from runcoach.db import RunCoachDB
        from runcoach.cli import migrate
        from runcoach.auth import hash_password

        config = Config(
            openai_api_key="x", openai_model="gpt-4o",
            data_dir=tmp_path / "data", timezone="Europe/London",
        )
        config.data_dir.mkdir(parents=True, exist_ok=True)

        db = RunCoachDB(config.db_path)
        db.ensure_default_user("athlete", hash_password("pass"))

        run_id = db.insert_run(
            stryd_activity_id=2, name="Run", date="2026-05-02",
            fit_path="activities/missing.fit", user_id=1,
        )
        db.update_parsed(
            run_id=run_id, yaml_path="activities/missing.yaml",
            avg_power_w=None, avg_hr=None, workout_name=None,
        )

        migrate(config, db)  # must not raise

        assert db.get_run(run_id)["parsed_data"] is None

    def test_migrate_is_idempotent(self, tmp_path):
        """Running migrate twice doesn't change already-populated runs."""
        import json
        import yaml as _yaml
        from runcoach.config import Config
        from runcoach.db import RunCoachDB
        from runcoach.cli import migrate
        from runcoach.auth import hash_password

        config = Config(
            openai_api_key="x", openai_model="gpt-4o",
            data_dir=tmp_path / "data", timezone="Europe/London",
        )
        config.data_dir.mkdir(parents=True, exist_ok=True)

        db = RunCoachDB(config.db_path)
        db.ensure_default_user("athlete", hash_password("pass"))

        yaml_rel = "activities/run.yaml"
        yaml_abs = config.data_dir / yaml_rel
        yaml_abs.parent.mkdir(parents=True, exist_ok=True)
        yaml_abs.write_text(_yaml.safe_dump({"avg_power": 200}), encoding="utf-8")

        run_id = db.insert_run(
            stryd_activity_id=3, name="Run", date="2026-05-03",
            fit_path="activities/run.fit", user_id=1,
        )
        db.update_parsed(
            run_id=run_id, yaml_path=yaml_rel,
            avg_power_w=200, avg_hr=None, workout_name=None,
        )

        migrate(config, db)
        first = db.get_run(run_id)["parsed_data"]

        migrate(config, db)  # second run must not change anything
        second = db.get_run(run_id)["parsed_data"]

        assert first == second
```

- [ ] **Step 5: Run the tests**

```bash
pytest tests/test_db.py::TestMigrateCommand -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add runcoach/cli.py pyproject.toml tests/test_db.py
git commit -m "feat: add runcoach-migrate command for YAML→DB back-fill"
```

---

### Task 4: Update `context.py` — read `parsed_data` instead of YAML files

`build_weekly_context()` currently filters runs by `r.get("yaml_path")` and reads YAML files from disk. After the migration, new runs have `parsed_data` but no `yaml_path`. Update `context.py` to read from `parsed_data` first, falling back to the YAML file for runs not yet migrated. Update `test_context.py` to use `parsed_data` instead of writing YAML files.

**Files:**
- Modify: `runcoach/context.py`
- Modify: `tests/test_context.py`

- [ ] **Step 1: Add `_load_run_parsed()` helper and update `build_weekly_context()`**

In `runcoach/context.py`, add at the top (after existing imports):

```python
import json as _json
```

Add a helper function before `build_weekly_context`:

```python
def _load_run_parsed(run: dict, data_dir: Path) -> dict | None:
    """Load the parsed workout dict for a run.

    Reads from parsed_data column if available; falls back to the YAML file
    for runs that pre-date the DB migration.
    """
    if run.get("parsed_data"):
        try:
            return _json.loads(run["parsed_data"])
        except Exception:
            return None
    if run.get("yaml_path"):
        yaml_path = data_dir / run["yaml_path"]
        if yaml_path.exists():
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
            except Exception:
                return None
    return None
```

Update `build_weekly_context` to use `_load_run_parsed`:

1. Change the `week_runs` filter from:
   ```python
   week_runs = [
       r for r in all_runs
       if r.get("yaml_path")
       and r["date"] >= window_start.isoformat()
       ...
   ```
   to:
   ```python
   week_runs = [
       r for r in all_runs
       if (r.get("parsed_data") or r.get("yaml_path"))
       and r["date"] >= window_start.isoformat()
       ...
   ```

2. Replace the previous-CP lookup loop (lines 98–110) with `_load_run_parsed`:
   ```python
   for run in sorted(all_runs, key=lambda r: r["date"], reverse=True):
       if (run.get("parsed_data") or run.get("yaml_path")) and run["date"] < target.isoformat():
           parsed = _load_run_parsed(run, data_dir)
           if parsed:
               cp = parsed.get("critical_power")
               if cp and cp > 0:
                   previous_cp = cp
                   break
   ```

3. Replace the per-run YAML read in the `for run in week_runs:` loop (lines 122–131):
   ```python
   for run in week_runs:
       parsed = _load_run_parsed(run, data_dir)
       if parsed is None:
           log.warning("Could not load data for run %s, skipping", run.get("id"))
           continue
       # ... rest of the loop body unchanged ...
   ```

4. Change the `chronic_runs` filter from `r.get("yaml_path")` to `r.get("parsed_data") or r.get("yaml_path")`.

5. Replace the per-run YAML read in the `for run in chronic_runs:` loop (lines 193–200):
   ```python
   for run in chronic_runs:
       parsed = _load_run_parsed(run, data_dir)
       if parsed is None:
           continue
       # ... rest of the loop body unchanged ...
   ```

- [ ] **Step 2: Update `tests/test_context.py` — use `parsed_data` instead of YAML files**

In `tests/test_context.py`, find every fixture that writes a YAML file and calls `db.update_parsed(yaml_path=...)`. Replace the YAML file write with `db.update_parsed(yaml_path=None, parsed_data=json.dumps(...))`.

Example: change this pattern:
```python
yaml_path = yaml_dir / "20260225_test_run" / "20260225_test_run.yaml"
yaml_path.parent.mkdir(parents=True)
# ... build content dict ...
with open(yaml_path, "w") as f:
    yaml.safe_dump(content, f)
db.update_parsed(
    run_id=run_id,
    yaml_path="activities/2026/02/20260225_test_run/20260225_test_run.yaml",
    avg_power_w=...,
    avg_hr=...,
    workout_name=...,
)
```

to:
```python
import json as _json
db.update_parsed(
    run_id=run_id,
    yaml_path=None,
    avg_power_w=...,
    avg_hr=...,
    workout_name=...,
    parsed_data=_json.dumps(content),
)
```

Apply this change to all occurrences in the file. Remove all `yaml_path.parent.mkdir(...)`, `with open(yaml_path, "w") as f: yaml.safe_dump(...)` and related `yaml_dir` variable assignments that only exist to support the YAML file writes.

- [ ] **Step 3: Run the tests**

```bash
pytest tests/test_context.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add runcoach/context.py tests/test_context.py
git commit -m "feat: context.py reads parsed_data from DB instead of YAML files"
```

---

### Task 5: Update `analyzer.py` — read from `parsed_data`

Change `analyze_and_write()` to accept a run dict (instead of a YAML path), update `build_chat_context()` to read `parsed_data`, update `analyze_run()` to use the `is_manual_upload` DB column, and update all callers simultaneously.

**Files:**
- Modify: `runcoach/analyzer.py`
- Modify: `runcoach/pipeline.py` (analyze stage)
- Modify: `runcoach/web/routes.py` (re-analysis route)
- Modify: `runcoach/web/api.py` (analyze task)
- Modify: `tests/test_analyzer.py`

- [ ] **Step 1: Update `analyze_run()` — read `is_manual_upload` from run dict**

In `runcoach/analyzer.py`, `analyze_run()` currently takes `yaml_content: str` and detects manual upload by string search. The new version takes `yaml_content` (reconstructed from JSON) **and** an explicit `is_manual_upload` flag:

Replace the current `analyze_run` function signature and body:

```python
def analyze_run(
    yaml_content: str,
    config: Config,
    context_yaml: str | None = None,
    db: RunCoachDB | None = None,
    run_date: str | None = None,
    user_id: int | None = None,
    is_manual_upload: bool = False,
) -> dict:
    """
    Send YAML workout data to the LLM for coaching analysis.

    yaml_content is the YAML-formatted string (reconstructed from parsed_data).
    is_manual_upload must be passed explicitly by the caller.

    Returns a dict with keys: commentary, prompt_tokens, completion_tokens.
    """
    system_msg = _build_system_prompt(db, user_id, run_date, is_manual_upload=is_manual_upload)

    if context_yaml:
        user_msg = context_yaml.rstrip("\n") + "\n---\n" + yaml_content
    else:
        user_msg = yaml_content

    return _dispatch_llm(system_msg, user_msg, config)
```

- [ ] **Step 2: Update `_build_context_yaml()` — accept pre-parsed dict instead of YAML string**

The function currently takes `yaml_content: str` and does `yaml.safe_load()` internally. Change it to accept an already-parsed dict:

```python
def _build_context_yaml(
    parsed: dict,
    run_date: str,
    config: Config,
    db: RunCoachDB,
    user_id: int | None,
) -> str | None:
    """Build weekly training context YAML for a run. Returns None on failure."""
    try:
        current_cp = parsed.get("critical_power")
        from runcoach.context import build_weekly_context, build_training_summary
        from datetime import date as _date

        context = build_weekly_context(
            run_date, config.data_dir, db, current_cp=current_cp, user_id=user_id
        )
        try:
            summary = build_training_summary(
                db=db,
                as_of_date=_date.fromisoformat(run_date),
                user_id=user_id,
            )
            ts = summary["training_summary"]
            context["training_summary"] = {
                "windows": ts["windows"],
                "current_rsb": ts["current_rsb"],
            }
        except Exception:
            log.warning("Failed to build training summary for LLM context")
        return yaml.safe_dump(context, sort_keys=False, allow_unicode=True)
    except Exception:
        log.exception("Failed to build training context, proceeding without it")
        return None
```

- [ ] **Step 3: Replace `analyze_and_write()` with run-dict version**

Replace the current `analyze_and_write` function:

```python
def analyze_and_write(
    run: dict,
    config: Config,
    db: RunCoachDB | None = None,
    user_id: int | None = None,
) -> dict:
    """
    Read parsed_data from a run dict, build training context, analyze, return result.

    No longer writes a .md file. Returns the result dict directly (not a tuple).
    """
    import json as _json

    if not run.get("parsed_data"):
        raise ValueError(f"Run {run.get('id')} has no parsed_data — cannot analyze")

    parsed = _json.loads(run["parsed_data"])
    yaml_content = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True)

    is_manual = bool(run.get("is_manual_upload"))
    run_date: str | None = run.get("date")

    context_yaml = None
    if db is not None and run_date:
        context_yaml = _build_context_yaml(parsed, run_date, config, db, user_id)

    return analyze_run(
        yaml_content, config,
        context_yaml=context_yaml,
        db=db,
        run_date=run_date,
        user_id=user_id,
        is_manual_upload=is_manual,
    )
```

- [ ] **Step 4: Update `build_chat_context()` — read `parsed_data` from run dict**

Replace the current `build_chat_context` function body. The function currently reads `yaml_path` from the run dict; change it to read `parsed_data`:

```python
def build_chat_context(
    run: dict,
    user_id: int,
    history: list[dict],
    new_message: str,
    config: Config,
    db: RunCoachDB,
) -> tuple[str, str]:
    """Build (system_msg, user_msg) for a follow-up chat turn."""
    import json as _json

    run_date = run.get("date")
    is_manual = bool(run.get("is_manual_upload"))
    system_msg = _build_system_prompt(db, user_id, run_date, is_manual_upload=is_manual)

    if not run.get("parsed_data"):
        raise ValueError(f"Run {run.get('id')} has no parsed_data — must be parsed before chat")

    parsed = _json.loads(run["parsed_data"])
    yaml_content = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True)

    context_yaml = None
    if run_date:
        context_yaml = _build_context_yaml(parsed, run_date, config, db, user_id)

    parts = []
    if context_yaml:
        parts.append(context_yaml.rstrip("\n"))
        parts.append("---")
    parts.append(yaml_content.rstrip("\n"))

    if history:
        parts.append("---")
        parts.append("Conversation so far:")
        for msg in history:
            prefix = "Athlete" if msg["role"] == "user" else "Coach"
            parts.append(f"{prefix}: {msg['message']}")

    parts.append("---")
    parts.append(f"Athlete: {new_message}")
    parts.append(
        "(Reply concisely and directly to the question above. Draw on the workout data "
        "and conversation context to support your answer, but do not repeat or summarise "
        "the original analysis.)"
    )

    return system_msg, "\n".join(parts)
```

- [ ] **Step 5: Update `pipeline.py` analyze stage**

In `runcoach/pipeline.py`, the analyze stage currently calls `analyze_and_write(yaml_path, ...)`. Change it to:

```python
        # 3. Analyze all parsed runs for this user
        if not config.has_llm:
            log.warning("No LLM provider configured, skipping analysis stage")
        elif not config.llm_auto_analyse:
            log.info("LLM_AUTO_ANALYSE is off, skipping automatic analysis")
        else:
            for run in db.get_pending_runs("parsed", user_id=user_id, date_from=config.analyze_from):
                try:
                    result = analyze_and_write(run, config, db=db, user_id=user_id)
                    db.update_analyzed(
                        run_id=run["id"],
                        md_path=None,
                        commentary=result["commentary"],
                        model_used=config.active_model,
                        prompt_tokens=result.get("prompt_tokens"),
                        completion_tokens=result.get("completion_tokens"),
                    )
                    summary["analyzed"] += 1
                except Exception as e:
                    log.exception("Analysis failed for run %s: %s", run["id"], e)
                    db.update_error(run["id"], f"Analysis error: {e}")
                    summary["errors"] += 1
```

Also remove the now-unused `md_path_rel = str(md_path.relative_to(config.data_dir))` line.

- [ ] **Step 6: Update `web/routes.py` re-analysis route**

In `analyze_run_route` (around line 383), the `_do_analyze` inner function currently reads `yaml_path` from the run dict. Replace it:

```python
    def _do_analyze(app, run_id, config, user_id):
        with app.app_context():
            db = _db()
            run = db.get_run(run_id)
            try:
                result = analyze_and_write(run, config, db=db, user_id=user_id)
                db.update_analyzed(
                    run_id=run["id"],
                    md_path=None,
                    commentary=result["commentary"],
                    model_used=config.active_model,
                    prompt_tokens=result.get("prompt_tokens"),
                    completion_tokens=result.get("completion_tokens"),
                )
                log.info("Analysis complete for run %s", run_id)
            except Exception as e:
                log.exception("Analysis failed for run %s: %s", run_id, e)
                db.update_error(run["id"], f"Analysis error: {e}")
```

- [ ] **Step 7: Update `web/api.py` analyze task**

In the `analyze_task` inner function inside `analyze_run` endpoint (around line 438), replace:

```python
                yaml_path = config.data_dir / fresh_run["yaml_path"]
                md_path, result = analyze_and_write(yaml_path, config, db=db)

                md_path_rel = str(md_path.relative_to(config.data_dir))
                db.update_analyzed(
                    run_id=fresh_run["id"],
                    md_path=md_path_rel,
                    commentary=result["commentary"],
                    model_used=config.active_model,
                    prompt_tokens=result.get("prompt_tokens"),
                    completion_tokens=result.get("completion_tokens"),
                )
```

with:

```python
                result = analyze_and_write(fresh_run, config, db=db)
                db.update_analyzed(
                    run_id=fresh_run["id"],
                    md_path=None,
                    commentary=result["commentary"],
                    model_used=config.active_model,
                    prompt_tokens=result.get("prompt_tokens"),
                    completion_tokens=result.get("completion_tokens"),
                )
```

- [ ] **Step 8: Update `tests/test_analyzer.py`**

`TestAnalyzeAndWrite` currently passes a YAML path and asserts an MD file is created, and unpacks a `(md_path, result)` tuple. Rewrite the class:

```python
class TestAnalyzeAndWrite:
    """Tests for the analyze_and_write function."""

    def _make_run(self, tmp_path, data: dict | None = None) -> dict:
        import json as _json
        if data is None:
            data = {"date": "2026-03-01", "name": "Test Run", "distance_km": 10.0}
        return {
            "id": 1,
            "date": data.get("date", "2026-03-01"),
            "is_manual_upload": 0,
            "parsed_data": _json.dumps(data),
        }

    def test_analyze_and_write_returns_result_dict(self, test_config, mock_openai_client, tmp_path):
        """analyze_and_write returns a dict, not a tuple."""
        run = self._make_run(tmp_path)
        result = analyze_and_write(run, test_config, db=None)
        assert isinstance(result, dict)
        assert "commentary" in result
        assert "prompt_tokens" in result

    def test_analyze_and_write_no_md_file(self, test_config, mock_openai_client, tmp_path):
        """analyze_and_write does not write a .md file."""
        run = self._make_run(tmp_path)
        analyze_and_write(run, test_config, db=None)
        # No .md files should exist anywhere in tmp_path
        assert list(tmp_path.rglob("*.md")) == []

    def test_analyze_and_write_raises_without_parsed_data(self, test_config, mock_openai_client, tmp_path):
        """analyze_and_write raises ValueError when parsed_data is missing."""
        run = {"id": 99, "date": "2026-03-01", "is_manual_upload": 0, "parsed_data": None}
        with pytest.raises(ValueError, match="no parsed_data"):
            analyze_and_write(run, test_config, db=None)

    def test_analyze_and_write_manual_upload_flag(self, test_config, mock_openai_client, tmp_path):
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
```

Also update `TestAnalyzeRun.test_analyze_run_manual_upload` — `analyze_run` no longer reads the `manual_upload: true` YAML key; instead it uses the explicit `is_manual_upload` parameter:

```python
    def test_analyze_run_manual_upload(self, test_config, mock_openai_client):
        """Manual upload flag triggers special system prompt note."""
        yaml_content = "date: '2026-03-01'\nname: Manual Upload\ndistance_km: 10.0\n"

        result = analyze_run(yaml_content, test_config, is_manual_upload=True)

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "manual upload" in system_msg.lower()
        assert "power data" in system_msg.lower()
```

- [ ] **Step 9: Update `test_pipeline.py` analyze stage**

In `TestPipelineAnalyzeStage`, the helper `_insert_parsed_run` writes a YAML file and uses `yaml_path`. Replace with `parsed_data`:

```python
class TestPipelineAnalyzeStage:
    def _insert_parsed_run(self, config, db, tmp_path):
        """Helper: insert a run already in 'parsed' stage with parsed_data JSON."""
        import json as _json
        run_id = db.insert_run(
            stryd_activity_id=10,
            name="Parsed Run",
            date="2026-03-05",
            fit_path="activities/run.fit",
        )
        db.update_parsed(
            run_id=run_id,
            yaml_path=None,
            avg_power_w=260,
            avg_hr=145,
            workout_name="Test",
            parsed_data=_json.dumps({"workout_name": "Test", "avg_power": 260}),
        )
        return run_id

    def test_analyze_stage_processes_parsed_runs(self, config, db, tmp_path):
        config.llm_auto_analyse = True
        run_id = self._insert_parsed_run(config, db, tmp_path)

        mock_result = {
            "commentary": "Great run!",
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }

        with patch(
            "runcoach.pipeline.analyze_and_write",
            return_value=mock_result,
        ):
            result = run_full_pipeline(config, db)

        assert result["analyzed"] == 1
        assert result["errors"] == 0
        updated = db.get_run(run_id)
        assert updated["stage"] == "analyzed"
        assert updated["commentary"] == "Great run!"
        assert updated["md_path"] is None

    def test_analyze_stage_records_error_on_failure(self, config, db, tmp_path):
        config.llm_auto_analyse = True
        run_id = self._insert_parsed_run(config, db, tmp_path)

        with patch(
            "runcoach.pipeline.analyze_and_write",
            side_effect=RuntimeError("openai boom"),
        ):
            result = run_full_pipeline(config, db)

        assert result["errors"] == 1
        assert db.get_run(run_id)["stage"] == "error"

    def test_analyze_respects_date_from_filter(self, config, db, tmp_path):
        """analyze_from config causes old runs to be skipped."""
        config.llm_auto_analyse = True
        config.analyze_from = "2026-04-01"
        run_id = self._insert_parsed_run(config, db, tmp_path)

        with patch("runcoach.pipeline.analyze_and_write") as mock_analyze:
            result = run_full_pipeline(config, db)

        mock_analyze.assert_not_called()
        assert result["analyzed"] == 0
```

- [ ] **Step 10: Run the tests**

```bash
pytest tests/test_analyzer.py tests/test_pipeline.py -v
```

Expected: all tests PASS.

- [ ] **Step 11: Commit**

```bash
git add runcoach/analyzer.py runcoach/pipeline.py runcoach/web/routes.py runcoach/web/api.py tests/test_analyzer.py tests/test_pipeline.py
git commit -m "feat: analyzer reads parsed_data from DB instead of YAML files"
```

---

### Task 6: Update API — serve `parsed_data` from DB

**Files:**
- Modify: `runcoach/web/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Update `format_run_for_api()`**

In `runcoach/web/api.py`, replace the yaml-file-reading block in `format_run_for_api()`:

```python
    # Before (lines 80–96):
    if include_yaml and run["yaml_path"]:
        try:
            yaml_path = Path(run["yaml_path"])
            if not yaml_path.is_absolute():
                config: Config = current_app.config["RUNCOACH_CONFIG"]
                yaml_path = config.data_dir / yaml_path
            if yaml_path.exists():
                with open(yaml_path) as f:
                    result["yaml_data"] = yaml.safe_load(f)
            else:
                log.warning(f"YAML file not found for run {run['id']}: {yaml_path}")
                result["yaml_data"] = None
        except Exception as e:
            log.error(f"Failed to load YAML for run {run['id']}: {e}")
            result["yaml_data"] = None

    # After:
    if include_yaml:
        if run.get("parsed_data"):
            try:
                result["yaml_data"] = json.loads(run["parsed_data"])
            except Exception as e:
                log.error(f"Failed to deserialize parsed_data for run {run['id']}: {e}")
                result["yaml_data"] = None
        else:
            result["yaml_data"] = None
```

Remove the now-unused `yaml` import from `api.py` (line 8: `import yaml`). Check no other code in `api.py` uses yaml — it doesn't.

- [ ] **Step 2: Update tests in `test_api.py`**

Find the tests that assert on `yaml_data` in `GET /api/v1/runs/:id`. Add a fixture helper that sets `parsed_data` and add/update these tests:

```python
class TestGetRun:
    def _insert_parsed_run(self, app) -> int:
        """Insert a run with parsed_data in the DB and return its ID."""
        import json as _json
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=42,
            name="Test Run",
            date="2026-03-07",
            fit_path="activities/test.fit",
            user_id=user_id,
        )
        db.update_parsed(
            run_id=run_id,
            yaml_path=None,
            avg_power_w=250,
            avg_hr=145,
            workout_name="Easy Run",
            parsed_data=_json.dumps({"workout_name": "Easy Run", "avg_power": 250}),
        )
        return run_id

    def test_get_run_includes_yaml_data(self, client, app, auth_headers):
        """GET /api/v1/runs/:id includes yaml_data sourced from parsed_data."""
        run_id = self._insert_parsed_run(app)
        resp = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "yaml_data" in data
        assert data["yaml_data"]["avg_power"] == 250

    def test_get_run_yaml_data_none_when_no_parsed_data(self, client, app, auth_headers):
        """GET /api/v1/runs/:id returns yaml_data=None when parsed_data is NULL."""
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=99,
            name="Unparsed",
            date="2026-03-08",
            fit_path="activities/unparsed.fit",
            user_id=user_id,
        )
        resp = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()["yaml_data"] is None
```

- [ ] **Step 3: Run the tests**

```bash
pytest tests/test_api.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add runcoach/web/api.py tests/test_api.py
git commit -m "feat: API serves yaml_data from parsed_data column"
```

---

### Task 7: Update run detail page — read `parsed_data`

**Files:**
- Modify: `runcoach/web/routes.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Update `run_detail` route**

In `runcoach/web/routes.py`, the `run_detail` function (around line 266) reads workout YAML from disk. Replace the file-read block with JSON decode:

```python
    # Before (lines 292–301):
    workout_data = None
    if run.get("yaml_path"):
        yaml_path = config.data_dir / run["yaml_path"]
        if yaml_path.exists():
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    workout_data = _yaml.safe_load(f)
            except Exception:
                pass

    # After:
    import json as _json
    workout_data = None
    if run.get("parsed_data"):
        try:
            workout_data = _json.loads(run["parsed_data"])
        except Exception:
            pass
```

Remove the `import yaml as _yaml` at line 269 if it's only used for this block (check the function — it is the only use).

- [ ] **Step 2: Add/update test in `test_web.py`**

Add a test for the run detail page that uses `parsed_data`:

```python
class TestRunDetail:
    def test_run_detail_loads_workout_data_from_parsed_data(self, client, app):
        """Run detail page renders without error when parsed_data is set."""
        import json as _json
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=77,
            name="Detail Test",
            date="2026-03-10",
            fit_path="activities/detail.fit",
            user_id=user_id,
        )
        db.update_parsed(
            run_id=run_id,
            yaml_path=None,
            avg_power_w=230,
            avg_hr=150,
            workout_name="Detail Test",
            parsed_data=_json.dumps({
                "workout_name": "Detail Test",
                "avg_power": 230,
                "blocks": {},
            }),
        )
        resp = client.get(f"/run/{run_id}")
        assert resp.status_code == 200

    def test_run_detail_handles_missing_parsed_data(self, client, app):
        """Run detail page renders without error when parsed_data is NULL."""
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=78,
            name="No Data",
            date="2026-03-11",
            fit_path="activities/nodata.fit",
            user_id=user_id,
        )
        resp = client.get(f"/run/{run_id}")
        assert resp.status_code == 200
```

- [ ] **Step 3: Run the tests**

```bash
pytest tests/test_web.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add runcoach/web/routes.py tests/test_web.py
git commit -m "feat: run detail page reads workout data from parsed_data"
```

---

### Task 8: Update CLI commands

Remove old file-path-based commands; add run-ID-based commands; ensure `backfill_rss` reads from `parsed_data`.

**Files:**
- Modify: `runcoach/cli.py`

- [ ] **Step 1: Rewrite `cli.py`**

Replace the entire file with:

```python
#!/usr/bin/env python3
"""RunCoach CLI — parse FIT files and trigger analysis by run ID."""

from __future__ import annotations

import argparse
import json as _json
import logging
import sys
from pathlib import Path

import yaml as _yaml

from runcoach.parser import parse_fit_file
from runcoach.analyzer import analyze_and_write
from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.context import compute_rss

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def parse_fit(fit_path: Path, config: Config, db: RunCoachDB, user_id: int = 1) -> None:
    """Parse a single FIT file, upsert DB record, store parsed_data."""
    if not fit_path.exists():
        log.error("File not found: %s", fit_path)
        sys.exit(1)
    if fit_path.suffix.lower() != ".fit":
        log.error("File must have .fit extension: %s", fit_path)
        sys.exit(1)

    log.info("Parsing %s...", fit_path)
    summary = parse_fit_file(fit_path, timezone=config.timezone)

    fit_path_rel = str(fit_path.relative_to(config.data_dir)) if fit_path.is_relative_to(config.data_dir) else str(fit_path)

    # Upsert: insert new run or update existing one
    existing = db.get_run_by_fit_path(fit_path_rel, user_id=user_id)
    if existing:
        run_id = existing["id"]
    else:
        from datetime import datetime
        run_id = db.insert_manual_run(
            name=summary.get("workout_name") or fit_path.stem,
            date=summary.get("date") or datetime.now().strftime("%Y-%m-%d"),
            fit_path=fit_path_rel,
            distance_m=summary.get("distance_km", 0) * 1000 if summary.get("distance_km") else None,
            moving_time_s=int(summary.get("duration_min", 0) * 60) if summary.get("duration_min") else None,
            user_id=user_id,
        )

    db.update_parsed(
        run_id=run_id,
        yaml_path=None,
        avg_power_w=summary.get("avg_power"),
        avg_hr=summary.get("avg_hr"),
        workout_name=summary.get("workout_name"),
        parsed_data=_json.dumps(summary),
    )
    log.info("Stored parsed_data for run %d", run_id)
    print(f"Parsed: run_id={run_id}, workout={summary.get('workout_name')}")


def analyze_by_run_id(run_id: int, config: Config, db: RunCoachDB, user_id: int = 1) -> None:
    """Analyze a single run by its DB ID."""
    run = db.get_run(run_id, user_id=user_id)
    if not run:
        log.error("Run %d not found", run_id)
        sys.exit(1)
    if not run.get("parsed_data"):
        log.error("Run %d has no parsed_data — parse it first", run_id)
        sys.exit(1)

    log.info("Analyzing run %d...", run_id)
    result = analyze_and_write(run, config, db=db, user_id=user_id)
    db.update_analyzed(
        run_id=run_id,
        md_path=None,
        commentary=result["commentary"],
        model_used=config.active_model,
        prompt_tokens=result.get("prompt_tokens"),
        completion_tokens=result.get("completion_tokens"),
    )
    log.info("Analysis complete for run %d", run_id)
    print(f"Analyzed: run_id={run_id}")


def analyze_by_date(date: str, config: Config, db: RunCoachDB, user_id: int = 1) -> None:
    """Analyze all parsed runs on a given date (YYYY-MM-DD)."""
    with db._connect() as conn:
        rows = conn.execute(
            """SELECT * FROM runs
               WHERE date = ? AND user_id = ?
                 AND stage IN ('parsed', 'analyzed')
                 AND parsed_data IS NOT NULL
               ORDER BY id""",
            (date, user_id),
        ).fetchall()

    if not rows:
        log.info("No parsed runs found for date %s", date)
        return

    for row in rows:
        run = dict(row)
        log.info("Analyzing run %d (%s)...", run["id"], run.get("workout_name"))
        try:
            result = analyze_and_write(run, config, db=db, user_id=user_id)
            db.update_analyzed(
                run_id=run["id"],
                md_path=None,
                commentary=result["commentary"],
                model_used=config.active_model,
                prompt_tokens=result.get("prompt_tokens"),
                completion_tokens=result.get("completion_tokens"),
            )
            print(f"Analyzed: run_id={run['id']}")
        except Exception as e:
            log.error("Analysis failed for run %d: %s", run["id"], e)


def backfill_rss(config: Config, db: RunCoachDB, dry_run: bool = False) -> None:
    """
    Backfill stryd_rss for runs where it is NULL.

    Reads from parsed_data (preferred) or falls back to the yaml_path file.
    """
    with db._connect() as conn:
        rows = conn.execute(
            """SELECT id, name, date, parsed_data, yaml_path FROM runs
               WHERE stryd_rss IS NULL
                 AND stage IN ('parsed', 'analyzed')
               ORDER BY date""",
        ).fetchall()

    updated = skipped = 0
    for row in rows:
        run_id = row["id"]
        name = row["name"]
        date = row["date"]

        parsed = None
        if row["parsed_data"]:
            try:
                parsed = _json.loads(row["parsed_data"])
            except Exception:
                pass
        elif row["yaml_path"]:
            yaml_path = config.data_dir / row["yaml_path"]
            if yaml_path.exists():
                try:
                    parsed = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

        if parsed is None:
            log.debug("No data for run %d (%s %s), skipping", run_id, date, name)
            skipped += 1
            continue

        rss = parsed.get("stryd_rss")
        if rss is None:
            pwr = parsed.get("avg_power") or 0
            cp = parsed.get("critical_power") or 0
            dur = parsed.get("duration_min") or 0
            if pwr > 0 and cp > 0 and dur > 0:
                rss = round(compute_rss(pwr, cp, dur), 1)

        if rss is None:
            log.debug("No RSS data for run %d (%s %s), skipping", run_id, date, name)
            skipped += 1
            continue

        log.info(
            "%srun %d (%s %s): stryd_rss = %.1f",
            "[dry-run] " if dry_run else "", run_id, date, name, rss,
        )
        if not dry_run:
            db.update_run_rss(run_id, rss)
        updated += 1

    log.info("Done: %d updated, %d skipped%s", updated, skipped, " (dry run)" if dry_run else "")


def migrate(config: Config, db: RunCoachDB) -> None:
    """
    Back-fill parsed_data for all runs that have a yaml_path but no parsed_data.

    Idempotent — skips runs already having parsed_data populated.
    """
    with db._connect() as conn:
        rows = conn.execute(
            """SELECT id, name, date, yaml_path FROM runs
               WHERE yaml_path IS NOT NULL AND parsed_data IS NULL
               ORDER BY date""",
        ).fetchall()

    migrated = skipped = 0
    for row in rows:
        run_id, name, date, yaml_rel = row["id"], row["name"], row["date"], row["yaml_path"]
        yaml_path = config.data_dir / yaml_rel
        if not yaml_path.exists():
            log.warning("YAML not found for run %d (%s %s), skipping", run_id, date, name)
            skipped += 1
            continue
        try:
            data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Could not read %s: %s", yaml_path, e)
            skipped += 1
            continue
        db.store_parsed_data(run_id, _json.dumps(data))
        log.info("Migrated run %d (%s %s)", run_id, date, name)
        migrated += 1

    log.info(
        "Migration complete: %d migrated, %d skipped (missing YAML)",
        migrated, skipped,
    )
    print(f"Done: {migrated} migrated, {skipped} skipped.")


def migrate_main() -> None:
    """CLI entry point for the one-shot YAML→DB migration."""
    config = Config.from_env()
    db = RunCoachDB(config.db_path)
    migrate(config, db)


def main() -> None:
    """CLI entry point with argparse for subcommands."""
    parser = argparse.ArgumentParser(
        description="RunCoach CLI — parse FIT files and trigger analysis by run ID",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # parse subcommand
    parse_parser = subparsers.add_parser("parse", help="Parse a FIT file and store in DB")
    parse_parser.add_argument("--file", type=Path, required=True, help="Path to .fit file")

    # analyze subcommand
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a run by ID or date")
    analyze_group = analyze_parser.add_mutually_exclusive_group(required=True)
    analyze_group.add_argument("--run-id", type=int, help="Analyze a specific run by DB ID")
    analyze_group.add_argument("--date", type=str, help="Analyze all parsed runs on date (YYYY-MM-DD)")

    # backfill-rss subcommand
    backfill_parser = subparsers.add_parser("backfill-rss", help="Backfill stryd_rss for historical runs")
    backfill_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = Config.from_env()
    db = RunCoachDB(config.db_path)

    if args.command == "parse":
        parse_fit(args.file, config, db)

    elif args.command == "analyze":
        if args.run_id:
            analyze_by_run_id(args.run_id, config, db)
        else:
            analyze_by_date(args.date, config, db)

    elif args.command == "backfill-rss":
        backfill_rss(config, db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all tests**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add runcoach/cli.py
git commit -m "refactor: update CLI to use run IDs and parsed_data"
```

---

### Task 9: Full test suite and push

- [ ] **Step 1: Run full test suite**

```bash
source .venv/bin/activate
pytest -v --tb=short
```

Expected: all tests PASS.

- [ ] **Step 2: Push and watch CI**

```bash
git push
gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
```

- [ ] **Step 3: Run migration on production after deploy**

After `docker compose pull && docker compose up -d`:

```bash
docker compose exec runcoach runcoach-migrate
```

Expected output: `Done: N migrated, 0 skipped.`

---

## What Does Not Change

- `fit_parser.py` — untouched
- Mobile app — `yaml_data` key and structure identical
- `.fit` files — stay on disk; `fit_path` column unchanged
- `yaml_path` / `md_path` columns — kept in schema, just stop being written (cleanup in follow-up PR tracked in project memory)
- LLM prompt format — YAML reconstructed from JSON; identical content
- Push notifications, Strava integration, Stryd sync — unaffected
