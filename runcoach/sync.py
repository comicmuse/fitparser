from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from runcoach.config import Config
from runcoach.db import RunCoachDB

log = logging.getLogger(__name__)


def _sanitize_name(name: str) -> str:
    """Convert an activity name to a filesystem-safe string."""
    clean = name.lower().replace(" ", "_").replace("/", "_")
    clean = re.sub(r"[^a-z0-9_-]", "", clean)
    return clean


def sync_new_activities(config: Config, db: RunCoachDB) -> list[dict]:
    """
    Sync recent activities from Stryd, download FIT files for any new ones.

    Returns a list of dicts for newly synced activities.
    """
    # Import here to avoid hard dependency at module level
    from strydcmd.stryd_api import StrydAPI

    log_id = db.start_sync_log()
    new_runs = []

    try:
        stryd = StrydAPI(config.stryd_email, config.stryd_password)
        stryd.authenticate()

        activities = stryd.get_activities(days=config.sync_lookback_days)
        log.info("Stryd returned %d activities", len(activities))

        for activity in activities:
            activity_id = activity.get("id")
            if not activity_id:
                continue

            # Skip if already in our database
            if db.get_run_by_stryd_id(activity_id):
                continue

            name = activity.get("name", "Unnamed Activity")
            timestamp = activity.get("timestamp", 0)
            distance = activity.get("distance")
            moving_time = activity.get("moving_time")

            dt = datetime.fromtimestamp(timestamp)
            date_str = dt.strftime("%Y-%m-%d")
            date_prefix = dt.strftime("%Y%m%d")
            clean_name = _sanitize_name(name)
            dir_name = f"{date_prefix}_{clean_name}"

            # Build directory: data/activities/YYYY/MM/YYYYMMDD_name/
            activity_dir = (
                config.activities_dir
                / dt.strftime("%Y")
                / dt.strftime("%m")
                / dir_name
            )
            activity_dir.mkdir(parents=True, exist_ok=True)

            # Download FIT file
            fit_filename = f"{dir_name}"
            filepath = stryd.download_fit_file(
                str(activity_id),
                str(activity_dir),
                filename=fit_filename,
            )

            if not filepath:
                log.warning("Failed to download FIT for activity %s (%s)", activity_id, name)
                continue

            # Store path relative to data_dir
            fit_path_rel = str(Path(filepath).relative_to(config.data_dir))

            run_id = db.insert_run(
                stryd_activity_id=activity_id,
                name=name,
                date=date_str,
                fit_path=fit_path_rel,
                distance_m=distance,
                moving_time_s=int(moving_time) if moving_time else None,
            )

            new_runs.append({"id": run_id, "name": name, "date": date_str})
            log.info("Synced: %s (%s)", name, date_str)

        db.finish_sync_log(
            log_id,
            status="success",
            activities_found=len(activities),
            activities_new=len(new_runs),
        )

    except Exception as e:
        log.exception("Sync failed")
        db.finish_sync_log(log_id, status="error", error_message=str(e))
        raise

    return new_runs


def sync_planned_workouts(config: Config, db: RunCoachDB) -> int:
    """
    Fetch planned workouts from the Stryd training calendar and store them.

    Returns the number of workouts upserted.
    """
    from strydcmd.stryd_api import StrydAPI

    stryd = StrydAPI(config.stryd_email, config.stryd_password)
    stryd.authenticate()

    workouts = stryd.get_planned_workouts(
        days_ahead=30,
        days_back=config.sync_lookback_days,
    )
    log.info("Stryd calendar returned %d planned workouts", len(workouts))

    count = 0
    for w in workouts:
        # Skip deleted workouts
        if w.get("deleted"):
            continue

        # Each workout entry has a nested "workout" dict with the plan details
        plan = w.get("workout") or {}
        title = plan.get("title") or w.get("name") or "Untitled"
        description = plan.get("desc") or plan.get("description") or ""
        workout_type = plan.get("type") or ""

        # Date comes as ISO string like "2026-04-25T10:00:00Z"
        date_raw = w.get("date") or ""
        if not date_raw:
            continue
        try:
            dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue

        duration_s = w.get("duration")  # seconds
        distance_m = w.get("distance")  # metres
        stress = w.get("stress")
        activity_id = w.get("activity_id") or None

        # Intensity zones as JSON string
        zones = w.get("intensity_zones")
        zones_str = json.dumps(zones) if zones else None

        db.upsert_planned_workout(
            date=date_str,
            title=title,
            description=description,
            workout_type=workout_type,
            duration_s=duration_s,
            distance_m=distance_m,
            stress=stress,
            intensity_zones=zones_str,
            activity_id=str(activity_id) if activity_id else None,
            raw_json=json.dumps(w),
        )
        count += 1

    log.info("Upserted %d planned workouts", count)
    return count
