from __future__ import annotations

import logging
from pathlib import Path

import yaml

from fit_to_yaml_blocks import build_blocks_from_fit

log = logging.getLogger(__name__)


def parse_fit_file(fit_path: Path, timezone: str = "Europe/London") -> dict:
    """Parse a FIT file and return the summary dict."""
    summary = build_blocks_from_fit(fit_path, tz_name=timezone)
    return summary


def parse_and_write(fit_path: Path, timezone: str = "Europe/London") -> Path:
    """Parse a FIT file, write the YAML alongside it, return the YAML path."""
    summary = parse_fit_file(fit_path, timezone=timezone)
    yaml_path = fit_path.with_suffix(".yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(summary, f, sort_keys=False, allow_unicode=True)
    log.info("Wrote %s", yaml_path)
    return yaml_path
