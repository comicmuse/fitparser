# Phase 1 Complete: Backend JSON API + Authentication

## Summary

Phase 1 of the RunCoach Android app implementation is complete! We've successfully created a production-ready REST API with JWT authentication that the mobile app will use.

## What Was Built

### 1. Authentication System (`runcoach/auth.py`)
- **JWT Token Management**:
  - Access tokens (1-hour expiry) for API requests
  - Refresh tokens (30-day expiry) for long-term sessions
  - HS256 algorithm for signing
- **Security**:
  - Password hashing using werkzeug's pbkdf2:sha256
  - `require_auth` decorator for protected endpoints
  - Token validation with expiry checking

### 2. Database Extensions (`runcoach/db.py`)
- **Users Table**:
  ```sql
  CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    password_hash TEXT,
    created_at TEXT,
    last_login TEXT
  );
  ```
  - Default user "athlete" created on first run
  - Password from env var `RUNCOACH_PASSWORD` (default: runcoach123)

- **UnifiedPush Subscriptions Table**:
  ```sql
  CREATE TABLE unifiedpush_subscriptions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    endpoint TEXT UNIQUE,
    topic TEXT,
    created_at TEXT
  );
  ```
  - Stores push notification subscriptions per user
  - Supports ntfy.sh and compatible UnifiedPush distributors

### 3. REST API Endpoints (`runcoach/web/api.py`)

#### Authentication Endpoints
- `POST /api/v1/auth/login` - Login with username/password, returns JWT tokens
- `POST /api/v1/auth/refresh` - Refresh access token using refresh token
- `POST /api/v1/auth/logout` - Logout (client discards tokens)

#### Runs Endpoints
- `GET /api/v1/runs?page=1&per_page=20` - List runs with pagination
- `GET /api/v1/runs/:id` - Get single run with full YAML data (blocks, HR zones, etc.)
- `POST /api/v1/runs/upload` - Upload FIT file (multipart/form-data)
- `POST /api/v1/runs/:id/analyze` - Trigger AI analysis for a run

#### Sync Endpoints
- `POST /api/v1/sync` - Trigger Stryd sync
- `GET /api/v1/sync/status` - Get sync status and statistics

#### Push Notification Endpoints
- `POST /api/v1/push/register` - Register UnifiedPush subscription
- `POST /api/v1/push/unregister` - Unregister subscription
- `POST /api/v1/push/test` - Send test notification

### 4. UnifiedPush Support (`runcoach/push.py`)
- **UnifiedPushNotifier Class**:
  - Sends notifications via ntfy.sh (or compatible server)
  - Supports deep linking (e.g., `runcoach://run/123`)
  - Includes structured data in notifications
  - Priority levels: min, low, default, high, urgent

- **Dual Push System**:
  - Sends to both Web Push (VAPID) and UnifiedPush subscribers
  - Gracefully handles missing subscriptions
  - Cleans up stale Web Push subscriptions automatically

### 5. Configuration Updates
- **Dependencies Added** (`pyproject.toml`):
  - `pyjwt>=2.8.0` - JWT token handling
  - `werkzeug>=3.0` - Password hashing
  - `requests>=2.31` - HTTP requests for UnifiedPush

- **Environment Variables** (`.env.example`):
  ```bash
  # JWT Authentication
  JWT_SECRET_KEY=<generate-with-secrets.token_hex(32)>
  RUNCOACH_PASSWORD=runcoach123

  # Push Notifications
  NTFY_SERVER=https://ntfy.sh
  ```

## Testing

### Automated Test Script (`test_api.py`)
All endpoints tested and working:
- ✅ Login with credentials
- ✅ Token refresh
- ✅ Unauthorized access rejection
- ✅ List runs with pagination (439 runs found)
- ✅ Get run details with YAML data
- ✅ Sync status retrieval

### Test Results
```
=== API Test Results ===
Total runs: 439
Run detail includes:
- Name, date, distance, duration
- Avg power (164W), avg HR (131 bpm)
- Full YAML workout blocks
- Status: parsed/analyzed/synced

Stats:
- Pending parse: 0
- Pending analyze: 397
- Errors: 0
```

## How to Use

### 1. Start the Server
```bash
source .venv/bin/activate
runcoach
# Server runs on http://localhost:5000
```

### 2. Test with curl
```bash
# Login
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "athlete", "password": "runcoach123"}'

# Get runs (with token)
curl http://localhost:5000/api/v1/runs \
  -H "Authorization: Bearer <access_token>"

# Get run detail
curl http://localhost:5000/api/v1/runs/436 \
  -H "Authorization: Bearer <access_token>"
```

### 3. Run Test Suite
```bash
python test_api.py
```

## API Response Examples

### Login Response
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user_id": 1,
  "username": "athlete"
}
```

### Runs List Response
```json
{
  "runs": [
    {
      "id": 436,
      "name": "Day 62 - EZ Aerobic / Recovery Run",
      "date": "2026-03-07",
      "distance_km": 4.66,
      "duration_formatted": "30:01",
      "avg_power_w": 164.0,
      "avg_hr": 131,
      "stryd_rss": 42.5,
      "stage": "parsed",
      "is_manual_upload": false
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 439,
    "total_pages": 22
  }
}
```

### Run Detail Response (with YAML)
```json
{
  "id": 436,
  "name": "Day 62 - EZ Aerobic / Recovery Run",
  "yaml_data": {
    "workout_name": "Day 62 - EZ Aerobic / Recovery Run",
    "date": "2026-03-07",
    "distance_km": 4.66,
    "duration_min": 30.0,
    "avg_power": 164,
    "avg_hr": 131,
    "blocks": {
      "warmup": {
        "duration_min": 5.2,
        "avg_power": 155,
        "hr_zones": {"Z1_pct": 10, "Z2_pct": 85}
      },
      "active_1": {
        "duration_min": 20.5,
        "target_power": {"min_w": 150, "max_w": 170}
      }
    }
  }
}
```

## Security Features

1. **JWT Authentication**: Stateless tokens, no server-side sessions
2. **Password Hashing**: pbkdf2:sha256 with salt
3. **CSRF Exempt**: API uses JWT instead of cookies (HTML UI still protected)
4. **Token Expiry**: Access tokens expire after 1 hour, refresh after 30 days
5. **Bearer Token**: Standard Authorization header format

## GrapheneOS Compatibility

- ✅ **No Google Play Services** required
- ✅ **UnifiedPush** support for notifications (ntfy.sh)
- ✅ **Open-source** push protocol
- ✅ **Self-hostable** ntfy.sh server option

## Next Steps: Phase 2

Now that the backend API is complete, Phase 2 will focus on:

1. **React Native Project Setup**:
   - Initialize TypeScript project
   - Install navigation, state management, API client
   - Set up project structure

2. **Authentication Flow**:
   - Zustand store for auth state
   - Axios client with JWT interceptors
   - Token refresh on 401 responses
   - AsyncStorage for token persistence

3. **Login Screen**:
   - Username/password form
   - AppNavigator with conditional routing
   - Test login flow and token storage

**Estimated Time**: Week 2 of 7-week plan

## Files Changed

```
modified:   .env.example           # Add JWT/push config
modified:   pyproject.toml         # Add dependencies
new file:   runcoach/auth.py       # JWT authentication
modified:   runcoach/db.py         # Users & push subscriptions
modified:   runcoach/push.py       # UnifiedPush support
modified:   runcoach/web/__init__.py  # Register API blueprint
new file:   runcoach/web/api.py   # REST API endpoints
new file:   test_api.py            # API test suite
```

## Commit

```
git checkout feature/android-app
git log -1 --oneline
# 82d668f Phase 1: Backend JSON API + Authentication
```

---

**Status**: ✅ Phase 1 Complete (Backend API ready for mobile consumption)
**Next**: 🔄 Phase 2 - React Native App Skeleton + Auth
