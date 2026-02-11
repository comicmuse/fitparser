from __future__ import annotations

import logging
import threading
import time

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

    @property
    def is_syncing(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the background scheduler thread."""
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
        if self._thread:
            self._thread.join(timeout=5)

    def trigger_now(self) -> None:
        """Trigger an immediate pipeline run in a background thread."""
        threading.Thread(target=self._run_once, daemon=True).start()

    def _loop(self) -> None:
        # Run once at startup, then every interval
        self._run_once()
        interval_s = self.config.sync_interval_hours * 3600
        while not self._stop_event.wait(timeout=interval_s):
            self._run_once()

    def _run_once(self) -> None:
        self._running = True
        try:
            run_full_pipeline(self.config, self.db)
        except Exception:
            log.exception("Pipeline error in scheduler")
        finally:
            self._running = False
