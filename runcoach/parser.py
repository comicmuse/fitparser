from __future__ import annotations

import logging
from pathlib import Path

from runcoach.fit_parser import build_blocks_from_fit

log = logging.getLogger(__name__)


def parse_fit_file(fit_path: Path, timezone: str = "Europe/London") -> dict:
    """Parse a FIT file and return the summary dict."""
    summary = build_blocks_from_fit(fit_path, tz_name=timezone)
    return summary
