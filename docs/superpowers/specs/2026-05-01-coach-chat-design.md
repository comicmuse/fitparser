# Coach Chat Feature Design

**Date:** 2026-05-01  
**Status:** Approved

## Context

RunCoach currently generates a one-shot AI analysis of each workout. Once the commentary is written there is no way for the athlete to ask follow-up questions. This feature adds a persistent, conversational chat interface so the athlete can engage the AI coach about a specific run — asking about pacing decisions, block-level power data, how the session compares to recent load, etc.

## Design

### Database

New table `run_chat` added via inline migration in `db.py`:

```sql
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
```

Each conversational turn produces two rows: one `role='user'` and one `role='assistant'`. History is ordered by `created_at`. Token columns are `NULL` on the user row.

New DB methods:
- `add_chat_message(run_id, user_id, role, message, model_used=None, prompt_tokens=None, completion_tokens=None) -> int`
- `get_chat_history(run_id, user_id) -> list[dict]`

### API Endpoints

Both endpoints in `runcoach/web/api.py`, behind `@require_auth`. Both verify `run.user_id == request.user_id` before proceeding.

**`GET /api/v1/runs/<id>/chat`**  
Returns full conversation history.

Response:
```json
{
  "history": [
    {"role": "user", "message": "...", "created_at": "..."},
    {"role": "assistant", "message": "...", "created_at": "..."}
  ]
}
```

**`POST /api/v1/runs/<id>/chat`**  
Accepts `{"message": "..."}`. Synchronous — blocks while LLM responds.

1. Validates run ownership
2. Calls `build_chat_context()` to assemble prompt
3. Calls `_dispatch_llm()` (unchanged)
4. Persists both turns to `run_chat`
5. Returns the assistant turn

Response:
```json
{
  "role": "assistant",
  "message": "...",
  "model_used": "gpt-4o",
  "prompt_tokens": 1200,
  "completion_tokens": 320,
  "created_at": "2026-05-01T10:00:00Z"
}
```

Error response (LLM failure, invalid input):
```json
{"error": "..."}  // 400 or 502
```
Nothing is persisted on error.

### LLM Context

New function `build_chat_context(run, user_id, history, new_message, config, db)` in `runcoach/analyzer.py`:

- **System message:** same as `analyze_run()` — athlete profile + race context injected via existing helpers
- **User message:** assembled as:
  1. Weekly training context YAML (from `build_weekly_context()`)
  2. Workout YAML (loaded from `run['yaml_path']`)
  3. Prior conversation transcript (formatted as `User: ... / Coach: ...` pairs)
  4. The new user question

Reuses `_dispatch_llm(system_msg, user_msg, config)` without modification. Works transparently across OpenAI, Claude, and Ollama.

### Web UI

Changes in `runcoach/web/templates/run_detail.html` and `runcoach/web/routes.py`:

- `run_detail()` route loads chat history from DB and passes it to the template
- Assistant messages rendered via `_safe_markdown()` (existing sanitiser)
- Chat panel rendered below the "Coach Analysis" card
- A new web route `POST /run/<id>/chat` in `routes.py` handles the browser chat submission using `@login_required` (session cookie auth, same as all other web routes). This keeps web auth consistent — no JWT needed from the browser.
- Input field + "Ask" button; on submit, JS POSTs to `/run/<id>/chat` (the session-auth web route), shows a spinner, then appends both the user message and assistant response to the panel without a page reload
- On LLM error, a brief inline error message is shown
- The API endpoints (`GET/POST /api/v1/runs/<id>/chat`) remain the mobile path, using JWT auth

### Tests

**Unit tests:**

- `tests/test_api.py` — new `TestRunChat` class:
  - POST sends message, gets assistant response (mock `_dispatch_llm`)
  - GET returns persisted history
  - POST by different user returns 403/404
  - POST with LLM error returns 502 and nothing persisted
- `tests/test_web.py` — confirm chat history renders in run detail template; confirm new `/run/<id>/chat` web route returns assistant message JSON
- `tests/test_db.py` — `add_chat_message` and `get_chat_history` round-trip

**Playwright E2E tests** (`tests/e2e/test_chat.py`):

Follows the existing patterns in `tests/e2e/` — uses `logged_in_page`, `flask_server`, and the mock Ollama server (same `_dispatch_llm()` pathway, so mock works automatically).

- `test_chat_panel_visible_on_analyzed_run` — run detail page for an analyzed run shows the chat input and "Ask" button
- `test_send_message_shows_response` — type a question, click Ask, spinner appears, response appended to panel (wait for `.chat-response` or equivalent selector)
- `test_chat_history_persists_after_reload` — after a successful chat turn, reload the page and verify both the user message and assistant response are still visible
- `test_chat_panel_not_shown_for_unanalyzed_run` — chat input is absent on a run that hasn't been analyzed yet (no commentary to follow up on)

## Files to Modify

| File | Change |
|---|---|
| `runcoach/db.py` | Add `run_chat` table migration + `add_chat_message()` + `get_chat_history()` |
| `runcoach/analyzer.py` | Add `build_chat_context()` helper |
| `runcoach/web/api.py` | Add `GET/POST /api/v1/runs/<id>/chat` endpoints |
| `runcoach/web/routes.py` | Load chat history in `run_detail()`, add `POST /run/<id>/chat` web route |
| `runcoach/web/templates/run_detail.html` | Add chat panel UI + JS |
| `tests/test_api.py` | Add `TestRunChat` test class |
| `tests/test_web.py` | Add chat panel render test + web route test |
| `tests/test_db.py` | Add chat DB method tests |
| `tests/e2e/test_chat.py` | New Playwright E2E test module (4 tests) |

## Success Criteria

All of the following must pass before the feature is considered complete:

1. `pytest -m "not e2e"` — all unit tests pass (including new `TestRunChat`, DB, and web route tests)
2. `pytest tests/e2e/ -m e2e` — all Playwright E2E tests pass (including new `tests/e2e/test_chat.py`)
3. Manual smoke test:
   - Start dev server, open an analyzed run
   - Type a follow-up question → spinner appears → response rendered below
   - Reload page → conversation history still visible
   - Open an unanalyzed run → chat panel absent
4. API smoke test: `GET /api/v1/runs/<id>/chat` with a valid JWT returns the same history seen in the browser
