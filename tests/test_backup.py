"""Tests for SQLite hot-backup functionality."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from runcoach.backup import backup_database
from runcoach.scheduler import Scheduler


# ---------------------------------------------------------------------------
# backup_database()
# ---------------------------------------------------------------------------


def test_backup_creates_bak_file(tmp_path):
    """backup_database() creates a .bak file next to the source."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()

    backup_database(db_path)

    assert (tmp_path / "test.db.bak").exists()


def test_backup_contains_source_data(tmp_path):
    """The backup file contains the same rows as the source."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO runs VALUES (1, 'monday')")
    conn.commit()
    conn.close()

    backup_database(db_path)

    bak = sqlite3.connect(tmp_path / "test.db.bak")
    rows = bak.execute("SELECT id, name FROM runs").fetchall()
    bak.close()
    assert rows == [(1, "monday")]


def test_backup_is_wal_free(tmp_path):
    """The backup is a clean WAL-free file (no -wal sidecar produced)."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    conn.close()

    backup_database(db_path)

    bak_path = tmp_path / "test.db.bak"
    assert bak_path.exists()
    assert not (tmp_path / "test.db.bak-wal").exists()


def test_backup_source_missing_raises(tmp_path):
    """backup_database() raises FileNotFoundError for a missing source."""
    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / "nonexistent.db")


# ---------------------------------------------------------------------------
# Scheduler backup loop
# ---------------------------------------------------------------------------


def _make_scheduler(config_kwargs=None):
    config = MagicMock()
    config.sync_interval_hours = 0
    config.backup_interval_hours = 24
    if config_kwargs:
        for k, v in config_kwargs.items():
            setattr(config, k, v)
    db = MagicMock()
    return Scheduler(config=config, db=db)


def test_scheduler_starts_backup_thread_regardless_of_sync_interval():
    """Backup thread starts even when sync is disabled (SYNC_INTERVAL_HOURS=0)."""
    sched = _make_scheduler()
    sched.start()
    time.sleep(0.1)
    try:
        assert sched.is_backup_running or sched._backup_thread is not None
    finally:
        sched.stop()


def test_scheduler_calls_backup_on_start(tmp_path):
    """Scheduler calls backup_database() once at startup."""
    db_path = tmp_path / "runcoach.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()

    config = MagicMock()
    config.sync_interval_hours = 0
    config.backup_interval_hours = 24
    config.db_path = db_path

    db = MagicMock()
    sched = Scheduler(config=config, db=db)

    with patch("runcoach.scheduler.backup_database") as mock_backup:
        sched.start()
        time.sleep(0.2)
        sched.stop()

    mock_backup.assert_called_at_least_once = lambda: None  # silence lint
    assert mock_backup.call_count >= 1
    call_args = mock_backup.call_args[0][0]
    assert call_args == db_path
