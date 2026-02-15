# RunCoach

Automated running workout analysis — syncs activities from [Stryd](https://www.stryd.com/), parses Garmin FIT files into structured YAML blocks, and generates AI coaching commentary using OpenAI.

Installable as a **Progressive Web App (PWA)** on Android (or any browser) with push notifications when new analyses are ready.

## Features

- **Stryd sync** — automatically fetches new activities on a configurable schedule
- **FIT parsing** — breaks workouts into blocks (warmup / work / rest / cooldown) with per-block power, HR, pace, and HR zone distribution
- **AI analysis** — sends structured workout data + weekly training context (ATL/CTL/RSB) to OpenAI for coaching commentary
- **Web dashboard** — dark-themed Flask UI with activity log, block timeline visualisation, HR zone charts, and rendered markdown commentary
- **PWA** — installable on Android home screen, works offline for cached pages
- **Push notifications** — Web Push (VAPID) alerts when a new analysis completes
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
| `OPENAI_API_KEY` | — | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | Model to use for analysis |
| `OPENAI_AUTO_ANALYSE` | `true` | Auto-analyze after sync (`false` = on-demand only) |
| `ANALYZE_FROM` | — | Only auto-analyze runs on/after this date (YYYY-MM-DD) |
| `DATA_DIR` | `data` | Root directory for activities, database, and outputs |
| `SYNC_INTERVAL_HOURS` | `6` | Background sync interval |
| `SYNC_LOOKBACK_DAYS` | `30` | How far back to check for new activities |
| `TIMEZONE` | `Europe/London` | Timezone for FIT timestamp parsing |
| `FLASK_PORT` | `5000` | Web server port |
| `FLASK_DEBUG` | `false` | Flask debug mode |
| `VAPID_PRIVATE_KEY` | — | VAPID private key for push notifications |
| `VAPID_PUBLIC_KEY` | — | VAPID public key for push notifications |
| `VAPID_EMAIL` | — | Contact email embedded in push messages |

## Push Notifications (VAPID Setup)

Generate keys (one-time):

```bash
source .venv/bin/activate
vapid --gen
# Then extract base64url keys:
python3 -c "
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import base64
with open('private_key.pem', 'rb') as f:
    pk = serialization.load_pem_private_key(f.read(), password=None)
priv = base64.urlsafe_b64encode(pk.private_numbers().private_value.to_bytes(32, 'big')).decode().rstrip('=')
pub = base64.urlsafe_b64encode(pk.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).decode().rstrip('=')
print(f'VAPID_PRIVATE_KEY={priv}')
print(f'VAPID_PUBLIC_KEY={pub}')
"
```

Add the output to your `.env`, then delete the PEM files.

No sign-up or third-party service required — VAPID keys are self-generated cryptographic keypairs.

## Pipeline

The pipeline runs three stages sequentially:

1. **Sync** — authenticate with Stryd API, download new FIT files
2. **Parse** — convert FIT → structured YAML with block segmentation, power/HR/pace stats, HR zone distribution, and power target compliance
3. **Analyze** — send YAML + 7-day training context to OpenAI, store markdown commentary

Runs automatically on the configured schedule, or trigger manually via the **Sync Now** button or CLI:

```bash
runcoach-pipeline
```

## Project Structure

```
runcoach/
  __init__.py
  analyzer.py      # OpenAI analysis with training context
  config.py         # Environment-based configuration
  context.py        # Weekly training load context (ATL/CTL/RSB)
  db.py             # SQLite database (WAL mode)
  parser.py         # FIT → YAML block parser
  pipeline.py       # Sync → Parse → Analyze pipeline
  push.py           # Web Push notification helper
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
- **OpenAI API** for coaching analysis
- **pywebpush** / **py-vapid** for Web Push notifications
- **Chart.js** for HR zone visualisation
- **Docker** for deployment
