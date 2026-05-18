from __future__ import annotations

import logging
import threading
import time

from runcoach.backup import backup_database
from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.pipeline import run_full_pipeline

log = logging.getLogger(__name__)


class Scheduler:
    """Background scheduler that runs the pipeline periodically."""

    def __init__(self, config: Config, db: RunCoachDB):
        self.config = config
        self.db = db
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._backup_thread: threading.Thread | None = None
        self._backup_stop_event = threading.Event()
        self._backup_running = False

    @property
    def is_syncing(self) -> bool:
        return self._running

    @property
    def is_backup_running(self) -> bool:
        return self._backup_running

    def start(self) -> None:
        """Start background threads for sync (if interval > 0) and backup."""
        self._backup_stop_event.clear()
        self._backup_thread = threading.Thread(target=self._backup_loop, daemon=True)
        self._backup_thread.start()

        if self.config.sync_interval_hours == 0:
            log.info("Scheduler sync disabled (SYNC_INTERVAL_HOURS=0)")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info(
            "Scheduler started (interval=%dh)", self.config.sync_interval_hours
        )

    def stop(self) -> None:
        """Signal the scheduler to stop."""
        self._stop_event.set()
        self._backup_stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._backup_thread:
            self._backup_thread.join(timeout=5)

    def trigger_now(self) -> None:
        """Trigger an immediate pipeline run in a background thread."""
        threading.Thread(target=self._run_once, daemon=True).start()

    def _loop(self) -> None:
        # Run once at startup, then every interval
        self._run_once()
        interval_s = self.config.sync_interval_hours * 3600
        while not self._stop_event.wait(timeout=interval_s):
            self._run_once()

    def _backup_loop(self) -> None:
        self._backup_once()
        interval_s = self.config.backup_interval_hours * 3600
        while not self._backup_stop_event.wait(timeout=interval_s):
            self._backup_once()

    def _backup_once(self) -> None:
        self._backup_running = True
        try:
            backup_database(self.config.db_path)
            log.info("Database backup complete")
        except Exception:
            log.exception("Backup error")
        finally:
            self._backup_running = False

    def _run_once(self) -> None:
        self._running = True
        try:
            users = self.db.get_all_users()
            for user in users:
                try:
                    run_full_pipeline(self.config, self.db, user_id=user["id"])
                except Exception:
                    log.exception("Pipeline error for user %d", user["id"])
        except Exception:
            log.exception("Scheduler error fetching users")
        finally:
            self._running = False
