# RunCoach

[![CI/CD](https://github.com/comicmuse/fitparser/actions/workflows/ci.yml/badge.svg)](https://github.com/comicmuse/fitparser/actions/workflows/ci.yml)

Automated running workout analysis — syncs activities from [Stryd](https://www.stryd.com/), parses Garmin FIT files into structured workout blocks, and generates AI coaching commentary using a configurable LLM (OpenAI, Claude, or Ollama).

Installable as a **Progressive Web App (PWA)** on Android (or any browser).

## Features

- **Stryd sync** — automatically fetches new activities on a configurable schedule
- **FIT parsing** — breaks workouts into blocks (warmup / work / rest / cooldown) with per-block power, HR, pace, and HR zone distribution
- **AI analysis** — sends structured workout data + weekly training context (ATL/CTL/RSB) to a configurable LLM (OpenAI, Claude, or Ollama) for coaching commentary
- **Web dashboard** — dark-themed Flask UI with activity log, block timeline visualisation, HR zone charts, and rendered markdown commentary
- **PWA** — installable on Android home screen, works offline for cached pages
- **Manual upload** — drag-and-drop FIT files for runs without Stryd sync
- **Docker** — single-container deployment

## Quickstart

### Local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # fill in credentials
python -m runcoach.web
```

Open http://localhost:5000

### Docker

```bash
docker compose up -d
```

## Configuration

All config is via environment variables (or `.env` file):

| Variable | Default | Description |
|---|---|---|
| `STRYD_EMAIL` | — | Stryd account email |
| `STRYD_PASSWORD` | — | Stryd account password |
| `OPENAI_API_KEY` | — | OpenAI API key (takes priority if multiple LLMs configured) |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model to use |
| `ANTHROPIC_API_KEY` | — | Anthropic API key (Claude) |
| `ANTHROPIC_MODEL` | `claude-opus-4-6` | Anthropic model to use |
| `OLLAMA_BASE_URL` | — | Ollama base URL (e.g. `http://localhost:11434`) |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model to use |
| `LLM_AUTO_ANALYSE` | `true` | Auto-analyze after sync (`false` = on-demand only) |
| `ANALYZE_FROM` | — | Only auto-analyze runs on/after this date (YYYY-MM-DD) |
| `DATA_DIR` | `data` | Root directory for activities, database, and outputs |
| `SYNC_INTERVAL_HOURS` | `0` | Background sync interval in hours; `0` disables periodic sync |
| `SYNC_LOOKBACK_DAYS` | `30` | How far back to check for new activities |
| `TIMEZONE` | `Europe/London` | Timezone for FIT timestamp parsing |
| `FLASK_PORT` | `5000` | Web server port |
| `FLASK_DEBUG` | `false` | Flask debug mode |

### Athlete Profile

The athlete profile is stored in the database and managed via the **Athlete Profile** page in the web UI (`/athlete-profile`). It is injected into the AI coaching prompt for every analysis — include your race goal, training approach, body weight for Stryd calculations, and any other context the coach should know.

## Pipeline

The pipeline runs three stages sequentially:

1. **Sync** — authenticate with Stryd API, download new FIT files
2. **Parse** — convert FIT → structured block data (power/HR/pace stats, HR zone distribution, power target compliance) stored as JSON in the database
3. **Analyze** — send workout data + 7-day training context to the configured LLM, store commentary in the database

Runs automatically on the configured schedule, or trigger manually via the **Sync Now** button or CLI:

```bash
runcoach-pipeline
```

## Project Structure

```
runcoach/
  __init__.py
  analyzer.py      # LLM analysis with training context
  config.py         # Environment-based configuration
  context.py        # Weekly training load context (ATL/CTL/RSB)
  db.py             # SQLite database (WAL mode)
  parser.py         # FIT → block data parser
  pipeline.py       # Sync → Parse → Analyze pipeline
  scheduler.py      # Background scheduler thread
  sync.py           # Stryd API sync
  web/
    __init__.py     # Flask app factory
    routes.py       # Web routes + API endpoints
    static/         # PWA assets (manifest, service worker, icons)
    templates/      # Jinja2 templates
```

## Tech Stack

- **Python 3.11+**, Flask, SQLite (WAL)
- **fitparse** for Garmin FIT decoding
- **OpenAI / Anthropic / Ollama** for coaching analysis (configurable)
- **Chart.js** for HR zone visualisation
- **Docker** for deployment

## Acknowledgements

- **[Stryd API](https://www.stryd.com)** — activity sync and training plan calendar, via `runcoach/stryd_api.py`
