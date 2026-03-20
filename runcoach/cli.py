#!/usr/bin/env python3
"""
CLI tool for manual parse and analyze operations on FIT files.

Provides two main subcommands:
- parse: Parse FIT files to YAML (single file or directory)
- analyze: Analyze YAML files with GPT-4o coach (single file or directory)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from runcoach.parser import parse_and_write
from runcoach.analyzer import analyze_and_write
from runcoach.config import Config
from runcoach.db import RunCoachDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def parse_file(fit_path: Path, timezone: str, output_path: Path | None = None) -> None:
    """Parse a single FIT file to YAML."""
    if not fit_path.exists():
        log.error("File not found: %s", fit_path)
        sys.exit(1)

    if not fit_path.suffix.lower() == ".fit":
        log.error("File must have .fit extension: %s", fit_path)
        sys.exit(1)

    log.info("Parsing %s...", fit_path)
    yaml_path = parse_and_write(fit_path, timezone=timezone, manual_upload=False)

    if output_path:
        yaml_path.rename(output_path)
        log.info("Wrote %s", output_path)
    else:
        log.info("Wrote %s", yaml_path)


def parse_directory(directory: Path, timezone: str, pattern: str = "*.fit") -> None:
    """Parse all FIT files in a directory (non-recursive)."""
    if not directory.exists() or not directory.is_dir():
        log.error("Directory not found: %s", directory)
        sys.exit(1)

    fit_files = list(directory.glob(pattern))
    if not fit_files:
        log.warning("No files matching %s found in %s", pattern, directory)
        return

    log.info("Found %d FIT files in %s", len(fit_files), directory)

    for fit_path in fit_files:
        try:
            parse_file(fit_path, timezone, output_path=None)
        except Exception as e:
            log.error("Failed to parse %s: %s", fit_path, e)


def analyze_file(yaml_path: Path, config: Config, db: RunCoachDB | None = None) -> None:
    """Analyze a single parsed YAML file."""
    if not yaml_path.exists():
        log.error("File not found: %s", yaml_path)
        sys.exit(1)

    if not yaml_path.suffix.lower() in (".yaml", ".yml"):
        log.error("File must have .yaml or .yml extension: %s", yaml_path)
        sys.exit(1)

    log.info("Analyzing %s...", yaml_path)
    try:
        md_path, _ = analyze_and_write(yaml_path, config, db=db)
        log.info("Wrote %s", md_path)
    except Exception as e:
        log.error("Failed to analyze %s: %s", yaml_path, e)
        sys.exit(1)


def analyze_directory(directory: Path, config: Config, db: RunCoachDB | None = None, pattern: str = "*.yaml") -> None:
    """Analyze all YAML files in a directory (non-recursive)."""
    if not directory.exists() or not directory.is_dir():
        log.error("Directory not found: %s", directory)
        sys.exit(1)

    yaml_files = list(directory.glob(pattern))
    if not yaml_files:
        log.warning("No files matching %s found in %s", pattern, directory)
        return

    log.info("Found %d YAML files in %s", len(yaml_files), directory)

    for yaml_path in yaml_files:
        try:
            analyze_file(yaml_path, config, db=db)
        except Exception as e:
            log.error("Failed to analyze %s: %s", yaml_path, e)


def main() -> None:
    """CLI entry point with argparse for subcommands."""
    parser = argparse.ArgumentParser(
        description="RunCoach CLI - Manual parse and analyze operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Parse subcommand
    parse_parser = subparsers.add_parser(
        "parse",
        help="Parse FIT file(s) to YAML",
    )
    parse_parser.add_argument(
        "--file",
        type=Path,
        help="Parse a single FIT file",
    )
    parse_parser.add_argument(
        "--directory",
        type=Path,
        help="Parse all FIT files in a directory",
    )
    parse_parser.add_argument(
        "--timezone",
        default="Europe/London",
        help="Timezone for timestamps (default: Europe/London)",
    )
    parse_parser.add_argument(
        "--output",
        type=Path,
        help="Output path (only for --file mode)",
    )
    parse_parser.add_argument(
        "--pattern",
        default="*.fit",
        help="File pattern for --directory mode (default: *.fit)",
    )

    # Analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze YAML file(s) with GPT-4o coach",
    )
    analyze_parser.add_argument(
        "--file",
        type=Path,
        help="Analyze a single YAML file",
    )
    analyze_parser.add_argument(
        "--directory",
        type=Path,
        help="Analyze all YAML files in a directory",
    )
    analyze_parser.add_argument(
        "--pattern",
        default="*.yaml",
        help="File pattern for --directory mode (default: *.yaml)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "parse":
        if not args.file and not args.directory:
            log.error("Must specify either --file or --directory")
            parse_parser.print_help()
            sys.exit(1)

        if args.file and args.directory:
            log.error("Cannot specify both --file and --directory")
            sys.exit(1)

        if args.output and args.directory:
            log.error("--output can only be used with --file")
            sys.exit(1)

        if args.file:
            parse_file(args.file, args.timezone, args.output)
        else:
            parse_directory(args.directory, args.timezone, args.pattern)

    elif args.command == "analyze":
        if not args.file and not args.directory:
            log.error("Must specify either --file or --directory")
            analyze_parser.print_help()
            sys.exit(1)

        if args.file and args.directory:
            log.error("Cannot specify both --file and --directory")
            sys.exit(1)

        config = Config.from_env()
        db = RunCoachDB(config.db_path)

        if args.file:
            analyze_file(args.file, config, db=db)
        else:
            analyze_directory(args.directory, config, db=db, pattern=args.pattern)


if __name__ == "__main__":
    main()
