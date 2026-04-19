from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.sync import sync_new_activities, sync_planned_workouts
from runcoach.parser import parse_and_write
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

        # 2. Parse all pending FIT files for this user
        for run in db.get_pending_runs("synced", user_id=user_id):
            try:
                fit_path = config.data_dir / run["fit_path"]
                stryd_rss = run.get("stryd_rss")

                # Get planned workout title for this date to use full name
                planned_workout_title = None
                if run.get("date"):
                    planned_workouts = db.get_planned_workout_for_date(
                        run["date"], user_id=user_id
                    )
                    if planned_workouts:
                        planned_workout_title = planned_workouts[0]["title"]

                yaml_path = parse_and_write(
                    fit_path,
                    timezone=config.timezone,
                    stryd_rss=stryd_rss,
                    planned_workout_title=planned_workout_title,
                )
                yaml_path_rel = str(yaml_path.relative_to(config.data_dir))

                # Read back parsed summary for DB fields
                import yaml as _yaml
                with open(yaml_path, "r", encoding="utf-8") as f:
                    parsed = _yaml.safe_load(f)

                db.update_parsed(
                    run_id=run["id"],
                    yaml_path=yaml_path_rel,
                    avg_power_w=parsed.get("avg_power"),
                    avg_hr=parsed.get("avg_hr"),
                    workout_name=parsed.get("workout_name"),
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
                    yaml_path = config.data_dir / run["yaml_path"]
                    md_path, result = analyze_and_write(
                        yaml_path, config, db=db, user_id=user_id
                    )
                    md_path_rel = str(md_path.relative_to(config.data_dir))

                    db.update_analyzed(
                        run_id=run["id"],
                        md_path=md_path_rel,
                        commentary=result["commentary"],
                        model_used=config.active_model,
                        prompt_tokens=result.get("prompt_tokens"),
                        completion_tokens=result.get("completion_tokens"),
                    )
                    summary["analyzed"] += 1
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
