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
    planned_workout_title: str | None = None,
) -> Path:
    """Parse a FIT file, write the YAML alongside it, return the YAML path.

    If manual_upload is True, adds a manual_upload annotation to the YAML.
    If stryd_rss is provided, includes it in the YAML output.
    If planned_workout_title is provided and matches the truncated FIT name,
    uses the full planned workout title instead of the truncated FIT name.
    """
    summary = parse_fit_file(fit_path, timezone=timezone)

    # Replace truncated workout name with full planned workout title if available
    if planned_workout_title:
        fit_name = summary.get("workout_name", "")
        # Check if the FIT name looks like a truncated version of the planned title
        # (FIT files truncate at 32 chars, so check if planned title starts with FIT name)
        if fit_name and len(fit_name) == 32 and planned_workout_title.startswith(fit_name):
            summary["workout_name"] = planned_workout_title
            summary["workout_name_source"] = "planned_workout"
        elif fit_name and planned_workout_title.startswith(fit_name[:31]):
            # Handle case where truncation happened mid-character
            summary["workout_name"] = planned_workout_title
            summary["workout_name_source"] = "planned_workout"

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
