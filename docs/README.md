# RunCoach Backend Documentation

This directory contains documentation for the RunCoach backend API.

## API Documentation

- **[API_REFERENCE.md](API_REFERENCE.md)** - Complete API endpoint reference
  - Authentication endpoints
  - Run endpoints (list, detail, upload, analyze)
  - Sync endpoints
  - Push notification endpoints

## Development Guides

- [PHASE1_COMPLETE.md](PHASE1_COMPLETE.md) - Phase 1: Mobile API implementation
- [agents.md](agents.md) - Claude agent configuration

## CI/CD

- [CI_IMPLEMENTATION.md](CI_IMPLEMENTATION.md) - Continuous integration setup

## Architecture

The backend is built with:

- **Flask** web framework
- **SQLite** database with WAL mode
- **JWT** authentication
- **OpenAI API** for AI analysis
- **Stryd API** for activity sync
- **Expo Push Notifications** for mobile alerts
- **UnifiedPush** support for privacy-focused notifications

See [../README.md](../README.md) and [../CLAUDE.md](../CLAUDE.md) for main project documentation.

## Related Projects

- [RunCoach Mobile](https://github.com/yourusername/runcoach-mobile) - React Native mobile app
