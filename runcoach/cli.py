#!/usr/bin/env python3
"""RunCoach CLI — parse FIT files and trigger analysis by run ID."""

from __future__ import annotations

import argparse
import json as _json
import logging
import sys
from pathlib import Path

import yaml as _yaml

from runcoach.parser import parse_fit_file
from runcoach.analyzer import analyze_and_write
from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.context import compute_rss

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def parse_fit(fit_path: Path, config: Config, db: RunCoachDB, user_id: int = 1) -> None:
    """Parse a single FIT file, upsert DB record, store parsed_data."""
    if not fit_path.exists():
        log.error("File not found: %s", fit_path)
        sys.exit(1)
    if fit_path.suffix.lower() != ".fit":
        log.error("File must have .fit extension: %s", fit_path)
        sys.exit(1)

    log.info("Parsing %s...", fit_path)
    summary = parse_fit_file(fit_path, timezone=config.timezone)

    fit_path_rel = str(fit_path.relative_to(config.data_dir)) if fit_path.is_relative_to(config.data_dir) else str(fit_path)

    # Upsert: insert new run or update existing one
    existing = db.get_run_by_fit_path(fit_path_rel, user_id=user_id)
    if existing:
        run_id = existing["id"]
    else:
        from datetime import datetime
        run_id = db.insert_manual_run(
            name=summary.get("workout_name") or fit_path.stem,
            date=summary.get("date") or datetime.now().strftime("%Y-%m-%d"),
            fit_path=fit_path_rel,
            distance_m=summary.get("distance_km", 0) * 1000 if summary.get("distance_km") else None,
            moving_time_s=int(summary.get("duration_min", 0) * 60) if summary.get("duration_min") else None,
            user_id=user_id,
        )

    db.update_parsed(
        run_id=run_id,
        yaml_path=None,
        avg_power_w=summary.get("avg_power"),
        avg_hr=summary.get("avg_hr"),
        workout_name=summary.get("workout_name"),
        parsed_data=_json.dumps(summary),
    )
    log.info("Stored parsed_data for run %d", run_id)
    print(f"Parsed: run_id={run_id}, workout={summary.get('workout_name')}")


def analyze_by_run_id(run_id: int, config: Config, db: RunCoachDB, user_id: int = 1) -> None:
    """Analyze a single run by its DB ID."""
    run = db.get_run(run_id, user_id=user_id)
    if not run:
        log.error("Run %d not found", run_id)
        sys.exit(1)
    if not run.get("parsed_data"):
        log.error("Run %d has no parsed_data — parse it first", run_id)
        sys.exit(1)

    log.info("Analyzing run %d...", run_id)
    result = analyze_and_write(run, config, db=db, user_id=user_id)
    db.update_analyzed(
        run_id=run_id,
        md_path=None,
        commentary=result["commentary"],
        model_used=config.active_model,
        prompt_tokens=result.get("prompt_tokens"),
        completion_tokens=result.get("completion_tokens"),
    )
    log.info("Analysis complete for run %d", run_id)
    print(f"Analyzed: run_id={run_id}")


def analyze_by_date(date: str, config: Config, db: RunCoachDB, user_id: int = 1) -> None:
    """Analyze all parsed runs on a given date (YYYY-MM-DD)."""
    with db._connect() as conn:
        rows = conn.execute(
            """SELECT * FROM runs
               WHERE date = ? AND user_id = ?
                 AND stage IN ('parsed', 'analyzed')
                 AND parsed_data IS NOT NULL
               ORDER BY id""",
            (date, user_id),
        ).fetchall()

    if not rows:
        log.info("No parsed runs found for date %s", date)
        return

    for row in rows:
        run = dict(row)
        log.info("Analyzing run %d (%s)...", run["id"], run.get("workout_name"))
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
            print(f"Analyzed: run_id={run['id']}")
        except Exception as e:
            log.error("Analysis failed for run %d: %s", run["id"], e)


def backfill_rss(config: Config, db: RunCoachDB, dry_run: bool = False) -> None:
    """
    Backfill stryd_rss for runs where it is NULL.

    Reads from parsed_data (preferred) or falls back to the yaml_path file.
    """
    with db._connect() as conn:
        rows = conn.execute(
            """SELECT id, name, date, parsed_data, yaml_path FROM runs
               WHERE stryd_rss IS NULL
                 AND stage IN ('parsed', 'analyzed')
               ORDER BY date""",
        ).fetchall()

    updated = skipped = 0
    for row in rows:
        run_id = row["id"]
        name = row["name"]
        date = row["date"]

        parsed = None
        if row["parsed_data"]:
            try:
                parsed = _json.loads(row["parsed_data"])
            except Exception:
                pass
        elif row["yaml_path"]:
            yaml_path = config.data_dir / row["yaml_path"]
            if yaml_path.exists():
                try:
                    parsed = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

        if parsed is None:
            log.debug("No data for run %d (%s %s), skipping", run_id, date, name)
            skipped += 1
            continue

        rss = parsed.get("stryd_rss")
        if rss is None:
            pwr = parsed.get("avg_power") or 0
            cp = parsed.get("critical_power") or 0
            dur = parsed.get("duration_min") or 0
            if pwr > 0 and cp > 0 and dur > 0:
                rss = round(compute_rss(pwr, cp, dur), 1)

        if rss is None:
            log.debug("No RSS data for run %d (%s %s), skipping", run_id, date, name)
            skipped += 1
            continue

        log.info(
            "%srun %d (%s %s): stryd_rss = %.1f",
            "[dry-run] " if dry_run else "", run_id, date, name, rss,
        )
        if not dry_run:
            db.update_run_rss(run_id, rss)
        updated += 1

    log.info("Done: %d updated, %d skipped%s", updated, skipped, " (dry run)" if dry_run else "")


def migrate(config: Config, db: RunCoachDB) -> None:
    """
    Back-fill parsed_data for all runs that have a yaml_path but no parsed_data.

    Idempotent — skips runs already having parsed_data populated.
    """
    with db._connect() as conn:
        rows = conn.execute(
            """SELECT id, name, date, yaml_path FROM runs
               WHERE yaml_path IS NOT NULL AND parsed_data IS NULL
               ORDER BY date""",
        ).fetchall()

    migrated = skipped = 0
    for row in rows:
        run_id, name, date, yaml_rel = row["id"], row["name"], row["date"], row["yaml_path"]
        yaml_path = config.data_dir / yaml_rel
        if not yaml_path.exists():
            log.warning("YAML not found for run %d (%s %s), skipping", run_id, date, name)
            skipped += 1
            continue
        try:
            data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Could not read %s: %s", yaml_path, e)
            skipped += 1
            continue
        db.store_parsed_data(run_id, _json.dumps(data))
        log.info("Migrated run %d (%s %s)", run_id, date, name)
        migrated += 1

    log.info(
        "Migration complete: %d migrated, %d skipped (missing YAML)",
        migrated, skipped,
    )
    print(f"Done: {migrated} migrated, {skipped} skipped.")


def migrate_main() -> None:
    """CLI entry point for the one-shot YAML→DB migration."""
    config = Config.from_env()
    db = RunCoachDB(config.db_path)
    migrate(config, db)


def main() -> None:
    """CLI entry point with argparse for subcommands."""
    parser = argparse.ArgumentParser(
        description="RunCoach CLI — parse FIT files and trigger analysis by run ID",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # parse subcommand
    parse_parser = subparsers.add_parser("parse", help="Parse a FIT file and store in DB")
    parse_parser.add_argument("--file", type=Path, required=True, help="Path to .fit file")

    # analyze subcommand
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a run by ID or date")
    analyze_group = analyze_parser.add_mutually_exclusive_group(required=True)
    analyze_group.add_argument("--run-id", type=int, help="Analyze a specific run by DB ID")
    analyze_group.add_argument("--date", type=str, help="Analyze all parsed runs on date (YYYY-MM-DD)")

    # backfill-rss subcommand
    backfill_parser = subparsers.add_parser("backfill-rss", help="Backfill stryd_rss for historical runs")
    backfill_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = Config.from_env()
    db = RunCoachDB(config.db_path)

    if args.command == "parse":
        parse_fit(args.file, config, db)

    elif args.command == "analyze":
        if args.run_id:
            analyze_by_run_id(args.run_id, config, db)
        else:
            analyze_by_date(args.date, config, db)

    elif args.command == "backfill-rss":
        backfill_rss(config, db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
