from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from runcoach.config import Config
from runcoach.db import RunCoachDB

log = logging.getLogger(__name__)


def _sanitize_name(name: str) -> str:
    """Convert an activity name to a filesystem-safe string."""
    clean = name.lower().replace(" ", "_").replace("/", "_")
    clean = re.sub(r"[^a-z0-9_-]", "", clean)
    return clean


def sync_new_activities(
    config: Config,
    db: RunCoachDB,
    stryd_email: str = "",
    stryd_password: str = "",
    user_id: int = 1,
) -> list[dict]:
    """
    Sync recent activities from Stryd, download FIT files for any new ones.

    Returns a list of dicts for newly synced activities.
    """
    # Import here to avoid hard dependency at module level
    from strydcmd.stryd_api import StrydAPI

    log_id = db.start_sync_log(user_id=user_id)
    new_runs = []

    try:
        stryd = StrydAPI(stryd_email, stryd_password)
        stryd.authenticate()

        activities = stryd.get_activities(days=config.sync_lookback_days)
        log.info("Stryd returned %d activities", len(activities))

        for activity in activities:
            activity_id = activity.get("id")
            if not activity_id:
                continue

            # Skip if already in our database — but update name if Stryd
            # has since renamed the activity (e.g. after plan-linking).
            existing = db.get_run_by_stryd_id(activity_id, user_id=user_id)
            if existing:
                new_name = activity.get("name", "")
                if new_name and new_name != existing["name"]:
                    log.info(
                        "Updating name for run %s: %r → %r",
                        activity_id, existing["name"], new_name,
                    )
                    db.update_run_name(existing["id"], new_name)
                stryd_rss = activity.get("stress")
                if stryd_rss is not None and existing.get("stryd_rss") is None:
                    db.update_run_rss(existing["id"], stryd_rss)
                    log.debug("Backfilled stryd_rss=%.1f for run %s", stryd_rss, activity_id)
                continue

            name = activity.get("name", "Unnamed Activity")
            timestamp = activity.get("timestamp", 0)
            distance = activity.get("distance")
            moving_time = activity.get("moving_time")
            stryd_rss = activity.get("stress")  # Stryd's Running Stress Score

            dt = datetime.fromtimestamp(timestamp)
            date_str = dt.strftime("%Y-%m-%d")
            date_prefix = dt.strftime("%Y%m%d")

            # If there's a planned workout for this date, prefer its title as
            # the run name — Stryd may not have linked the plan yet at sync time.
            planned = db.get_planned_workout_for_date(date_str, user_id=user_id)
            if planned and planned[0].get("title"):
                name = planned[0]["title"]
                log.debug("Using planned workout title %r for activity %s", name, activity_id)

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
                stryd_rss=stryd_rss,
                user_id=user_id,
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


def sync_planned_workouts(
    config: Config,
    db: RunCoachDB,
    stryd_email: str = "",
    stryd_password: str = "",
    user_id: int = 1,
) -> int:
    """
    Fetch planned workouts from the Stryd training calendar and store them.

    Removes any locally stored planned workouts within the sync date range
    that are no longer present in Stryd's response (moved or deleted).

    Returns the number of workouts upserted.
    """
    from datetime import timedelta

    from strydcmd.stryd_api import StrydAPI

    stryd = StrydAPI(stryd_email, stryd_password)
    stryd.authenticate()

    days_ahead = 30
    workouts = stryd.get_planned_workouts(
        days_ahead=days_ahead,
        days_back=config.sync_lookback_days,
    )
    log.info("Stryd calendar returned %d planned workouts", len(workouts))

    # Build a set of active (date, title) keys from Stryd's response
    active_keys: set[tuple[str, str]] = set()
    active_workouts: list[dict] = []

    for w in workouts:
        # Skip deleted workouts
        if w.get("deleted"):
            continue

        # Each workout entry has a nested "workout" dict with the plan details
        plan = w.get("workout") or {}
        title = plan.get("title") or w.get("name") or "Untitled"

        # Date comes as ISO string like "2026-04-25T10:00:00Z"
        date_raw = w.get("date") or ""
        if not date_raw:
            continue
        try:
            dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue

        active_keys.add((date_str, title))
        active_workouts.append((w, plan, title, date_str))

    # Determine the sync date range used by the API call
    today = datetime.now(timezone.utc).date()
    range_start = (today - timedelta(days=config.sync_lookback_days)).strftime("%Y-%m-%d")
    range_end = (today + timedelta(days=days_ahead + 1)).strftime("%Y-%m-%d")

    # Remove local workouts in that range that are no longer in Stryd
    local_workouts = db.get_planned_workouts_in_range(range_start, range_end, user_id=user_id)
    removed = 0
    for lw in local_workouts:
        key = (lw["date"], lw["title"])
        if key not in active_keys:
            if db.delete_planned_workout(lw["date"], lw["title"], user_id=user_id):
                removed += 1
                log.info("Removed stale planned workout: %s on %s", lw["title"], lw["date"])

    if removed:
        log.info("Removed %d stale planned workout(s)", removed)

    # Upsert all active workouts
    count = 0
    for w, plan, title, date_str in active_workouts:
        description = plan.get("desc") or plan.get("description") or ""
        workout_type = plan.get("type") or ""

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
            user_id=user_id,
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
