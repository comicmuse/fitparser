from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stryd_activity_id INTEGER UNIQUE NOT NULL,
    name TEXT,
    date TEXT NOT NULL,
    distance_m REAL,
    moving_time_s INTEGER,
    fit_path TEXT,
    yaml_path TEXT,
    md_path TEXT,
    stage TEXT NOT NULL DEFAULT 'synced',
    error_message TEXT,
    avg_power_w REAL,
    avg_hr INTEGER,
    workout_name TEXT,
    commentary TEXT,
    analyzed_at TEXT,
    model_used TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    synced_at TEXT NOT NULL,
    parsed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    activities_found INTEGER,
    activities_new INTEGER,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(date);
CREATE INDEX IF NOT EXISTS idx_runs_stage ON runs(stage);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunCoachDB:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    # ------ runs ------

    def get_all_runs(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY date DESC, id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_run_by_stryd_id(self, stryd_activity_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE stryd_activity_id = ?",
                (stryd_activity_id,),
            ).fetchone()
        return dict(row) if row else None

    def insert_run(
        self,
        stryd_activity_id: int,
        name: str,
        date: str,
        fit_path: str,
        distance_m: float | None = None,
        moving_time_s: int | None = None,
    ) -> int:
        now = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO runs
                   (stryd_activity_id, name, date, fit_path,
                    distance_m, moving_time_s, stage, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'synced', ?)""",
                (stryd_activity_id, name, date, fit_path,
                 distance_m, moving_time_s, now),
            )
            return cur.lastrowid

    def update_parsed(
        self,
        run_id: int,
        yaml_path: str,
        avg_power_w: float | None,
        avg_hr: int | None,
        workout_name: str | None,
    ) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """UPDATE runs
                   SET stage='parsed', yaml_path=?, avg_power_w=?,
                       avg_hr=?, workout_name=?, parsed_at=?, updated_at=?
                   WHERE id=?""",
                (yaml_path, avg_power_w, avg_hr, workout_name, now, now, run_id),
            )

    def update_analyzed(
        self,
        run_id: int,
        md_path: str,
        commentary: str,
        model_used: str,
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

    def update_error(self, run_id: int, error_message: str) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """UPDATE runs
                   SET stage='error', error_message=?, updated_at=?
                   WHERE id=?""",
                (error_message, now, run_id),
            )

    def get_pending_runs(self, stage: str, date_from: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if date_from:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE stage = ? AND date >= ? ORDER BY date ASC",
                    (stage, date_from),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE stage = ? ORDER BY date ASC",
                    (stage,),
                ).fetchall()
        return [dict(r) for r in rows]

    def reset_errors_to_synced(self) -> int:
        """Reset all error runs back to synced so they can be re-processed."""
        now = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE runs
                   SET stage='synced', error_message=NULL, updated_at=?
                   WHERE stage='error'""",
                (now,),
            )
            return cur.rowcount

    # ------ sync_log ------

    def start_sync_log(self) -> int:
        now = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO sync_log (started_at, status) VALUES (?, 'running')",
                (now,),
            )
            return cur.lastrowid

    def finish_sync_log(
        self,
        log_id: int,
        status: str,
        activities_found: int = 0,
        activities_new: int = 0,
        error_message: str | None = None,
    ) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """UPDATE sync_log
                   SET finished_at=?, status=?,
                       activities_found=?, activities_new=?,
                       error_message=?
                   WHERE id=?""",
                (now, status, activities_found, activities_new,
                 error_message, log_id),
            )

    def get_last_sync(self) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def get_sync_stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            pending_parse = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE stage='synced'"
            ).fetchone()[0]
            pending_analyze = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE stage='parsed'"
            ).fetchone()[0]
            errors = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE stage='error'"
            ).fetchone()[0]
        return {
            "total_runs": total,
            "pending_parse": pending_parse,
            "pending_analyze": pending_analyze,
            "errors": errors,
        }
