# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RunCoach is an automated running workout analysis system that syncs activities from Stryd, parses Garmin FIT files into structured workout blocks, and generates AI coaching commentary using a configurable LLM (OpenAI, Claude, or Ollama). It's a Progressive Web App (PWA).

The system has three main stages:
1. **Sync** — authenticate with Stryd API, download new FIT files
2. **Parse** — convert FIT → structured block data (power/HR/pace/zones) stored as JSON in `runs.parsed_data`
3. **Analyze** — send workout data + 7-day training context (ATL/CTL/RSB) to OpenAI, store commentary in DB

## Working on GitHub Issues

When implementing a GitHub issue:

1. **Create a feature branch** — never implement issue work directly on `main`:
   ```bash
   git checkout -b feature/issue-<number>-<short-description>
   ```
2. **Raise a PR** against `main` when the work is complete and tests pass, referencing the issue:
   ```bash
   gh pr create --title "..." --body "Closes #<number> ..."
   ```
3. **Close the issue** — use `gh issue close <number>` once the PR is merged (or include `Closes #<number>` in the PR body so GitHub closes it automatically on merge).

## Development Commands

### Local Setup

This project uses a `.venv` virtual environment. **The venv is activated before Claude starts** — do not prefix commands with `source .venv/bin/activate`. Check `VIRTUAL_ENV` is set at the start of a session and warn the user if it is absent. **NEVER** install packages or run commands using the global Python installation.

```bash
# Create virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Copy and configure environment
cp .env.example .env
# Edit .env with Stryd credentials, OpenAI API key, etc.
```

### Running the Application
```bash
# Start web server (default port 5000)
python -m runcoach.web
# or
runcoach

# Run full pipeline manually (sync + parse + analyze)
runcoach-pipeline
```

### Docker Deployment
```bash
# Build the Docker image
docker compose build

# Start the container (builds automatically if needed)
docker compose up -d

# View logs
docker compose logs -f

# Stop the container
docker compose down

# Rebuild and restart after code changes
docker compose up -d --build
```

**Note:** Ensure your user is in the `docker` group to run Docker commands without sudo:
```bash
sudo usermod -aG docker $USER
# Then log out and back in for the change to take effect
```

### Production Deployment

Production runs via Docker on this machine at `/srv/runcoach`. CI builds and pushes the image to `ghcr.io/comicmuse/fitparser:latest` on every push to `main`. To deploy:

```bash
cd /srv/runcoach
docker compose pull
docker compose up -d
```

### Testing Individual Components
```bash
# Parse a single FIT file and store parsed data in DB
runcoach-cli parse --file path/to/file.fit

# Analyze a run by DB ID
runcoach-cli analyze --run-id 42

# Analyze all parsed runs on a given date
runcoach-cli analyze --date 2026-05-01

# Back-fill parsed_data for all historical runs (run once after deploy)
runcoach-migrate
```

### Pre-Merge Test Command

**Before merging any branch, run the full test suite — all of the following are required to pass:**

```bash
pytest && pytest -m e2e --no-cov -v
```

```bash
# If any Flutter files were changed:
cd mobile && dart format --output=none --set-exit-if-changed . && flutter test
```

Unit tests alone are not sufficient. E2E tests cover web routes and templates that unit tests do not exercise end-to-end. `dart format` is enforced by CI — always run it before committing Flutter changes.

### Running Tests

The project includes comprehensive unit and Playwright E2E tests. Always run tests before committing changes.

```bash
# Install test dependencies (first time only)
pip install -e ".[dev]"

# Run all tests
pytest

# Run all tests with verbose output
pytest -v

# Run tests with coverage report
pytest --cov=runcoach --cov-report=term-missing

# Run specific test file
pytest tests/test_context.py

# Run specific test function
pytest tests/test_context.py::TestComputeRSS::test_compute_rss_normal

# Run tests quietly (less output)
pytest -q

# Generate HTML coverage report
pytest --cov=runcoach --cov-report=html
# Open htmlcov/index.html in browser to view detailed coverage
```

**Test Structure:**
- `tests/test_context.py` - Training context and RSS calculations
- `tests/test_db.py` - Database CRUD operations
- `tests/test_analyzer.py` - AI analysis with mocked OpenAI
- `tests/test_fit_parser.py` - FIT file parsing
- `tests/test_parser.py` - Parser integration
- `tests/test_web.py` - Flask web UI routes, login, profile sanitization
- `tests/test_api.py` - JWT REST API endpoints
- `tests/test_pipeline.py` - Pipeline orchestration (sync/parse/analyze stages)
- `tests/test_sync.py` - Stryd sync
- `tests/conftest.py` - Shared fixtures (temp databases, mock clients, sample files)

**Testing Best Practices:**
- External APIs (OpenAI, Stryd) are mocked to avoid costs and rate limits
- Tests use temporary databases and directories (`tmp_path` fixture)
- Real FIT/YAML files from `data/activities/` are used for integration tests
- All timestamps use ISO 8601 format like production code
- Always update **both** Python unit tests (`tests/test_*.py`) **and** Playwright E2E tests (`tests/e2e/`) when making changes to web routes or templates. Run E2E tests with `pytest -m e2e --no-cov -v`.

## Architecture

### Core Pipeline (`runcoach/pipeline.py`)
The `run_full_pipeline()` function orchestrates all three stages sequentially. It's executed:
- Automatically on a configurable schedule (via `scheduler.py`)
- Manually via the "Sync Now" button in the web UI
- Via CLI with `runcoach-pipeline`

Uses a threading lock to prevent concurrent pipeline runs.

### Data Flow
1. **Sync** (`sync.py`) → Downloads FIT files from Stryd, stores metadata in SQLite with stage='synced'
2. **Parse** (`parser.py`) → Calls `fit_parser.py` to segment FIT into workout blocks (warmup/work/rest/cooldown), stores JSON in `runs.parsed_data`, updates DB to stage='parsed'
3. **Analyze** (`analyzer.py`) → Builds weekly training context via `context.py`, sends to OpenAI with athlete profile + schema, stores commentary in `runs.commentary`, updates DB to stage='analyzed'

### Database Schema (`db.py`)
- **runs** table: tracks activity progression through pipeline stages (synced → parsed → analyzed → error)
  - `stryd_activity_id`: links to Stryd API (nullable for manual uploads)
  - `stage`: current pipeline stage
  - `is_manual_upload`: distinguishes manual FIT uploads from Stryd sync
  - `parsed_data`: JSON-serialised output of `build_blocks_from_fit()`
  - `commentary`: AI coaching markdown text
- **planned_workouts** table: stores prescribed workouts from Stryd training calendar
- **sync_log** table: audit trail of sync operations

Uses WAL mode for better concurrency.

### Training Context (`context.py`)
Builds a 7-day training summary before each analysis:
- **RSS (Running Stress Score)**: `(duration_h) * (avg_power / CP)^2 * 100`
- **ATL (Acute Training Load)**: 7-day average daily RSS
- **CTL (Chronic Training Load)**: 42-day average daily RSS
- **RSB (Running Stress Balance)**: CTL - ATL (positive = fresh, negative = fatigued)

Also includes:
- Prescribed workout from Stryd training plan (if available)
- Next 2 scheduled workouts (for forward-looking advice)

### FIT Parsing (`runcoach/fit_parser.py`)
Core module for converting Garmin FIT files to structured workout data:
- Extracts workout steps and laps from FIT files
- Maps steps to laps by index
- Calculates per-block stats (duration, distance, avg HR/power, HR drift)
- Computes power target compliance (% time below/in/above target band)
- Calculates HR zone distribution using 5-zone model
- Returns a summary dict; caller serialises to JSON and stores in `runs.parsed_data`

Main public API: `build_blocks_from_fit(fit_path, tz_name)` returns a summary dict.

### AI Analysis (`analyzer.py`)
Sends training context + workout data to the configured LLM with:
- System prompt including athlete profile loaded from the `users` table in the database
- `workout_yaml_schema.json` for structured data format
- Special handling for manual uploads (no power data penalty)

Reads `parsed_data` JSON from the run dict, reconstructs a YAML string for the LLM prompt (format unchanged), and stores the returned commentary in `runs.commentary`. No `.md` file is written. The active provider is resolved by `config.llm_provider` (OpenAI → Claude → Ollama, in priority order based on which keys are set).

### Stryd Integration (`runcoach/stryd_api.py`)
Inlined API client for authentication and activity retrieval:
- `authenticate()`: email/password login, stores session token and user ID
- `get_activities()`: fetch recent activities from the calendar endpoint
- `get_planned_workouts()`: fetch training plan workouts from `api.stryd.com` (returns full block structure including power targets)
- `download_fit_file()`: download FIT file for a specific activity

### Strava Integration (`runcoach/strava.py`)
Optional integration for route maps and webhook-triggered sync:
- **OAuth 2.0 flow**: Connect via Athlete Profile page (`/athlete-profile`)
- **Tokens stored**: `strava_access_token`, `strava_refresh_token`, `strava_token_expires_at` in `users` table; auto-refreshed when expired
- **Webhook auto-registration**: After OAuth connect, `register_webhook()` is called automatically — Strava's push subscription is registered as part of the callback; the subscription ID is stored in `users.strava_webhook_subscription_id`
- **Webhook**: `POST /strava/webhook` receives activity events from Strava, triggers Stryd sync pipeline, fetches route polyline
- **Webhook verification**: `GET /strava/webhook` handles Strava hub challenge using `STRAVA_WEBHOOK_VERIFY_TOKEN`
- **Route maps**: Strava `summary_polyline` decoded server-side and rendered with Leaflet.js on Run Detail page
- **Activity links**: `strava_activity_id` stored in `runs` table links to `https://www.strava.com/activities/{id}`

#### Setting up Strava
1. Create an app at `https://www.strava.com/settings/api` — set the Authorization Callback Domain to your server's domain
2. Set `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_WEBHOOK_VERIFY_TOKEN` in `.env`
3. Connect your Strava account via the Athlete Profile page in the web UI — this runs the OAuth flow **and** automatically registers the webhook subscription in one step
4. The Athlete Profile page will confirm the webhook subscription ID once registered

## Key Configuration

All config via environment variables (see `config.py`):
- `STRYD_EMAIL` / `STRYD_PASSWORD`: Stryd API credentials
- `OPENAI_API_KEY` / `OPENAI_MODEL`: OpenAI LLM (default model: `gpt-4o`)
- `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL`: Claude LLM (default model: `claude-opus-4-6`)
- `OLLAMA_BASE_URL` / `OLLAMA_MODEL` / `OLLAMA_NUM_CTX`: Ollama LLM (default model: `llama3.2`)
- Only one LLM provider needs to be configured; OpenAI takes priority if multiple are set
- `LLM_AUTO_ANALYSE`: Auto-analyze after sync (default: true)
- `ANALYZE_FROM`: Only auto-analyze runs on/after this date (YYYY-MM-DD)
- `DATA_DIR`: Root for activities, database, outputs (default: `data/`)
- `SYNC_INTERVAL_HOURS`: Background sync interval in hours; `0` disables periodic sync (default: 0)
- `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET`: Strava OAuth app credentials (optional)
- `STRAVA_WEBHOOK_VERIFY_TOKEN`: Random token for Strava webhook verification (optional)

### Directory Structure
```
data/
  activities/
    YYYY/
      MM/
        YYYYMMDD_activity_name/
          YYYYMMDD_activity_name.fit    # Original FIT file
          YYYYMMDD_activity_name.yaml   # Legacy — pre-migration runs only; not written for new runs
          YYYYMMDD_activity_name.md     # Legacy — pre-migration runs only; not written for new runs
  runcoach.db                           # SQLite database (runs, planned_workouts, etc.)
```

Parsed block data and AI commentary are now stored in the `runs` table (`parsed_data` and `commentary` columns). `.yaml` and `.md` files are kept on disk for historical reference but are no longer written or read by the application (except as a fallback for pre-migration runs that lack `parsed_data`).

## Important Patterns

### Manual Upload vs Stryd Sync
Manual uploads (drag-and-drop FIT files in web UI):
- Have `is_manual_upload=1` in database
- Have `stryd_activity_id=NULL`
- AI analysis skips power data criticism (many manual uploads lack Stryd power)
- Detection is via `run["is_manual_upload"]` DB column — not YAML content

### Prescribed Workout Comparison
When a Stryd training plan workout is prescribed for a date:
- `context.py` includes it in `prescribed_workout` field
- AI coach compares actual execution to prescription
- Flags meaningful deviations in power zones, duration, distance

## Subagent-Driven Development Notes

When executing implementation plans via `superpowers:subagent-driven-development`, apply these lessons:

**Review scope:** Skip the full two-stage (spec + quality) review for pure config/boilerplate tasks — adding a dataclass field, editing a YAML file, appending two method stubs. A quick self-review by the implementer is enough. Reserve the full review cycle for tasks with real logic (DB queries, API endpoints, async flows, new service classes).

**Run targeted tests during implementation, not the full suite.** Each subagent should run only the relevant test file (e.g. `pytest tests/test_db.py`) after implementing, leaving `pytest && pytest -m e2e --no-cov -v` for the final pre-merge verification step. The full Python suite takes ~2.5 minutes and running it after every task wastes ~15 minutes across a 6-task feature.

**Spec compliance and code quality reviews are independent — run them in parallel**, not sequentially. Both just read the same committed files.

**Batch independent tasks.** Identify tasks with no shared state early and dispatch them together (e.g. three independent new Flutter files can all be dispatched in one message).

**Check `VIRTUAL_ENV` at the very start of a session** and warn the user immediately if it's absent — before dispatching any subagents. A missing venv discovered mid-feature causes interruptions and confused subagents.

## Development Notes

- Python 3.11+ required
- Flask serves both HTML UI and JSON API endpoints
- PWA manifest + service worker in `runcoach/web/static/`
- Chart.js for HR zone visualization
- Database migrations handled inline in `db.py._init_schema()`
- Background scheduler runs in separate thread (`scheduler.py`)
- All timestamps stored as ISO 8601 strings in UTC
- Always create appropriate tests for any significant change to functionality, or for any new behaviour

## Athlete Profile

The athlete profile is stored in the `athlete_profile` column of the `users` table in the database. It is managed via the **Athlete Profile** page in the web UI (`/athlete-profile`) or via the mobile API (`GET/PUT /api/v1/athlete/profile`).

The profile text is injected into the OpenAI system prompt for every analysis. Include:
- Race goals and dates
- Training approach (e.g., Stryd power-based)
- Body weight (for Stryd power calculations)
- Any context the AI coach should consider

On first startup, the profile is automatically seeded from `coach_profile.txt` if it exists.
