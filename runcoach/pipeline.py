from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.sync import sync_new_activities
from runcoach.parser import parse_and_write
from runcoach.analyzer import analyze_and_write

log = logging.getLogger(__name__)

_pipeline_lock = threading.Lock()


def run_full_pipeline(config: Config, db: RunCoachDB) -> dict:
    """
    Run the complete pipeline: sync -> parse -> analyze.

    Returns a summary dict with counts.
    """
    if not _pipeline_lock.acquire(blocking=False):
        log.info("Pipeline already running, skipping")
        return {"skipped": True}

    try:
        summary = {"synced": 0, "parsed": 0, "analyzed": 0, "errors": 0}

        # 1. Sync new activities from Stryd
        try:
            new_runs = sync_new_activities(config, db)
            summary["synced"] = len(new_runs)
        except Exception as e:
            log.error("Sync stage failed: %s", e)
            summary["errors"] += 1

        # 2. Parse all pending FIT files
        for run in db.get_pending_runs("synced"):
            try:
                fit_path = config.data_dir / run["fit_path"]
                yaml_path = parse_and_write(fit_path, timezone=config.timezone)
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

        # 3. Analyze all parsed runs with GPT-4o
        if not config.openai_api_key:
            log.warning("No OPENAI_API_KEY set, skipping analysis stage")
        else:
            for run in db.get_pending_runs("parsed", date_from=config.analyze_from):
                try:
                    yaml_path = config.data_dir / run["yaml_path"]
                    md_path, result = analyze_and_write(yaml_path, config, db=db)
                    md_path_rel = str(md_path.relative_to(config.data_dir))

                    db.update_analyzed(
                        run_id=run["id"],
                        md_path=md_path_rel,
                        commentary=result["commentary"],
                        model_used=config.openai_model,
                        prompt_tokens=result.get("prompt_tokens"),
                        completion_tokens=result.get("completion_tokens"),
                    )
                    summary["analyzed"] += 1
                except Exception as e:
                    log.exception("Analysis failed for run %s: %s", run["id"], e)
                    db.update_error(run["id"], f"Analysis error: {e}")
                    summary["errors"] += 1

        log.info(
            "Pipeline complete: synced=%d parsed=%d analyzed=%d errors=%d",
            summary["synced"], summary["parsed"],
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
    summary = run_full_pipeline(config, db)
    print(f"Pipeline result: {summary}")


if __name__ == "__main__":
    main()
