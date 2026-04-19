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
    stryd_activity_id INTEGER UNIQUE,
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
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_manual_upload INTEGER NOT NULL DEFAULT 0,
    stryd_rss REAL
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

CREATE TABLE IF NOT EXISTS planned_workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    title TEXT,
    description TEXT,
    workout_type TEXT,
    duration_s REAL,
    distance_m REAL,
    stress REAL,
    intensity_zones TEXT,
    activity_id TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_planned_date_title
    ON planned_workouts(date, title);
CREATE INDEX IF NOT EXISTS idx_planned_date ON planned_workouts(date);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login TEXT,
    athlete_profile TEXT
);

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
            # Migration: add is_manual_upload column if it doesn't exist
            cursor = conn.execute("PRAGMA table_info(runs)")
            columns = {row[1]: row for row in cursor.fetchall()}
            if "is_manual_upload" not in columns:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN is_manual_upload INTEGER NOT NULL DEFAULT 0"
                )
            # Migration: add stryd_rss column if it doesn't exist
            if "stryd_rss" not in columns:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN stryd_rss REAL"
                )
            # Migration: add garmin_connect_id and strava_activity_id columns
            if "garmin_connect_id" not in columns:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN garmin_connect_id TEXT"
                )
            if "strava_activity_id" not in columns:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN strava_activity_id TEXT"
                )
            if "strava_map_polyline" not in columns:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN strava_map_polyline TEXT"
                )

            # Migration: allow NULL stryd_activity_id for manual uploads
            # Check if stryd_activity_id has NOT NULL constraint (column index 3 is notnull flag)
            if "stryd_activity_id" in columns and columns["stryd_activity_id"][3] == 1:
                # Need to recreate the table to remove NOT NULL constraint
                log.info("Migrating runs table to allow NULL stryd_activity_id")
                conn.executescript("""
                    PRAGMA foreign_keys=OFF;

                    CREATE TABLE IF NOT EXISTS runs_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        stryd_activity_id INTEGER UNIQUE,
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
                        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                        is_manual_upload INTEGER NOT NULL DEFAULT 0,
                        stryd_rss REAL
                    );

                    INSERT INTO runs_new SELECT
                        id, stryd_activity_id, name, date, distance_m, moving_time_s,
                        fit_path, yaml_path, md_path, stage, error_message,
                        avg_power_w, avg_hr, workout_name, commentary, analyzed_at,
                        model_used, prompt_tokens, completion_tokens, synced_at,
                        parsed_at, created_at, updated_at,
                        COALESCE(is_manual_upload, 0),
                        NULL
                    FROM runs;

                    DROP TABLE runs;
                    ALTER TABLE runs_new RENAME TO runs;

                    CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(date);
                    CREATE INDEX IF NOT EXISTS idx_runs_stage ON runs(stage);

                    PRAGMA foreign_keys=ON;
                """)

            # Migration: add athlete_profile, stryd_athlete_id, and Strava columns to users
            cursor = conn.execute("PRAGMA table_info(users)")
            user_columns = {row[1] for row in cursor.fetchall()}
            if "stryd_athlete_id" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN stryd_athlete_id TEXT")
            for col, col_type in [
                ("strava_access_token", "TEXT"),
                ("strava_refresh_token", "TEXT"),
                ("strava_token_expires_at", "INTEGER"),
                ("strava_athlete_id", "TEXT"),
                ("strava_webhook_subscription_id", "INTEGER"),
            ]:
                if col not in user_columns:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            if "display_name" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
            if "race_date" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN race_date TEXT")
            if "race_distance" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN race_distance TEXT")
            if "athlete_profile" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN athlete_profile TEXT")
                # Seed from coach_profile.txt if the default user exists and profile is null
                seed_path = Path(__file__).resolve().parent.parent / "coach_profile.txt"
                if seed_path.exists():
                    try:
                        seed_text = seed_path.read_text(encoding="utf-8").strip()
                        conn.execute(
                            """UPDATE users SET athlete_profile = ?
                               WHERE athlete_profile IS NULL AND id = (SELECT MIN(id) FROM users)""",
                            (seed_text,),
                        )
                        log.info("Seeded athlete_profile from coach_profile.txt")
                    except Exception:
                        log.exception("Failed to seed athlete_profile from coach_profile.txt")

            # Migration: add Stryd credentials to users
            cursor = conn.execute("PRAGMA table_info(users)")
            user_columns = {row[1] for row in cursor.fetchall()}
            if "stryd_email" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN stryd_email TEXT")
            if "stryd_password" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN stryd_password TEXT")

            # Migration: add is_active and is_admin to users
            cursor = conn.execute("PRAGMA table_info(users)")
            user_columns = {row[1] for row in cursor.fetchall()}
            if "is_active" not in user_columns:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
                )
            if "is_admin" not in user_columns:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
                )
                # First user (lowest id) is admin by default
                conn.execute(
                    "UPDATE users SET is_admin = 1 WHERE id = (SELECT MIN(id) FROM users)"
                )

            # Migration: add user_id to runs
            cursor = conn.execute("PRAGMA table_info(runs)")
            run_cols = {row[1] for row in cursor.fetchall()}
            if "user_id" not in run_cols:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_runs_user_id ON runs(user_id)"
                )

            # Migration: add user_id to planned_workouts and fix unique index
            cursor = conn.execute("PRAGMA table_info(planned_workouts)")
            pw_cols = {row[1] for row in cursor.fetchall()}
            if "user_id" not in pw_cols:
                conn.execute(
                    "ALTER TABLE planned_workouts ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1"
                )
                # Replace old (date, title) unique index with (date, title, user_id)
                conn.execute("DROP INDEX IF EXISTS idx_planned_date_title")
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_planned_date_title"
                    " ON planned_workouts(date, title, user_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_planned_workouts_user_id"
                    " ON planned_workouts(user_id)"
                )

            # Migration: add user_id to sync_log
            cursor = conn.execute("PRAGMA table_info(sync_log)")
            sl_cols = {row[1] for row in cursor.fetchall()}
            if "user_id" not in sl_cols:
                conn.execute(
                    "ALTER TABLE sync_log ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1"
                )

    # ------ runs ------

    def get_all_runs(self, user_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE user_id = ? ORDER BY date DESC, id DESC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: int, user_id: int | None = None) -> Optional[dict]:
        with self._connect() as conn:
            if user_id is not None:
                row = conn.execute(
                    "SELECT * FROM runs WHERE id = ? AND user_id = ?",
                    (run_id, user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM runs WHERE id = ?", (run_id,)
                ).fetchone()
        return dict(row) if row else None

    def get_run_by_stryd_id(
        self, stryd_activity_id: int, user_id: int | None = None
    ) -> Optional[dict]:
        with self._connect() as conn:
            if user_id is not None:
                row = conn.execute(
                    "SELECT * FROM runs WHERE stryd_activity_id = ? AND user_id = ?",
                    (stryd_activity_id, user_id),
                ).fetchone()
            else:
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
        user_id: int = 1,
        distance_m: float | None = None,
        moving_time_s: int | None = None,
        stryd_rss: float | None = None,
    ) -> int:
        now = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO runs
                   (stryd_activity_id, name, date, fit_path,
                    distance_m, moving_time_s, stage, synced_at, stryd_rss, user_id)
                   VALUES (?, ?, ?, ?, ?, ?, 'synced', ?, ?, ?)""",
                (stryd_activity_id, name, date, fit_path,
                 distance_m, moving_time_s, now, stryd_rss, user_id),
            )
            return cur.lastrowid

    def insert_manual_run(
        self,
        name: str,
        date: str,
        fit_path: str,
        distance_m: float | None = None,
        moving_time_s: int | None = None,
        user_id: int = 1,
    ) -> int:
        """Insert a manually uploaded run (no Stryd activity ID)."""
        now = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO runs
                   (stryd_activity_id, name, date, fit_path,
                    distance_m, moving_time_s, stage, synced_at, is_manual_upload, user_id)
                   VALUES (NULL, ?, ?, ?, ?, ?, 'synced', ?, 1, ?)""",
                (name, date, fit_path, distance_m, moving_time_s, now, user_id),
            )
            return cur.lastrowid

    def get_run_by_fit_path(
        self, fit_path: str, user_id: int | None = None
    ) -> Optional[dict]:
        """Get a run by its FIT file path."""
        with self._connect() as conn:
            if user_id is not None:
                row = conn.execute(
                    "SELECT * FROM runs WHERE fit_path = ? AND user_id = ?",
                    (fit_path, user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM runs WHERE fit_path = ?", (fit_path,)
                ).fetchone()
        return dict(row) if row else None

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

    def get_pending_runs(
        self, stage: str, user_id: int | None = None, date_from: str | None = None
    ) -> list[dict]:
        with self._connect() as conn:
            if user_id is not None and date_from:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE stage = ? AND user_id = ? AND date >= ? ORDER BY date ASC",
                    (stage, user_id, date_from),
                ).fetchall()
            elif user_id is not None:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE stage = ? AND user_id = ? ORDER BY date ASC",
                    (stage, user_id),
                ).fetchall()
            elif date_from:
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

    def start_sync_log(self, user_id: int = 1) -> int:
        now = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO sync_log (started_at, status, user_id) VALUES (?, 'running', ?)",
                (now, user_id),
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

    def get_last_sync(self, user_id: int | None = None) -> Optional[dict]:
        with self._connect() as conn:
            if user_id is not None:
                row = conn.execute(
                    "SELECT * FROM sync_log WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                    (user_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
                ).fetchone()
        return dict(row) if row else None

    def get_sync_stats(self, user_id: int | None = None) -> dict:
        with self._connect() as conn:
            if user_id is not None:
                total = conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE user_id = ?", (user_id,)
                ).fetchone()[0]
                pending_parse = conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE stage='synced' AND user_id = ?", (user_id,)
                ).fetchone()[0]
                pending_analyze = conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE stage='parsed' AND user_id = ?", (user_id,)
                ).fetchone()[0]
                errors = conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE stage='error' AND user_id = ?", (user_id,)
                ).fetchone()[0]
            else:
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

    # ------ planned_workouts ------

    def upsert_planned_workout(
        self,
        date: str,
        title: str,
        user_id: int = 1,
        description: str | None = None,
        workout_type: str | None = None,
        duration_s: float | None = None,
        distance_m: float | None = None,
        stress: float | None = None,
        intensity_zones: str | None = None,
        activity_id: str | None = None,
        raw_json: str | None = None,
    ) -> int:
        """Insert or update a planned workout (keyed on date + title + user_id)."""
        now = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO planned_workouts
                   (date, title, user_id, description, workout_type, duration_s,
                    distance_m, stress, intensity_zones, activity_id,
                    raw_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(date, title, user_id) DO UPDATE SET
                     description = excluded.description,
                     workout_type = excluded.workout_type,
                     duration_s = excluded.duration_s,
                     distance_m = excluded.distance_m,
                     stress = excluded.stress,
                     intensity_zones = excluded.intensity_zones,
                     activity_id = excluded.activity_id,
                     raw_json = excluded.raw_json,
                     updated_at = excluded.updated_at""",
                (date, title, user_id, description, workout_type, duration_s,
                 distance_m, stress, intensity_zones, activity_id,
                 raw_json, now, now),
            )
            return cur.lastrowid

    def delete_planned_workout(
        self, date: str, title: str, user_id: int | None = None
    ) -> bool:
        """Delete a planned workout by date and title. Returns True if deleted."""
        with self._connect() as conn:
            if user_id is not None:
                cur = conn.execute(
                    "DELETE FROM planned_workouts WHERE date = ? AND title = ? AND user_id = ?",
                    (date, title, user_id),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM planned_workouts WHERE date = ? AND title = ?",
                    (date, title),
                )
            return cur.rowcount > 0

    def get_planned_workout_for_date(
        self, date: str, user_id: int | None = None
    ) -> list[dict]:
        """Get all planned workouts for a given date."""
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    "SELECT * FROM planned_workouts WHERE date = ? AND user_id = ? ORDER BY id",
                    (date, user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM planned_workouts WHERE date = ? ORDER BY id",
                    (date,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_upcoming_planned_workouts(
        self, from_date: str, limit: int = 14, user_id: int | None = None
    ) -> list[dict]:
        """Get upcoming planned workouts from a date onwards."""
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    """SELECT * FROM planned_workouts
                       WHERE date >= ? AND user_id = ?
                       ORDER BY date ASC
                       LIMIT ?""",
                    (from_date, user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM planned_workouts
                       WHERE date >= ?
                       ORDER BY date ASC
                       LIMIT ?""",
                    (from_date, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_all_planned_workouts(self, user_id: int | None = None) -> list[dict]:
        """Get all planned workouts ordered by date."""
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    "SELECT * FROM planned_workouts WHERE user_id = ? ORDER BY date ASC",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM planned_workouts ORDER BY date ASC"
                ).fetchall()
        return [dict(r) for r in rows]

    def get_planned_workouts_in_range(
        self, start_date: str, end_date: str, user_id: int | None = None
    ) -> list[dict]:
        """Get planned workouts within a date range [start, end)."""
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    """SELECT * FROM planned_workouts
                       WHERE date >= ? AND date < ? AND user_id = ?
                       ORDER BY date ASC""",
                    (start_date, end_date, user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM planned_workouts
                       WHERE date >= ? AND date < ?
                       ORDER BY date ASC""",
                    (start_date, end_date),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_past_planned_workouts(
        self,
        before_date: str,
        limit: int = 10,
        offset: int = 0,
        user_id: int | None = None,
    ) -> list[dict]:
        """Get past planned workouts (before a date), most recent first."""
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    """SELECT * FROM planned_workouts
                       WHERE date < ? AND user_id = ?
                       ORDER BY date DESC
                       LIMIT ? OFFSET ?""",
                    (before_date, user_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM planned_workouts
                       WHERE date < ?
                       ORDER BY date DESC
                       LIMIT ? OFFSET ?""",
                    (before_date, limit, offset),
                ).fetchall()
        return [dict(r) for r in rows]

    def count_past_planned_workouts(
        self, before_date: str, user_id: int | None = None
    ) -> int:
        with self._connect() as conn:
            if user_id is not None:
                return conn.execute(
                    "SELECT COUNT(*) FROM planned_workouts WHERE date < ? AND user_id = ?",
                    (before_date, user_id),
                ).fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM planned_workouts WHERE date < ?",
                (before_date,),
            ).fetchone()[0]

    def count_upcoming_planned_workouts(
        self, from_date: str, user_id: int | None = None
    ) -> int:
        with self._connect() as conn:
            if user_id is not None:
                return conn.execute(
                    "SELECT COUNT(*) FROM planned_workouts WHERE date >= ? AND user_id = ?",
                    (from_date, user_id),
                ).fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM planned_workouts WHERE date >= ?",
                (from_date,),
            ).fetchone()[0]

    def get_upcoming_planned_workouts_paged(
        self,
        from_date: str,
        limit: int = 10,
        offset: int = 0,
        user_id: int | None = None,
    ) -> list[dict]:
        """Get upcoming planned workouts with pagination."""
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    """SELECT * FROM planned_workouts
                       WHERE date >= ? AND user_id = ?
                       ORDER BY date ASC
                       LIMIT ? OFFSET ?""",
                    (from_date, user_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM planned_workouts
                       WHERE date >= ?
                       ORDER BY date ASC
                       LIMIT ? OFFSET ?""",
                    (from_date, limit, offset),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_runs_in_date_range(
        self, start_date: str, end_date: str, user_id: int | None = None
    ) -> list[dict]:
        """Get runs within a date range [start, end)."""
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    """SELECT * FROM runs
                       WHERE date >= ? AND date < ? AND user_id = ?
                       ORDER BY date ASC""",
                    (start_date, end_date, user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM runs
                       WHERE date >= ? AND date < ?
                       ORDER BY date ASC""",
                    (start_date, end_date),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_runs_paginated(
        self, limit: int = 10, offset: int = 0, user_id: int | None = None
    ) -> list[dict]:
        """Get all runs with pagination, most recent first."""
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
                    (user_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [dict(r) for r in rows]

    def count_runs(self, user_id: int | None = None) -> int:
        with self._connect() as conn:
            if user_id is not None:
                return conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE user_id = ?", (user_id,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    # ------ users ------

    def get_user_by_username(self, username: str) -> Optional[dict]:
        """Get a user by username."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        """Get a user by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_all_users(self) -> list[dict]:
        """Return all users ordered by id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY id ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def set_user_active(self, user_id: int, is_active: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, user_id),
            )

    def set_user_admin(self, user_id: int, is_admin: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (1 if is_admin else 0, user_id),
            )

    def delete_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM runs WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM planned_workouts WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM sync_log WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def create_user(self, username: str, password_hash: str) -> int:
        """Create a new user."""
        now = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, now),
            )
            return cur.lastrowid

    def update_last_login(self, user_id: int) -> None:
        """Update user's last login timestamp."""
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (now, user_id),
            )

    def ensure_default_user(self, username: str, password_hash: str) -> int:
        """
        Ensure default user exists, create if not.
        Returns the user ID.
        """
        user = self.get_user_by_username(username)
        if user:
            return user["id"]
        return self.create_user(username, password_hash)

    def get_athlete_profile(self, user_id: int) -> str:
        """Return the athlete profile text for a user (empty string if not set)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT athlete_profile FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        if row and row[0]:
            return row[0]
        return ""

    def get_stryd_athlete_id(self, user_id: int) -> str | None:
        """Return the Stryd athlete UUID for a user, or None if not set."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT stryd_athlete_id FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return row[0] if row and row[0] else None

    def update_stryd_athlete_id(self, user_id: int, stryd_athlete_id: str) -> None:
        """Update the Stryd athlete UUID for a user."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET stryd_athlete_id = ? WHERE id = ?",
                (stryd_athlete_id, user_id),
            )

    def update_athlete_profile(self, user_id: int, profile_text: str) -> None:
        """Update the athlete profile text for a user."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET athlete_profile = ? WHERE id = ?",
                (profile_text, user_id),
            )

    def get_race_goal(self, user_id: int) -> dict:
        """Return the race goal for a user as a dict with race_date and race_distance."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT race_date, race_distance FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        if row:
            return {"race_date": row[0] or None, "race_distance": row[1] or None}
        return {"race_date": None, "race_distance": None}

    def update_race_goal(
        self,
        user_id: int,
        race_date: str | None,
        race_distance: str | None,
    ) -> None:
        """Update the race date and distance for a user."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET race_date = ?, race_distance = ? WHERE id = ?",
                (race_date or None, race_distance or None, user_id),
            )

    def get_display_name(self, user_id: int) -> str:
        """Return the display name for a user (empty string if not set)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT display_name FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return row[0] if row and row[0] else ""

    def update_user_info(self, user_id: int, display_name: str, username: str) -> None:
        """Update the display name and login username for a user."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET display_name = ?, username = ? WHERE id = ?",
                (display_name, username, user_id),
            )

    def get_default_user_id(self) -> int | None:
        """Return the ID of the first (default) user, or None if no users exist."""
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
        return row[0] if row else None

    def get_stryd_credentials(self, user_id: int) -> dict:
        """Return Stryd credentials for a user as {stryd_email, stryd_password}."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT stryd_email, stryd_password FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row:
            return {"stryd_email": row[0] or "", "stryd_password": row[1] or ""}
        return {"stryd_email": "", "stryd_password": ""}

    def update_stryd_credentials(
        self, user_id: int, stryd_email: str, stryd_password: str
    ) -> None:
        """Update Stryd login credentials for a user."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET stryd_email = ?, stryd_password = ? WHERE id = ?",
                (stryd_email, stryd_password, user_id),
            )

    # ------ Strava OAuth tokens ------

    def get_user_by_strava_athlete_id(self, strava_athlete_id: str) -> Optional[dict]:
        """Find a user by their Strava athlete ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE strava_athlete_id = ?",
                (str(strava_athlete_id),),
            ).fetchone()
        return dict(row) if row else None

    def get_strava_tokens(self, user_id: int) -> Optional[dict]:
        """Return Strava OAuth tokens for a user, or None if not connected."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT strava_access_token, strava_refresh_token,
                          strava_token_expires_at, strava_athlete_id
                   FROM users WHERE id = ?""",
                (user_id,),
            ).fetchone()
        if row and row[0]:
            return {
                "strava_access_token": row[0],
                "strava_refresh_token": row[1],
                "strava_token_expires_at": row[2],
                "strava_athlete_id": row[3],
            }
        return None

    def save_strava_tokens(
        self,
        user_id: int,
        access_token: str,
        refresh_token: str,
        expires_at: int,
        strava_athlete_id: str | None = None,
    ) -> None:
        """Save (or update) Strava OAuth tokens for a user."""
        with self._connect() as conn:
            if strava_athlete_id is not None:
                conn.execute(
                    """UPDATE users
                       SET strava_access_token = ?, strava_refresh_token = ?,
                           strava_token_expires_at = ?, strava_athlete_id = ?
                       WHERE id = ?""",
                    (access_token, refresh_token, expires_at, strava_athlete_id, user_id),
                )
            else:
                conn.execute(
                    """UPDATE users
                       SET strava_access_token = ?, strava_refresh_token = ?,
                           strava_token_expires_at = ?
                       WHERE id = ?""",
                    (access_token, refresh_token, expires_at, user_id),
                )

    def clear_strava_tokens(self, user_id: int) -> None:
        """Remove all Strava credentials for a user."""
        with self._connect() as conn:
            conn.execute(
                """UPDATE users
                   SET strava_access_token = NULL, strava_refresh_token = NULL,
                       strava_token_expires_at = NULL
                   WHERE id = ?""",
                (user_id,),
            )

    def save_strava_webhook_subscription_id(
        self, user_id: int, subscription_id: int
    ) -> None:
        """Store the Strava webhook subscription ID for the user."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET strava_webhook_subscription_id = ? WHERE id = ?",
                (subscription_id, user_id),
            )

    def get_strava_webhook_subscription_id(self, user_id: int) -> int | None:
        """Return the stored Strava webhook subscription ID, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT strava_webhook_subscription_id FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return row[0] if row and row[0] is not None else None

    def update_run_name(self, run_id: int, name: str) -> None:
        """Update the display name of a run."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET name = ? WHERE id = ?",
                (name, run_id),
            )

    def update_run_strava_data(
        self,
        run_id: int,
        strava_activity_id: str | None = None,
        strava_map_polyline: str | None = None,
    ) -> None:
        """Update Strava activity ID and/or map polyline for a run."""
        with self._connect() as conn:
            conn.execute(
                """UPDATE runs
                   SET strava_activity_id = COALESCE(?, strava_activity_id),
                       strava_map_polyline = COALESCE(?, strava_map_polyline)
                   WHERE id = ?""",
                (strava_activity_id, strava_map_polyline, run_id),
            )

    def get_run_by_strava_id(
        self, strava_activity_id: str, user_id: int | None = None
    ) -> Optional[dict]:
        """Get a run by its Strava activity ID."""
        with self._connect() as conn:
            if user_id is not None:
                row = conn.execute(
                    "SELECT * FROM runs WHERE strava_activity_id = ? AND user_id = ?",
                    (str(strava_activity_id), user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM runs WHERE strava_activity_id = ?",
                    (str(strava_activity_id),),
                ).fetchone()
        return dict(row) if row else None

    def get_runs_on_date(self, date: str, user_id: int | None = None) -> list[dict]:
        """Get all runs for a specific date."""
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE date = ? AND user_id = ? ORDER BY id ASC",
                    (date, user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE date = ? ORDER BY id ASC",
                    (date,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_unlinked_runs(self, user_id: int | None = None) -> list[dict]:
        """Return all runs that have no Strava activity ID linked yet."""
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE strava_activity_id IS NULL AND user_id = ? ORDER BY date ASC",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE strava_activity_id IS NULL ORDER BY date ASC"
                ).fetchall()
        return [dict(r) for r in rows]

    def get_user_password_hash(self, user_id: int) -> str | None:
        """Return the stored password hash for the given user, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return row[0] if row else None
