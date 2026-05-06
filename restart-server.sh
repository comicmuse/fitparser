#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Kill whatever is currently on the port (default 5001, respects FLASK_PORT)
PORT="${FLASK_PORT:-5001}"
EXISTING=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
    echo "Stopping existing server on port $PORT (PID $EXISTING)..."
    kill "$EXISTING"
    sleep 2
fi

source "$SCRIPT_DIR/.venv/bin/activate"
cd "$SCRIPT_DIR"
python -m runcoach.web >/tmp/runcoach-dev.out 2>/tmp/runcoach-dev.err &
echo "Server started on port $PORT (PID $!)"
