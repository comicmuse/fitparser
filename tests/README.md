# RunCoach Tests

This directory contains unit tests for the RunCoach application.

## Running Tests

```bash
# From project root, activate virtual environment
source .venv/bin/activate

# Install test dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=runcoach --cov-report=html
```

## Test Files

- **test_context.py** - Training context calculations (RSS, ATL/CTL/RSB), workout classification
- **test_db.py** - Database operations (CRUD for runs, planned workouts, sync logs, push subscriptions)
- **test_analyzer.py** - AI analysis with mocked OpenAI client
- **test_fit_parser.py** - FIT file parsing and block segmentation
- **test_web.py** - Flask web UI routes and pages
- **conftest.py** - Shared pytest fixtures

## Coverage

Current test coverage: **69%** overall (109 tests passing)

Core modules:
- `analyzer.py` - 96%
- `db.py` - 96%
- `context.py` - 92%
- `scheduler.py` - 88%
- `fit_parser.py` - 83%
- `web/__init__.py` - 81%
- `config.py` - 74%

Partially tested:
- `web/routes.py` - 49% (basic route tests)
- `pipeline.py` - 47% (orchestration logic)
- `parser.py` - 42% (FIT to YAML wrapper)

Untested modules:
- `cli.py` - 0% (CLI entry points)
- `sync.py` - 29% (Stryd API sync - requires mocking)
- `push.py` - 14% (Web Push notifications)

## Fixtures

Located in `conftest.py`:

- `sample_fit_file` - Path to a small sample FIT file from `data/activities/`
- `sample_yaml_file` - Path to a parsed YAML file
- `temp_db` - Temporary SQLite database for testing
- `test_config` - Test configuration with dummy values
- `mock_openai_client` - Mocked OpenAI client with predictable responses
- `app` - Flask test app with temporary database
- `client` - Flask test client for making requests

## Mocking

External services are mocked to avoid costs and rate limits:

- **OpenAI API** - Returns "Test commentary" with 100 prompt tokens, 50 completion tokens
- **Stryd API** - Not currently tested (would need mocking for sync tests)

## Test Data

Tests use real FIT and YAML files from `data/activities/2026/01/` for integration testing.
Small runs like `20260129_day_25_-_testing` are preferred for faster test execution.

## Web Tests

The web tests verify that:
- ✅ Flask app starts successfully
- ✅ All main routes load without errors (/, /workouts, /run/:id, /status)
- ✅ API endpoints require correct HTTP methods
- ✅ Calendar view renders with planned workouts and actual runs
- ✅ Markdown commentary is properly rendered and sanitized
- ✅ Error handling works for nonexistent runs
- ✅ Pagination works for workout lists
