from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from runcoach.config import Config
from runcoach.db import RunCoachDB
import json as _json

from runcoach.sync import sync_new_activities, sync_planned_workouts
from runcoach.parser import parse_fit_file
from runcoach.analyzer import analyze_and_write

log = logging.getLogger(__name__)

_pipeline_lock = threading.Lock()


def run_full_pipeline(config: Config, db: RunCoachDB, user_id: int = 1) -> dict:
    """
    Run the complete pipeline: sync -> parse -> analyze for a specific user.

    Returns a summary dict with counts.
    """
    if not _pipeline_lock.acquire(blocking=False):
        log.info("Pipeline already running, skipping")
        return {"skipped": True}

    try:
        summary = {"synced": 0, "parsed": 0, "analyzed": 0, "errors": 0, "planned": 0}

        # Load Stryd credentials from DB for this user
        creds = db.get_stryd_credentials(user_id)
        stryd_email = creds.get("stryd_email", "")
        stryd_password = creds.get("stryd_password", "")

        # 1. Sync new activities from Stryd
        if not stryd_email or not stryd_password:
            log.info("Stryd credentials not configured for user %d, skipping sync", user_id)
        else:
            try:
                new_runs = sync_new_activities(
                    config, db,
                    stryd_email=stryd_email,
                    stryd_password=stryd_password,
                    user_id=user_id,
                )
                summary["synced"] = len(new_runs)
            except Exception as e:
                log.error("Sync stage failed for user %d: %s", user_id, e)
                summary["errors"] += 1

        # 1b. Sync planned workouts from training calendar
        if stryd_email and stryd_password:
            try:
                planned_count = sync_planned_workouts(
                    config, db,
                    stryd_email=stryd_email,
                    stryd_password=stryd_password,
                    user_id=user_id,
                )
                summary["planned"] = planned_count
            except Exception as e:
                log.error("Planned workouts sync failed for user %d: %s", user_id, e)

        # 1c. Link unlinked runs to Strava activities (if Strava is configured)
        if config.strava_client_id:
            try:
                from runcoach.strava import link_unlinked_runs
                strava_linked = link_unlinked_runs(db, user_id, config)
                if strava_linked:
                    log.info("Strava: linked %d run(s) for user %d", strava_linked, user_id)
                summary["strava_linked"] = strava_linked
            except Exception as e:
                log.error("Strava link stage failed for user %d: %s", user_id, e)

        # 2. Parse all pending FIT files for this user
        for run in db.get_pending_runs("synced", user_id=user_id):
            try:
                fit_path = config.data_dir / run["fit_path"]
                stryd_rss = run.get("stryd_rss")

                planned_workout_title = None
                if run.get("date"):
                    planned_workouts = db.get_planned_workout_for_date(
                        run["date"], user_id=user_id
                    )
                    if planned_workouts:
                        planned_workout_title = planned_workouts[0]["title"]

                parsed_summary = parse_fit_file(fit_path, timezone=config.timezone)

                if planned_workout_title:
                    fit_name = parsed_summary.get("workout_name", "")
                    if fit_name and len(fit_name) == 32 and planned_workout_title.startswith(fit_name):
                        parsed_summary["workout_name"] = planned_workout_title
                        parsed_summary["workout_name_source"] = "planned_workout"
                    elif fit_name and planned_workout_title.startswith(fit_name[:31]):
                        parsed_summary["workout_name"] = planned_workout_title
                        parsed_summary["workout_name_source"] = "planned_workout"

                if stryd_rss is not None:
                    parsed_summary["stryd_rss"] = round(stryd_rss, 1)
                    parsed_summary["stryd_rss_note"] = "Running Stress Score from Stryd (official)"

                db.update_parsed(
                    run_id=run["id"],
                    yaml_path=None,
                    avg_power_w=parsed_summary.get("avg_power"),
                    avg_hr=parsed_summary.get("avg_hr"),
                    workout_name=parsed_summary.get("workout_name"),
                    parsed_data=_json.dumps(parsed_summary),
                )
                summary["parsed"] += 1
            except Exception as e:
                log.exception("Parse failed for run %s: %s", run["id"], e)
                db.update_error(run["id"], f"Parse error: {e}")
                summary["errors"] += 1

        # 3. Analyze all parsed runs for this user
        if not config.has_llm:
            log.warning("No LLM provider configured, skipping analysis stage")
        elif not config.llm_auto_analyse:
            log.info("LLM_AUTO_ANALYSE is off, skipping automatic analysis")
        else:
            for run in db.get_pending_runs("parsed", user_id=user_id, date_from=config.analyze_from):
                try:
                    result = analyze_and_write(run, config, db=db, user_id=user_id)
                    db.update_analyzed(
                        run_id=run["id"],
                        md_path=None,
                        commentary=result["commentary"],
                        model_used=config.active_model,
                        prompt_tokens=result.get("prompt_tokens"),
                        completion_tokens=result.get("completion_tokens"),
                    )
                    summary["analyzed"] += 1
                    try:
                        from runcoach.notifications import send_analysis_notification
                        send_analysis_notification(
                            run["id"], run.get("name", "Run"), user_id, db, config
                        )
                    except Exception:
                        log.warning(
                            "Push notification failed for run %s (non-fatal)", run["id"]
                        )
                except Exception as e:
                    log.exception("Analysis failed for run %s: %s", run["id"], e)
                    db.update_error(run["id"], f"Analysis error: {e}")
                    summary["errors"] += 1

        log.info(
            "Pipeline complete (user=%d): synced=%d planned=%d parsed=%d analyzed=%d errors=%d",
            user_id, summary["synced"], summary["planned"], summary["parsed"],
            summary["analyzed"], summary["errors"],
        )
        return summary

    finally:
        _pipeline_lock.release()


def main() -> None:
    """CLI entry point for one-shot pipeline run."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = Config.from_env()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    db = RunCoachDB(config.db_path)
    # Run for all users
    for user in db.get_all_users():
        summary = run_full_pipeline(config, db, user_id=user["id"])
        print(f"Pipeline result (user={user['id']}): {summary}")


if __name__ == "__main__":
    main()
