# Coach Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent conversational chat panel to the run detail page, letting athletes ask the AI coach follow-up questions about a specific workout.

**Architecture:** A new `run_chat` DB table stores the conversation history per run/user. A synchronous `POST /run/<id>/chat` web route (session auth) and `POST /api/v1/runs/<id>/chat` API endpoint (JWT auth) accept messages, call the LLM with full context (system prompt + weekly context YAML + workout YAML + prior history), persist both turns, and return the assistant response. The run detail page renders stored history on load and appends new turns via JS without a page reload.

**Tech Stack:** Python/Flask, SQLite (via existing `RunCoachDB`), OpenAI/Claude/Ollama (via existing `_dispatch_llm`), Jinja2, vanilla JS, pytest + pytest-playwright

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `runcoach/db.py` | Modify | Add `run_chat` table to `SCHEMA_SQL`; add `add_chat_message()` and `get_chat_history()` |
| `runcoach/analyzer.py` | Modify | Extract `_build_system_prompt()`; add `build_chat_context()` |
| `runcoach/web/api.py` | Modify | Add `GET/POST /api/v1/runs/<id>/chat` |
| `runcoach/web/routes.py` | Modify | Add `POST /run/<id>/chat`; update `run_detail()` to load history |
| `runcoach/web/templates/run_detail.html` | Modify | Add chat panel UI + JS |
| `tests/test_db.py` | Modify | Add `TestRunChat` class |
| `tests/test_analyzer.py` | Modify | Add tests for `build_chat_context()` |
| `tests/test_api.py` | Modify | Add `TestRunChat` class |
| `tests/test_web.py` | Modify | Add chat route + template render tests |
| `tests/e2e/test_chat.py` | Create | Playwright E2E tests (4 scenarios) |

---

## Task 1: DB — `run_chat` table and CRUD methods

**Files:**
- Modify: `runcoach/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing DB tests**

Add a new `TestRunChat` class to `tests/test_db.py`:

```python
class TestRunChat:
    def test_add_and_get_chat_messages(self, temp_db):
        run_id = temp_db.insert_run(
            stryd_activity_id=9001,
            name="Chat Test Run",
            date="2026-04-01",
            fit_path="activities/chat_test.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        msg_id = temp_db.add_chat_message(run_id, 1, "user", "What was my power?")
        assert msg_id > 0

        temp_db.add_chat_message(
            run_id, 1, "assistant",
            "Your average power was 200W.",
            model_used="llama3.2",
            prompt_tokens=100,
            completion_tokens=50,
        )

        history = temp_db.get_chat_history(run_id, 1)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["message"] == "What was my power?"
        assert history[1]["role"] == "assistant"
        assert history[1]["message"] == "Your average power was 200W."
        assert history[1]["model_used"] == "llama3.2"
        assert history[1]["prompt_tokens"] == 100
        assert history[1]["completion_tokens"] == 50

    def test_get_chat_history_user_isolation(self, temp_db):
        run_id = temp_db.insert_run(
            stryd_activity_id=9002,
            name="Isolation Run",
            date="2026-04-02",
            fit_path="activities/isolation.fit",
            distance_m=5000,
            moving_time_s=1500,
        )
        temp_db.add_chat_message(run_id, 1, "user", "User 1 question")
        temp_db.add_chat_message(run_id, 1, "assistant", "Reply to user 1")
        temp_db.add_chat_message(run_id, 2, "user", "User 2 question")
        temp_db.add_chat_message(run_id, 2, "assistant", "Reply to user 2")

        history_u1 = temp_db.get_chat_history(run_id, 1)
        history_u2 = temp_db.get_chat_history(run_id, 2)

        assert len(history_u1) == 2
        assert history_u1[0]["message"] == "User 1 question"
        assert len(history_u2) == 2
        assert history_u2[0]["message"] == "User 2 question"

    def test_get_chat_history_empty(self, temp_db):
        run_id = temp_db.insert_run(
            stryd_activity_id=9003,
            name="Empty Chat Run",
            date="2026-04-03",
            fit_path="activities/empty_chat.fit",
            distance_m=3000,
            moving_time_s=900,
        )
        history = temp_db.get_chat_history(run_id, 1)
        assert history == []

    def test_chat_messages_ordered_by_created_at(self, temp_db):
        run_id = temp_db.insert_run(
            stryd_activity_id=9004,
            name="Order Test Run",
            date="2026-04-04",
            fit_path="activities/order_test.fit",
            distance_m=4000,
            moving_time_s=1200,
        )
        temp_db.add_chat_message(run_id, 1, "user", "First question")
        temp_db.add_chat_message(run_id, 1, "assistant", "First reply")
        temp_db.add_chat_message(run_id, 1, "user", "Second question")
        temp_db.add_chat_message(run_id, 1, "assistant", "Second reply")

        history = temp_db.get_chat_history(run_id, 1)
        assert history[0]["message"] == "First question"
        assert history[1]["message"] == "First reply"
        assert history[2]["message"] == "Second question"
        assert history[3]["message"] == "Second reply"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
source .venv/bin/activate
pytest tests/test_db.py::TestRunChat -v
```

Expected: `AttributeError: 'RunCoachDB' object has no attribute 'add_chat_message'`

- [ ] **Step 3: Add `run_chat` table to `SCHEMA_SQL` in `runcoach/db.py`**

Find the end of `SCHEMA_SQL` (just before the closing `"""`). Add the new table after the `users` table definition:

```python
CREATE TABLE IF NOT EXISTS run_chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    message TEXT NOT NULL,
    model_used TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_run_chat_run_user ON run_chat(run_id, user_id);
```

- [ ] **Step 4: Add `add_chat_message()` and `get_chat_history()` methods to `RunCoachDB`**

Add both methods anywhere in the `RunCoachDB` class body (e.g. after `update_analyzed`):

```python
def add_chat_message(
    self,
    run_id: int,
    user_id: int,
    role: str,
    message: str,
    model_used: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> int:
    with self._connect() as conn:
        cur = conn.execute(
            """INSERT INTO run_chat
               (run_id, user_id, role, message, model_used,
                prompt_tokens, completion_tokens, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, user_id, role, message, model_used,
             prompt_tokens, completion_tokens, _now_iso()),
        )
        return cur.lastrowid

def get_chat_history(self, run_id: int, user_id: int) -> list[dict]:
    with self._connect() as conn:
        rows = conn.execute(
            """SELECT id, run_id, user_id, role, message,
                      model_used, prompt_tokens, completion_tokens, created_at
               FROM run_chat
               WHERE run_id = ? AND user_id = ?
               ORDER BY created_at ASC, id ASC""",
            (run_id, user_id),
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_db.py::TestRunChat -v
```

Expected: 4 tests PASS

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
pytest -m "not e2e" -q
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add runcoach/db.py tests/test_db.py
git commit -m "feat: add run_chat table and CRUD methods to RunCoachDB"
```

---

## Task 2: Analyzer — `_build_system_prompt()` and `build_chat_context()`

**Files:**
- Modify: `runcoach/analyzer.py`
- Modify: `tests/test_analyzer.py`

- [ ] **Step 1: Write failing tests for `build_chat_context()`**

Add to `tests/test_analyzer.py` (check existing imports there; add `from unittest.mock import MagicMock` if not present):

```python
class TestBuildChatContext:
    def test_returns_system_and_user_message(self, tmp_path):
        from unittest.mock import MagicMock
        from runcoach.analyzer import build_chat_context
        from runcoach.config import Config

        yaml_content = "date: '2026-04-01'\ncritical_power: 200\nblocks: []\n"
        (tmp_path / "test.yaml").write_text(yaml_content)

        run = {"date": "2026-04-01", "yaml_path": "test.yaml", "is_manual_upload": 0}
        config = Config(data_dir=tmp_path)
        db = MagicMock()
        db.get_athlete_profile.return_value = "Test athlete profile"
        db.get_race_goal.return_value = {"race_date": None, "race_distance": None}

        system_msg, user_msg = build_chat_context(
            run=run,
            user_id=1,
            history=[],
            new_message="What was my average power?",
            config=config,
            db=db,
        )

        assert isinstance(system_msg, str)
        assert len(system_msg) > 50
        assert "What was my average power?" in user_msg

    def test_history_included_in_user_message(self, tmp_path):
        from unittest.mock import MagicMock
        from runcoach.analyzer import build_chat_context
        from runcoach.config import Config

        yaml_content = "date: '2026-04-01'\ncritical_power: 200\nblocks: []\n"
        (tmp_path / "test.yaml").write_text(yaml_content)

        run = {"date": "2026-04-01", "yaml_path": "test.yaml", "is_manual_upload": 0}
        config = Config(data_dir=tmp_path)
        db = MagicMock()
        db.get_athlete_profile.return_value = ""
        db.get_race_goal.return_value = {"race_date": None, "race_distance": None}

        history = [
            {"role": "user", "message": "How was my heart rate?"},
            {"role": "assistant", "message": "Your HR averaged 145 bpm."},
        ]

        _, user_msg = build_chat_context(
            run=run, user_id=1, history=history,
            new_message="And my power?", config=config, db=db,
        )

        assert "How was my heart rate?" in user_msg
        assert "Your HR averaged 145 bpm." in user_msg
        assert "And my power?" in user_msg

    def test_manual_upload_flag_in_system_prompt(self, tmp_path):
        from unittest.mock import MagicMock
        from runcoach.analyzer import build_chat_context
        from runcoach.config import Config

        (tmp_path / "test.yaml").write_text("date: '2026-04-01'\nblocks: []\n")

        run = {"date": "2026-04-01", "yaml_path": "test.yaml", "is_manual_upload": 1}
        config = Config(data_dir=tmp_path)
        db = MagicMock()
        db.get_athlete_profile.return_value = ""
        db.get_race_goal.return_value = {"race_date": None, "race_distance": None}

        system_msg, _ = build_chat_context(
            run=run, user_id=1, history=[], new_message="Test", config=config, db=db
        )

        assert "manually uploaded" in system_msg.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_analyzer.py::TestBuildChatContext -v
```

Expected: `ImportError: cannot import name 'build_chat_context' from 'runcoach.analyzer'`

- [ ] **Step 3: Extract `_build_system_prompt()` helper in `runcoach/analyzer.py`**

Add the new helper **before** `analyze_run()`. It extracts the system prompt construction currently inline in `analyze_run()`:

```python
def _build_system_prompt(
    db: RunCoachDB | None,
    user_id: int | None,
    run_date: str | None = None,
    is_manual_upload: bool = False,
) -> str:
    schema = _load_schema()
    profile = _load_athlete_profile(db, user_id)
    system_msg = SYSTEM_PROMPT.format(schema=schema, athlete_profile=profile)

    race_goal = _load_race_goal(db, user_id)
    race_date_str = race_goal.get("race_date")
    race_distance = race_goal.get("race_distance")
    if race_date_str and race_distance:
        try:
            race_date_obj = date.fromisoformat(race_date_str)
            current = date.fromisoformat(run_date) if run_date else date.today()
            days_until = (race_date_obj - current).days
            phase = _training_phase(days_until)
            system_msg += RACE_CONTEXT_PROMPT.format(
                race_distance=race_distance,
                race_date=race_date_str,
                days_until_race=days_until,
                training_phase=phase,
                current_date=current.isoformat(),
            )
        except (ValueError, TypeError):
            pass

    if is_manual_upload:
        system_msg += (
            "\n\nNOTE: This run was manually uploaded and may not have Stryd power data. "
            "Do not penalise or comment on missing power data for manual uploads. "
            "Focus on HR, pace, and other available metrics instead."
        )

    return system_msg
```

- [ ] **Step 4: Refactor `analyze_run()` to use `_build_system_prompt()`**

Replace the system prompt building block in `analyze_run()` (lines 214–244 in the current file) with the simpler version:

```python
def analyze_run(
    yaml_content: str,
    config: Config,
    context_yaml: str | None = None,
    db: RunCoachDB | None = None,
    run_date: str | None = None,
    user_id: int | None = None,
) -> dict:
    is_manual = "manual_upload: true" in yaml_content
    system_msg = _build_system_prompt(db, user_id, run_date, is_manual_upload=is_manual)

    if context_yaml:
        user_msg = context_yaml.rstrip("\n") + "\n---\n" + yaml_content
    else:
        user_msg = yaml_content

    return _dispatch_llm(system_msg, user_msg, config)
```

- [ ] **Step 5: Add `build_chat_context()` to `runcoach/analyzer.py`**

Add after `analyze_run()`:

```python
def build_chat_context(
    run: dict,
    user_id: int,
    history: list[dict],
    new_message: str,
    config: Config,
    db: RunCoachDB,
) -> tuple[str, str]:
    run_date = run.get("date")
    is_manual = bool(run.get("is_manual_upload"))
    system_msg = _build_system_prompt(db, user_id, run_date, is_manual_upload=is_manual)

    yaml_path = config.data_dir / run["yaml_path"]
    yaml_content = yaml_path.read_text(encoding="utf-8")

    context_yaml = None
    try:
        parsed = yaml.safe_load(yaml_content)
        current_cp = parsed.get("critical_power")
        if run_date:
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
                log.warning("Failed to build training summary for chat context")
            context_yaml = yaml.safe_dump(context, sort_keys=False, allow_unicode=True)
    except Exception:
        log.exception("Failed to build training context for chat, proceeding without it")

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

    return system_msg, "\n".join(parts)
```

- [ ] **Step 6: Run analyzer tests to confirm they pass**

```bash
pytest tests/test_analyzer.py -v
```

Expected: all tests pass (including the new `TestBuildChatContext` tests)

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
pytest -m "not e2e" -q
```

Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add runcoach/analyzer.py tests/test_analyzer.py
git commit -m "feat: extract _build_system_prompt and add build_chat_context to analyzer"
```

---

## Task 3: API endpoints — `GET/POST /api/v1/runs/<id>/chat`

**Files:**
- Modify: `runcoach/web/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Add a new `TestRunChat` class to `tests/test_api.py`. Add `from unittest.mock import patch` at the top if not already present.

```python
class TestRunChat:
    def test_get_chat_history_empty(self, client, auth_headers, app):
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=8001,
            name="Chat Run",
            date="2026-04-01",
            fit_path="activities/chat.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        resp = client.get(f"/api/v1/runs/{run_id}/chat", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["history"] == []

    def test_get_chat_history_with_messages(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=8002,
            name="Chat Run 2",
            date="2026-04-02",
            fit_path="activities/chat2.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        db.add_chat_message(run_id, user_id, "user", "How was my power?")
        db.add_chat_message(run_id, user_id, "assistant", "Your power was great.")

        resp = client.get(f"/api/v1/runs/{run_id}/chat", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["history"]) == 2
        assert data["history"][0]["role"] == "user"
        assert data["history"][1]["role"] == "assistant"

    def test_post_chat_returns_assistant_response(self, client, auth_headers, app):
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=8003,
            name="Chat Run 3",
            date="2026-04-03",
            fit_path="activities/chat3.fit",
            distance_m=8000,
            moving_time_s=2400,
        )

        with patch("runcoach.web.api.build_chat_context") as mock_ctx, \
             patch("runcoach.web.api._dispatch_llm") as mock_llm:
            mock_ctx.return_value = ("system prompt text", "user message text")
            mock_llm.return_value = {
                "commentary": "Your power was excellent at 220W average.",
                "prompt_tokens": 150,
                "completion_tokens": 60,
            }
            resp = client.post(
                f"/api/v1/runs/{run_id}/chat",
                json={"message": "How was my power?"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["role"] == "assistant"
        assert data["message"] == "Your power was excellent at 220W average."
        assert data["prompt_tokens"] == 150
        assert data["completion_tokens"] == 60
        assert "created_at" in data

    def test_post_chat_persists_both_turns(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=8004,
            name="Chat Run 4",
            date="2026-04-04",
            fit_path="activities/chat4.fit",
            distance_m=8000,
            moving_time_s=2400,
        )

        with patch("runcoach.web.api.build_chat_context") as mock_ctx, \
             patch("runcoach.web.api._dispatch_llm") as mock_llm:
            mock_ctx.return_value = ("sys", "usr")
            mock_llm.return_value = {
                "commentary": "Great run!",
                "prompt_tokens": 100,
                "completion_tokens": 30,
            }
            client.post(
                f"/api/v1/runs/{run_id}/chat",
                json={"message": "Was it good?"},
                headers=auth_headers,
            )

        history = db.get_chat_history(run_id, user_id)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["message"] == "Was it good?"
        assert history[1]["role"] == "assistant"
        assert history[1]["message"] == "Great run!"

    def test_post_chat_wrong_user_returns_404(self, client, app):
        from runcoach.auth import create_access_token, hash_password
        db = app.config["db"]

        other_user_id = db.create_user("other_user_chat", hash_password("pass"))
        other_token = create_access_token(other_user_id, app.config["SECRET_KEY"])
        other_headers = {"Authorization": f"Bearer {other_token}"}

        run_id = db.insert_run(
            stryd_activity_id=8005,
            name="Private Run",
            date="2026-04-05",
            fit_path="activities/private.fit",
            distance_m=8000,
            moving_time_s=2400,
        )

        resp = client.get(f"/api/v1/runs/{run_id}/chat", headers=other_headers)
        assert resp.status_code == 404

    def test_post_chat_empty_message_returns_400(self, client, auth_headers, app):
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=8006,
            name="Chat Run 6",
            date="2026-04-06",
            fit_path="activities/chat6.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        resp = client.post(
            f"/api/v1/runs/{run_id}/chat",
            json={"message": "  "},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_post_chat_llm_error_returns_502_nothing_persisted(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=8007,
            name="Chat Run 7",
            date="2026-04-07",
            fit_path="activities/chat7.fit",
            distance_m=8000,
            moving_time_s=2400,
        )

        with patch("runcoach.web.api.build_chat_context") as mock_ctx, \
             patch("runcoach.web.api._dispatch_llm") as mock_llm:
            mock_ctx.return_value = ("sys", "usr")
            mock_llm.side_effect = RuntimeError("LLM unavailable")
            resp = client.post(
                f"/api/v1/runs/{run_id}/chat",
                json={"message": "Test"},
                headers=auth_headers,
            )

        assert resp.status_code == 502
        assert db.get_chat_history(run_id, user_id) == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_api.py::TestRunChat -v
```

Expected: `404 NOT FOUND` (endpoints not yet registered)

- [ ] **Step 3: Add imports and endpoints to `runcoach/web/api.py`**

Add to the imports at the top of `api.py` (check existing imports to avoid duplicates):

```python
from runcoach.analyzer import _dispatch_llm, build_chat_context
```

Then add both endpoints after the existing `get_run` endpoint:

```python
@api_bp.route("/runs/<int:run_id>/chat", methods=["GET"])
@require_auth
def get_run_chat(run_id: int):
    db = get_db()
    run = db.get_run(run_id, user_id=request.user_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    history = db.get_chat_history(run_id, user_id=request.user_id)
    return jsonify({
        "history": [
            {"role": h["role"], "message": h["message"], "created_at": h["created_at"]}
            for h in history
        ]
    }), 200


@api_bp.route("/runs/<int:run_id>/chat", methods=["POST"])
@require_auth
def post_run_chat(run_id: int):
    db = get_db()
    config = current_app.config["config"]
    run = db.get_run(run_id, user_id=request.user_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404

    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    history = db.get_chat_history(run_id, user_id=request.user_id)

    try:
        system_msg, user_msg = build_chat_context(
            run=run,
            user_id=request.user_id,
            history=history,
            new_message=message,
            config=config,
            db=db,
        )
        result = _dispatch_llm(system_msg, user_msg, config)
    except Exception as e:
        log.exception("Chat LLM error for run %s: %s", run_id, e)
        return jsonify({"error": "LLM request failed"}), 502

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    db.add_chat_message(run_id, request.user_id, "user", message)
    db.add_chat_message(
        run_id, request.user_id, "assistant",
        result["commentary"],
        model_used=config.active_model,
        prompt_tokens=result.get("prompt_tokens"),
        completion_tokens=result.get("completion_tokens"),
    )

    return jsonify({
        "role": "assistant",
        "message": result["commentary"],
        "model_used": config.active_model,
        "prompt_tokens": result.get("prompt_tokens"),
        "completion_tokens": result.get("completion_tokens"),
        "created_at": now,
    }), 200
```

- [ ] **Step 4: Run API tests to confirm they pass**

```bash
pytest tests/test_api.py::TestRunChat -v
```

Expected: all 7 tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
pytest -m "not e2e" -q
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add runcoach/web/api.py tests/test_api.py
git commit -m "feat: add GET/POST /api/v1/runs/<id>/chat endpoints"
```

---

## Task 4: Web Route — `POST /run/<id>/chat` + update `run_detail()`

**Files:**
- Modify: `runcoach/web/routes.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write failing web tests**

Add to `tests/test_web.py` (add `from unittest.mock import patch` if not present):

```python
class TestRunChat:
    def test_run_detail_includes_chat_history(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=7001,
            name="Chat Web Run",
            date="2026-04-01",
            fit_path="activities/chat_web.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        db.update_analyzed(
            run_id=run_id,
            md_path="activities/chat_web.md",
            commentary="Good run.",
            model_used="llama3.2",
            prompt_tokens=50,
            completion_tokens=20,
        )
        db.add_chat_message(run_id, user_id, "user", "How was my power?")
        db.add_chat_message(run_id, user_id, "assistant", "Your power was **200W**.")

        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        resp = client.get(f"/run/{run_id}")
        assert resp.status_code == 200
        assert b"How was my power?" in resp.data
        assert b"200W" in resp.data  # markdown rendered to HTML

    def test_chat_route_returns_assistant_response(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=7002,
            name="Chat Route Run",
            date="2026-04-02",
            fit_path="activities/chat_route.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        db.update_analyzed(
            run_id=run_id,
            md_path="activities/chat_route.md",
            commentary="Nice session.",
            model_used="llama3.2",
            prompt_tokens=50,
            completion_tokens=20,
        )

        with client.session_transaction() as sess:
            sess["user_id"] = user_id

        with patch("runcoach.web.routes.build_chat_context") as mock_ctx, \
             patch("runcoach.web.routes._dispatch_llm") as mock_llm:
            mock_ctx.return_value = ("sys", "usr")
            mock_llm.return_value = {
                "commentary": "Your HR looked great.",
                "prompt_tokens": 80,
                "completion_tokens": 25,
            }
            resp = client.post(
                f"/run/{run_id}/chat",
                json={"message": "How was my HR?"},
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["role"] == "assistant"
        assert data["message"] == "Your HR looked great."
        assert "message_html" in data

    def test_chat_route_unauthenticated_redirects(self, client, app):
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=7003,
            name="Auth Run",
            date="2026-04-03",
            fit_path="activities/auth.fit",
            distance_m=5000,
            moving_time_s=1500,
        )
        resp = client.post(
            f"/run/{run_id}/chat",
            json={"message": "test"},
            content_type="application/json",
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_web.py::TestRunChat -v
```

Expected: failures (route not registered, template variable missing)

- [ ] **Step 3: Add imports to `runcoach/web/routes.py`**

Add to the existing imports at the top of `routes.py`:

```python
from runcoach.analyzer import _dispatch_llm, build_chat_context
```

- [ ] **Step 4: Update `run_detail()` to load chat history**

Inside `run_detail()`, after the block that builds `commentary_html`, add:

```python
chat_history_raw = db.get_chat_history(run_id, user_id=user_id)
chat_history_html = [
    {
        **msg,
        "message_html": _safe_markdown(msg["message"]) if msg["role"] == "assistant" else None,
    }
    for msg in chat_history_raw
]
```

Then add `chat_history_html=chat_history_html` to the `render_template(...)` call at the end of `run_detail()`.

- [ ] **Step 5: Add `POST /run/<id>/chat` route**

Add after the `analyze_run_route()` function:

```python
@bp.route("/run/<int:run_id>/chat", methods=["POST"])
@_login_required
def run_chat(run_id: int):
    db = _db()
    user_id = _current_user_id()
    config: Config = current_app.config["config"]
    run = db.get_run(run_id, user_id=user_id)

    if run is None:
        return jsonify({"error": "Run not found"}), 404

    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    history = db.get_chat_history(run_id, user_id=user_id)

    try:
        system_msg, user_msg = build_chat_context(
            run=run,
            user_id=user_id,
            history=history,
            new_message=message,
            config=config,
            db=db,
        )
        result = _dispatch_llm(system_msg, user_msg, config)
    except Exception as e:
        log.exception("Chat LLM error for run %s: %s", run_id, e)
        return jsonify({"error": "LLM request failed"}), 502

    db.add_chat_message(run_id, user_id, "user", message)
    db.add_chat_message(
        run_id, user_id, "assistant",
        result["commentary"],
        model_used=config.active_model,
        prompt_tokens=result.get("prompt_tokens"),
        completion_tokens=result.get("completion_tokens"),
    )

    return jsonify({
        "role": "assistant",
        "message": result["commentary"],
        # message_html is server-sanitized via nh3 (same as commentary_html elsewhere)
        "message_html": _safe_markdown(result["commentary"]),
    }), 200
```

- [ ] **Step 6: Run web tests to confirm they pass**

```bash
pytest tests/test_web.py::TestRunChat -v
```

Expected: all 3 tests PASS

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
pytest -m "not e2e" -q
```

Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add runcoach/web/routes.py tests/test_web.py
git commit -m "feat: add POST /run/<id>/chat web route and load chat history in run_detail"
```

---

## Task 5: UI — chat panel in `run_detail.html`

**Files:**
- Modify: `runcoach/web/templates/run_detail.html`

- [ ] **Step 1: Locate the Coach Analysis card in the template**

Open `runcoach/web/templates/run_detail.html`. Find the section rendering `commentary_html` (search for `class="commentary"`). The chat panel goes immediately after this card's closing `</div>`.

- [ ] **Step 2: Add the chat panel HTML**

After the Coach Analysis card closing tag, add:

```html
{% if run.stage == 'analyzed' %}
<div class="card" id="chat-panel">
  <h2>Ask the Coach</h2>

  <div class="chat-history" id="chat-history">
    {% for msg in chat_history_html %}
    <div class="chat-message chat-message--{{ msg.role }}">
      {% if msg.role == 'user' %}
        <p class="chat-bubble chat-bubble--user">{{ msg.message }}</p>
      {% else %}
        <div class="chat-bubble chat-bubble--assistant">{{ msg.message_html | safe }}</div>
      {% endif %}
    </div>
    {% endfor %}
  </div>

  <form id="chat-form" class="chat-form">
    <textarea
      id="chat-input"
      name="message"
      placeholder="Ask a follow-up question…"
      rows="2"
      required
    ></textarea>
    <div class="chat-form-actions">
      <button type="submit" id="chat-submit">Ask</button>
      <span id="chat-spinner" style="display:none">Thinking…</span>
    </div>
  </form>
  <p id="chat-error" class="chat-error" style="display:none"></p>
</div>
{% endif %}
```

- [ ] **Step 3: Add CSS for the chat panel**

In the `<style>` block of `run_detail.html` (or `base.html` if styles are centralised there), add:

```css
.chat-history {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
  max-height: 400px;
  overflow-y: auto;
}
.chat-message--user { align-self: flex-end; max-width: 80%; }
.chat-message--assistant { align-self: flex-start; max-width: 90%; }
.chat-bubble--user {
  background: var(--accent, #3b82f6);
  color: #fff;
  border-radius: 1rem 1rem 0.25rem 1rem;
  padding: 0.5rem 0.9rem;
  margin: 0;
}
.chat-bubble--assistant {
  background: var(--card-bg, #f9fafb);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 1rem 1rem 1rem 0.25rem;
  padding: 0.5rem 0.9rem;
}
.chat-form { display: flex; flex-direction: column; gap: 0.5rem; }
.chat-form textarea {
  width: 100%;
  resize: vertical;
  padding: 0.5rem;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 0.375rem;
  font-family: inherit;
  font-size: 0.9rem;
}
.chat-form-actions { display: flex; align-items: center; gap: 0.75rem; }
.chat-error { color: #dc2626; font-size: 0.875rem; margin-top: 0.25rem; }
```

- [ ] **Step 4: Add JavaScript for the chat interaction**

Just before `</body>` (or in the page's existing script block), add:

```html
<script>
(function () {
  var form = document.getElementById('chat-form');
  if (!form) return;

  function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    var input = document.getElementById('chat-input');
    var message = input.value.trim();
    if (!message) return;

    var submitBtn = document.getElementById('chat-submit');
    var spinner   = document.getElementById('chat-spinner');
    var errorEl   = document.getElementById('chat-error');
    var history   = document.getElementById('chat-history');

    submitBtn.disabled = true;
    spinner.style.display = 'inline';
    errorEl.style.display = 'none';
    input.value = '';

    var userDiv = document.createElement('div');
    userDiv.className = 'chat-message chat-message--user';
    var userBubble = document.createElement('p');
    userBubble.className = 'chat-bubble chat-bubble--user';
    userBubble.textContent = message;
    userDiv.appendChild(userBubble);
    history.appendChild(userDiv);
    history.scrollTop = history.scrollHeight;

    try {
      var resp = await fetch(window.location.pathname + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message }),
      });
      var data = await resp.json();
      if (!resp.ok) {
        errorEl.textContent = data.error || 'Something went wrong. Please try again.';
        errorEl.style.display = 'block';
      } else {
        var assistantDiv = document.createElement('div');
        assistantDiv.className = 'chat-message chat-message--assistant';
        var assistantBubble = document.createElement('div');
        assistantBubble.className = 'chat-bubble chat-bubble--assistant';
        // message_html is sanitized server-side by nh3 (same pipeline as commentary_html)
        assistantBubble.innerHTML = data.message_html;
        assistantDiv.appendChild(assistantBubble);
        history.appendChild(assistantDiv);
        history.scrollTop = history.scrollHeight;
      }
    } catch (err) {
      errorEl.textContent = 'Network error. Please try again.';
      errorEl.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      spinner.style.display = 'none';
    }
  });
})();
</script>
```

Note: `assistantBubble.innerHTML = data.message_html` is safe here because `message_html` is produced by `_safe_markdown()` on the server, which sanitizes via `nh3` with an allowlist — the same pipeline used for `commentary_html` rendered throughout the app. Plain user text is set via `.textContent` (no XSS risk).

- [ ] **Step 5: Verify manually in the browser**

```bash
source .venv/bin/activate
python -m runcoach.web
```

Open http://localhost:5000. Navigate to an analyzed run and verify:
- Chat panel appears below Coach Analysis
- Existing history (if any) renders correctly
- Typing a question and clicking Ask shows spinner, then appends user bubble and coach response
- Refreshing the page shows the conversation from DB
- Unanalyzed run has no chat panel

- [ ] **Step 6: Run full unit test suite**

```bash
pytest -m "not e2e" -q
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add runcoach/web/templates/run_detail.html
git commit -m "feat: add chat panel UI to run detail page"
```

---

## Task 6: Playwright E2E tests

**Files:**
- Create: `tests/e2e/test_chat.py`

- [ ] **Step 1: Create `tests/e2e/test_chat.py`**

```python
"""Playwright E2E tests for the coach chat feature."""
from __future__ import annotations

import pytest

from tests.e2e.conftest import SAMPLE_YAML_REL

pytestmark = pytest.mark.e2e


@pytest.fixture
def analyzed_run_id(flask_server, e2e_data_dir):
    """Insert a fresh analyzed run for chat tests (function-scoped for isolation)."""
    from runcoach.db import RunCoachDB

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    run_id = db.insert_manual_run(
        "Chat E2E Test Run", "2026-02-10",
        "activities/2026/02/chat_e2e/chat_e2e.fit", 9000, 2700,
    )
    db.update_parsed(run_id, SAMPLE_YAML_REL, 185.0, 148, "Chat E2E Test Run")
    db.update_analyzed(
        run_id=run_id,
        md_path="activities/2026/02/chat_e2e/chat_e2e.md",
        commentary=(
            "Great effort today! Power was consistent throughout the warmup. "
            "Heart rate stayed in Z2 — ideal for aerobic development."
        ),
        model_used="llama3.2",
        prompt_tokens=120,
        completion_tokens=55,
    )
    return run_id


@pytest.fixture
def parsed_only_run_id(flask_server, e2e_data_dir):
    """Insert a parsed-only run (no commentary) for testing chat panel absence."""
    from runcoach.db import RunCoachDB

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    run_id = db.insert_manual_run(
        "Parsed Only E2E Run", "2026-02-11",
        "activities/2026/02/parsed_only_e2e/parsed_only_e2e.fit", 5000, 1800,
    )
    db.update_parsed(run_id, SAMPLE_YAML_REL, 170.0, 140, "Parsed Only E2E Run")
    return run_id


def test_chat_panel_visible_on_analyzed_run(logged_in_page, server_url, analyzed_run_id):
    """The chat panel appears on an analyzed run page."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{analyzed_run_id}")
    assert page.locator("#chat-panel").is_visible()
    assert page.locator("#chat-input").is_visible()
    assert page.locator("#chat-submit").is_visible()


def test_send_message_shows_response(logged_in_page, server_url, analyzed_run_id):
    """Submitting a question appends a coach response to the chat history."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{analyzed_run_id}")
    page.locator("#chat-input").fill("What was my average heart rate?")
    page.locator("#chat-submit").click()
    page.wait_for_selector(".chat-message--assistant", timeout=30_000)

    assistant_messages = page.locator(".chat-message--assistant").all()
    assert len(assistant_messages) >= 1
    assert len(assistant_messages[-1].text_content().strip()) > 10


def test_chat_history_persists_after_reload(logged_in_page, server_url, analyzed_run_id):
    """After a chat turn, reloading the page still shows the conversation."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{analyzed_run_id}")
    page.locator("#chat-input").fill("How did my power look in the warmup?")
    page.locator("#chat-submit").click()
    page.wait_for_selector(".chat-message--assistant", timeout=30_000)

    page.reload()
    page.wait_for_load_state("networkidle")

    assert page.locator(".chat-message--user").count() >= 1
    assert page.locator(".chat-message--assistant").count() >= 1


def test_chat_panel_not_shown_for_unanalyzed_run(
    logged_in_page, server_url, parsed_only_run_id
):
    """The chat panel is absent on a run that has not been analyzed yet."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{parsed_only_run_id}")
    assert not page.locator("#chat-panel").is_visible()
```

- [ ] **Step 2: Run the new E2E tests**

```bash
source .venv/bin/activate
pytest tests/e2e/test_chat.py -v --tb=short
```

Expected: all 4 tests PASS

- [ ] **Step 3: Run the full E2E suite to check for regressions**

```bash
pytest tests/e2e/ -m e2e -v --tb=short
```

Expected: all E2E tests pass

- [ ] **Step 4: Run the complete test suite (unit + E2E)**

```bash
pytest -v --tb=short
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_chat.py
git commit -m "feat: add Playwright E2E tests for coach chat feature"
```

---

## Success Criteria (from spec)

All of the following must be confirmed before the feature is complete:

1. `pytest -m "not e2e" -q` — all unit tests pass
2. `pytest tests/e2e/ -m e2e` — all Playwright E2E tests pass (including `test_chat.py`)
3. Manual smoke test on dev server:
   - Analyzed run → chat panel visible → question → spinner → response rendered below
   - Page reload → conversation history still present
   - Unanalyzed run → no chat panel
4. API smoke: `GET /api/v1/runs/<id>/chat` with a valid JWT returns the same history visible in the browser
