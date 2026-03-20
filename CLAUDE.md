# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RunCoach is an automated running workout analysis system that syncs activities from Stryd, parses Garmin FIT files into structured YAML blocks, and generates AI coaching commentary using OpenAI. It's a Progressive Web App (PWA) with push notifications.

The system has three main stages:
1. **Sync** — authenticate with Stryd API, download new FIT files
2. **Parse** — convert FIT → structured YAML with block segmentation, power/HR/pace stats, HR zone distribution
3. **Analyze** — send YAML + 7-day training context (ATL/CTL/RSB) to OpenAI, store markdown commentary

## Development Commands

### Local Setup

**IMPORTANT:** This project uses a `.venv` virtual environment. **NEVER** install packages or run commands using the global Python installation. Always activate the virtual environment first.

```bash
# Create virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Copy and configure environment
cp .env.example .env
# Edit .env with Stryd credentials, OpenAI API key, etc.
```

**All commands below assume you have activated the virtual environment with `source .venv/bin/activate`**

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

### Testing Individual Components
```bash
# Test Stryd authentication and sync (from strydcmd-src)
cd strydcmd-src
source .venv/bin/activate
stryd -g 7  # Get activities from last 7 days
stryd -g 30 -f  # Download FIT files for last 30 days
strydsync 30  # Sync to SQLite database

# Parse a single FIT file to YAML
runcoach-cli parse --file path/to/file.fit

# Parse all FIT files in a directory
runcoach-cli parse --directory path/to/dir/

# Analyze a single YAML file
runcoach-cli analyze --file path/to/file.yaml

# Analyze all YAML files in a directory
runcoach-cli analyze --directory path/to/dir/
```

### Running Tests

The project includes comprehensive unit tests with pytest. Always run tests before committing changes.

```bash
# Install test dependencies (first time only)
source .venv/bin/activate
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
- `tests/test_context.py` - Training context and RSS calculations (92% coverage)
- `tests/test_db.py` - Database CRUD operations (96% coverage)
- `tests/test_analyzer.py` - AI analysis with mocked OpenAI (96% coverage)
- `tests/test_fit_parser.py` - FIT file parsing (83% coverage)
- `tests/test_web.py` - Flask web UI routes and pages (49% coverage)
- `tests/conftest.py` - Shared fixtures (temp databases, mock clients, sample files)

**Current Coverage:** 69% overall (109 tests passing)

**Testing Best Practices:**
- External APIs (OpenAI, Stryd) are mocked to avoid costs and rate limits
- Tests use temporary databases and directories (`tmp_path` fixture)
- Real FIT/YAML files from `data/activities/` are used for integration tests
- All timestamps use ISO 8601 format like production code

## Architecture

### Core Pipeline (`runcoach/pipeline.py`)
The `run_full_pipeline()` function orchestrates all three stages sequentially. It's executed:
- Automatically on a configurable schedule (via `scheduler.py`)
- Manually via the "Sync Now" button in the web UI
- Via CLI with `runcoach-pipeline`

Uses a threading lock to prevent concurrent pipeline runs.

### Data Flow
1. **Sync** (`sync.py`) → Downloads FIT files from Stryd, stores metadata in SQLite with stage='synced'
2. **Parse** (`parser.py`) → Calls `fit_parser.py` to segment FIT into workout blocks (warmup/work/rest/cooldown), writes YAML, updates DB to stage='parsed'
3. **Analyze** (`analyzer.py`) → Builds weekly training context via `context.py`, sends to OpenAI with athlete profile + schema, writes markdown commentary, updates DB to stage='analyzed'

### Database Schema (`db.py`)
- **runs** table: tracks activity progression through pipeline stages (synced → parsed → analyzed → error)
  - `stryd_activity_id`: links to Stryd API (nullable for manual uploads)
  - `stage`: current pipeline stage
  - `is_manual_upload`: distinguishes manual FIT uploads from Stryd sync
- **planned_workouts** table: stores prescribed workouts from Stryd training calendar
- **push_subscriptions** table: Web Push endpoints for notifications
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
Core module for converting Garmin FIT files to structured YAML:
- Extracts workout steps and laps from FIT files
- Maps steps to laps by index
- Calculates per-block stats (duration, distance, avg HR/power, HR drift)
- Computes power target compliance (% time below/in/above target band)
- Calculates HR zone distribution using 5-zone model
- Outputs structured YAML with all block data

Main public API: `build_blocks_from_fit(fit_path, tz_name)` returns a summary dict.

### AI Analysis (`analyzer.py`)
Sends training context + workout YAML to OpenAI with:
- System prompt including athlete profile loaded from the `users` table in the database
- `workout_yaml_schema.json` for structured data format
- Special handling for manual uploads (no power data penalty)

Returns markdown commentary stored in DB and written to `.md` file.

### Stryd Integration (`strydcmd-src/`)
Bundled subproject with its own package:
- `stryd_api.py`: Stryd API client for authentication and activity retrieval
- `database.py`: Separate SQLite database for detailed Stryd data (87 fields, time-series)
- `strydsync` command: batch sync with progress tracking

## Key Configuration

All config via environment variables (see `config.py`):
- `STRYD_EMAIL` / `STRYD_PASSWORD`: Stryd API credentials
- `OPENAI_API_KEY` / `OPENAI_MODEL`: OpenAI configuration
- `OPENAI_AUTO_ANALYSE`: Auto-analyze after sync (default: true)
- `ANALYZE_FROM`: Only auto-analyze runs on/after this date (YYYY-MM-DD)
- `DATA_DIR`: Root for activities, database, outputs (default: `data/`)
- `SYNC_INTERVAL_HOURS`: Background sync interval (default: 6)

### Directory Structure
```
data/
  activities/
    YYYY/
      MM/
        YYYYMMDD_activity_name/
          YYYYMMDD_activity_name.fit    # Original FIT file
          YYYYMMDD_activity_name.yaml   # Parsed workout blocks
          YYYYMMDD_activity_name.md     # AI commentary
  runcoach.db                           # SQLite database (runs, planned_workouts, etc.)
```

## Important Patterns

### Manual Upload vs Stryd Sync
Manual uploads (drag-and-drop FIT files in web UI):
- Have `is_manual_upload=1` in database
- Have `stryd_activity_id=NULL`
- Include `manual_upload: true` in YAML
- AI analysis skips power data criticism (many manual uploads lack Stryd power)

### Prescribed Workout Comparison
When a Stryd training plan workout is prescribed for a date:
- `context.py` includes it in `prescribed_workout` field
- AI coach compares actual execution to prescription
- Flags meaningful deviations in power zones, duration, distance

### Push Notifications
Uses Web Push (VAPID) for analysis completion alerts:
- Self-generated keypairs (no third-party service)
- Keys stored as base64url in environment
- `push.py` sends notifications to all subscribed endpoints

## Development Notes

- **Virtual Environment:** This project uses `.venv` - always activate with `source .venv/bin/activate` before running any commands
- Python 3.11+ required
- Flask serves both HTML UI and JSON API endpoints
- PWA manifest + service worker in `runcoach/web/static/`
- Chart.js for HR zone visualization
- Database migrations handled inline in `db.py._init_schema()`
- Background scheduler runs in separate thread (`scheduler.py`)
- All timestamps stored as ISO 8601 strings in UTC

## Athlete Profile

The athlete profile is stored in the `athlete_profile` column of the `users` table in the database. It is managed via the **Athlete Profile** page in the web UI (`/athlete-profile`) or via the mobile API (`GET/PUT /api/v1/athlete/profile`).

The profile text is injected into the OpenAI system prompt for every analysis. Include:
- Race goals and dates
- Training approach (e.g., Stryd power-based)
- Body weight (for Stryd power calculations)
- Any context the AI coach should consider

On first startup, the profile is automatically seeded from `coach_profile.txt` if it exists.
