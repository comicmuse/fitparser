# YAML → DB Migration Design

## Goal

Replace YAML files as the storage layer for parsed workout data. The SQLite database becomes the single authoritative store. Parsed run data (blocks, HR zones, running dynamics, session metrics) is stored as a JSON blob in a new `parsed_data` column on the `runs` table.

## Context

Currently the parse stage writes a `.yaml` file alongside each `.fit` file. Every downstream consumer (analyzer, API, web UI, mobile app) reads from that file. The DB tracks only a handful of scalar fields (`avg_power_w`, `avg_hr`, `workout_name`, `yaml_path`). This creates a dual-store problem: fields needed by the mobile app live only in YAML, while relationship data lives only in DB.

464 YAML files exist on disk covering all historical runs.

## Decisions

- **Storage**: JSON blob in `runs.parsed_data TEXT` column. No new tables. Cross-block querying is not a current use case; block counts are variable and normalising them caused historical complexity.
- **Migration**: Import from existing YAML files (not re-parse from FIT). YAML is authoritative for historical data; re-parsing risks divergence from what AI commentary was written against.
- **Old files**: YAML and MD files are left on disk, not deleted. `yaml_path` and `md_path` columns kept but stop being written. Column removal is a follow-up PR (tracked in project memory).
- **API key**: `yaml_data` kept unchanged. Mobile app receives identical payload, no client update needed.
- **MD files**: `.md` commentary files stop being written. Commentary is already stored in `runs.commentary`; the file write was always redundant.
- **CLI**: Updated to use run IDs rather than file paths. Old file-path forms removed.

## Architecture

### Data flow — new runs

```
FIT file
  → parse_fit_file()          [parser.py — unchanged, returns dict]
  → json.dumps()
  → db.update_parsed(..., parsed_data=...)   [DB write]
  → (no YAML file written)
```

### Data flow — analysis

```
runs.parsed_data (JSON)
  → json.loads()
  → yaml.safe_dump()          [reconstruct YAML string for LLM prompt — format unchanged]
  → LLM
  → db.update_analyzed(commentary=...)
  → (no .md file written)
```

### Data flow — API / mobile

```
runs.parsed_data (JSON)
  → json.loads()
  → response["yaml_data"]     [key name unchanged]
```

---

## Schema Changes

**Add** to `runs` table (in `SCHEMA_SQL` and a migration guard):
```sql
parsed_data TEXT   -- JSON-serialised output of build_blocks_from_fit()
```

**Keep but stop writing**: `yaml_path TEXT`, `md_path TEXT` — removed in follow-up cleanup PR.

**Update** `db.update_parsed()` signature:
```python
def update_parsed(
    self,
    run_id: int,
    yaml_path: str | None,      # pass None for new runs
    avg_power_w: float | None,
    avg_hr: int | None,
    workout_name: str | None,
    parsed_data: str | None = None,   # NEW — JSON string
) -> None:
```

**Update** `db.update_analyzed()` — make `md_path` optional (default `None`) since `.md` files are no longer written:
```python
def update_analyzed(
    self,
    run_id: int,
    md_path: str | None = None,   # was required; now optional, always pass None
    commentary: str = "",
    model_used: str = "",
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
```

---

## Module Changes

### `runcoach/parser.py`

- **Remove** `parse_and_write()` — the function that wrote YAML files.
- **Keep** `parse_fit_file(fit_path, timezone) -> dict` as the sole public function.
- `parser.py` becomes a thin wrapper around `fit_parser.build_blocks_from_fit()`.

### `runcoach/pipeline.py`

Replace `parse_and_write()` call with:
```python
summary = parse_fit_file(fit_path, timezone=config.timezone)
# apply planned_workout_title / stryd_rss enrichment inline (moved from parse_and_write)
parsed_data = json.dumps(summary)
db.update_parsed(
    run_id=run["id"],
    yaml_path=None,
    avg_power_w=summary.get("avg_power"),
    avg_hr=summary.get("avg_hr"),
    workout_name=summary.get("workout_name"),
    parsed_data=parsed_data,
)
```
Remove the post-parse YAML file read-back (currently used to extract scalar fields).

### `runcoach/analyzer.py`

`analyze_and_write(yaml_path: Path, config, ...)` → `analyze_and_write(run: dict, config, ...)`.

Internal change:
```python
# Before
yaml_content = yaml_path.read_text(encoding="utf-8")

# After
parsed = json.loads(run["parsed_data"])
yaml_content = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True)
```

Remove `.md` file write at end of function. Return value changes from `(md_path, result)` to `result` dict only. All callers (`pipeline.py`, `web/routes.py`, `web/api.py`) updated from `md_path, result = analyze_and_write(...)` to `result = analyze_and_write(...)`.

**`manual_upload` detection**: currently `analyzer.py` reads `"manual_upload: true" in yaml_content` (string search). After refactor, read `run["is_manual_upload"]` from the DB column directly — cleaner and avoids reconstructing YAML just for this flag. The `manual_upload` / `manual_upload_note` keys are no longer injected into `parsed_data`.

`build_chat_context(run, ...)` — same change: read `parsed_data` from run dict instead of `yaml_path`.

`_build_context_yaml(yaml_content, ...)` — signature unchanged; callers now pass reconstructed YAML string.

### `runcoach/web/api.py`

`format_run_for_api()`:
```python
# Before
if include_yaml and run["yaml_path"]:
    yaml_path = config.data_dir / run["yaml_path"]
    result["yaml_data"] = yaml.safe_load(open(yaml_path))

# After
if include_yaml and run.get("parsed_data"):
    result["yaml_data"] = json.loads(run["parsed_data"])
```

`analyze_run` endpoint: pass `run` dict (already fetched) to `analyze_and_write()` instead of constructing `yaml_path`.

### `runcoach/web/routes.py`

Manual upload handler: replace `parse_and_write()` call with `parse_fit_file()` + `db.update_parsed(..., parsed_data=...)`.

Re-analysis route: pass `run` dict to `analyze_and_write()`.

Run detail page: read blocks/metrics from `run["parsed_data"]` via `json.loads()` instead of reading YAML file.

### `runcoach/cli.py`

Remove:
- `parse --directory`
- `analyze --file <yaml_path>`
- `analyze --directory`

Add:
- `parse --file <fit_path>` — parses FIT, upserts DB record, stores `parsed_data`. No YAML written.
- `analyze --run-id <id>` — reads from DB, runs analysis, stores commentary.
- `analyze --date <YYYY-MM-DD>` — finds all parsed runs on that date, analyzes each.

Add:
- `runcoach-migrate` entry point — one-shot migration command (see below).

---

## Migration Command

`runcoach-migrate` (new CLI entry point, idempotent):

```
For each run in DB where yaml_path IS NOT NULL AND parsed_data IS NULL:
    - Resolve yaml_path relative to DATA_DIR
    - If file exists: yaml.safe_load() → json.dumps() → db.store_parsed_data(run_id, json_str)
    - If file missing: log WARNING, skip
Log summary: N migrated, M skipped (missing file), K already done.
```

Safe to run multiple times — skips runs that already have `parsed_data`. Should be run once after deployment before old YAML-reading code paths are removed.

New DB method: `db.store_parsed_data(run_id: int, parsed_data: str) -> None` (simple UPDATE).

---

## Test Changes

### `tests/test_parser.py`
- Remove: assertions that a `.yaml` file is written to disk.
- Keep: assertions on the dict returned by `parse_fit_file()` (structure, field values).
- Add: test that `parse_fit_file()` result is JSON-serialisable (i.e. `json.dumps()` doesn't raise).

### `tests/test_pipeline.py`
- Change: mock `parse_fit_file` (not `parse_and_write`).
- Change: assert `db.update_parsed` called with `parsed_data` kwarg containing valid JSON.
- Remove: fixture code that writes YAML files to `tmp_path`.

### `tests/test_analyzer.py`
- Change: construct a run dict with `parsed_data=json.dumps({...})` instead of writing a YAML file.
- Change: pass run dict to `analyze_and_write()`.
- Add: assert no `.md` file is written.
- Change: assert return value is a dict (not a `(Path, dict)` tuple).

### `tests/test_context.py`
- Change: set `parsed_data` JSON on run records via `db.update_parsed()` instead of writing YAML files.
- Remove: all `yaml_path.write_text(...)` fixture code.

### `tests/test_web.py`
- Change: set `parsed_data` on run records in DB fixtures instead of writing YAML files.
- Keep: `yaml_data` key assertions in API response — same key, now sourced from DB.

### `tests/test_api.py`
- Change: set `parsed_data` on run records in DB fixtures.
- Keep: assert `yaml_data` present in `GET /api/v1/runs/:id` response.
- Add: assert `yaml_data` is `None` when `parsed_data` is `NULL`.

---

## Rollout Order

1. Add `parsed_data` column (schema + migration guard) — DB backward-compatible, no behaviour change.
2. Update `update_parsed()` to accept and store `parsed_data`.
3. Update parse callers (`pipeline.py`, `web/routes.py`) to store JSON — new runs get `parsed_data` from this point.
4. Implement and run `runcoach-migrate` — backfills historical runs.
5. Update `analyzer.py` and `build_chat_context()` to read from `parsed_data`.
6. Update `format_run_for_api()` to serve from `parsed_data`.
7. Update run detail page in `web/routes.py`.
8. Update CLI.
9. Update all tests throughout.

Steps 1–4 are the data layer; steps 5–8 are consumers. Each step is independently deployable without breaking the previous state.

---

## What Does Not Change

- `fit_parser.py` — untouched. `build_blocks_from_fit()` is the parser; this refactor is purely about where the output goes.
- Mobile app — no changes. `yaml_data` key and structure identical.
- `.fit` files — stay on disk, `fit_path` column unchanged.
- LLM prompt format — YAML text reconstructed from JSON; identical to what the model currently receives.
- Web push notifications, Strava integration, Stryd sync — unaffected.
