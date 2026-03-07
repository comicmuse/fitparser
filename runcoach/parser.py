from __future__ import annotations

import logging
from pathlib import Path

import yaml

from runcoach.fit_parser import build_blocks_from_fit

log = logging.getLogger(__name__)


def parse_fit_file(fit_path: Path, timezone: str = "Europe/London") -> dict:
    """Parse a FIT file and return the summary dict."""
    summary = build_blocks_from_fit(fit_path, tz_name=timezone)
    return summary


def parse_and_write(
    fit_path: Path,
    timezone: str = "Europe/London",
    manual_upload: bool = False,
    stryd_rss: float | None = None,
) -> Path:
    """Parse a FIT file, write the YAML alongside it, return the YAML path.

    If manual_upload is True, adds a manual_upload annotation to the YAML.
    If stryd_rss is provided, includes it in the YAML output.
    """
    summary = parse_fit_file(fit_path, timezone=timezone)

    if stryd_rss is not None:
        summary["stryd_rss"] = round(stryd_rss, 1)
        summary["stryd_rss_note"] = "Running Stress Score from Stryd (official)"

    if manual_upload:
        summary["manual_upload"] = True
        summary["manual_upload_note"] = (
            "This run was manually uploaded without Stryd sync. "
            "Power data may be missing or incomplete."
        )
    
    yaml_path = fit_path.with_suffix(".yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(summary, f, sort_keys=False, allow_unicode=True)
    log.info("Wrote %s", yaml_path)
    return yaml_path
