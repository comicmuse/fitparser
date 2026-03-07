# RunCoach Mobile API Reference

Base URL: `http://localhost:5000/api/v1` (or your deployment URL)

## Authentication

### Login
```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "athlete",
  "password": "runcoach123"
}

# Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user_id": 1,
  "username": "athlete"
}
```

### Refresh Token
```bash
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ..."
}

# Response 200
{
  "access_token": "eyJ..."
}
```

### Logout
```bash
POST /api/v1/auth/logout
Authorization: Bearer <access_token>

# Response 200
{
  "message": "Logged out successfully"
}
```

## Runs

All run endpoints require `Authorization: Bearer <access_token>` header.

### List Runs
```bash
GET /api/v1/runs?page=1&per_page=20
Authorization: Bearer <access_token>

# Response 200
{
  "runs": [
    {
      "id": 436,
      "name": "Day 62 - EZ Aerobic / Recovery Run",
      "date": "2026-03-07",
      "distance_km": 4.66,
      "distance_m": 4657.0,
      "duration_s": 1801,
      "duration_formatted": "30:01",
      "avg_power_w": 164.0,
      "avg_hr": 131,
      "stryd_rss": 42.5,
      "workout_name": "Day 62 - EZ Aerobic / Recovery Run",
      "stage": "parsed",
      "is_manual_upload": false,
      "commentary": null,
      "analyzed_at": null,
      "model_used": null,
      "error_message": null
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

### Get Run Detail
```bash
GET /api/v1/runs/:id
Authorization: Bearer <access_token>

# Response 200
{
  "id": 436,
  "name": "Day 62 - EZ Aerobic / Recovery Run",
  "date": "2026-03-07",
  "distance_km": 4.66,
  "duration_formatted": "30:01",
  "avg_power_w": 164.0,
  "avg_hr": 131,
  "stage": "parsed",
  "yaml_data": {
    "workout_name": "Day 62 - EZ Aerobic / Recovery Run",
    "date": "2026-03-07",
    "distance_km": 4.66,
    "duration_min": 30.0,
    "avg_power": 164,
    "avg_hr": 131,
    "critical_power": 202,
    "blocks": {
      "warmup": {
        "duration_min": 5.2,
        "distance_km": 0.85,
        "avg_power": 155,
        "avg_hr": 125,
        "hr_zones": {
          "Z1_pct": 10,
          "Z2_pct": 85,
          "Z3_pct": 5
        }
      },
      "active_1": {
        "duration_min": 20.5,
        "distance_km": 3.2,
        "avg_power": 168,
        "avg_hr": 133,
        "target_power": {
          "min_w": 150,
          "max_w": 170
        },
        "pct_time_in_range": 87.3
      }
    },
    "session_hr_zones": {
      "Z1_pct": 5,
      "Z2_pct": 75,
      "Z3_pct": 15,
      "Z4_pct": 5
    }
  }
}
```

### Upload FIT File
```bash
POST /api/v1/runs/upload
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file=@/path/to/activity.fit

# Response 201
{
  "run_id": 440,
  "message": "File uploaded successfully. Parsing and analysis will begin shortly."
}
```

### Trigger Analysis
```bash
POST /api/v1/runs/:id/analyze
Authorization: Bearer <access_token>

# Response 202
{
  "message": "Analysis started"
}

# Error 400 (wrong stage)
{
  "error": "Run must be in 'parsed' stage (currently 'synced')"
}
```

## Sync

### Trigger Sync
```bash
POST /api/v1/sync
Authorization: Bearer <access_token>

# Response 202
{
  "message": "Sync started"
}

# Error 409 (already running)
{
  "error": "Sync already in progress"
}
```

### Get Sync Status
```bash
GET /api/v1/sync/status
Authorization: Bearer <access_token>

# Response 200
{
  "last_sync": {
    "id": 42,
    "started_at": "2026-03-07T17:09:44.172142+00:00",
    "finished_at": "2026-03-07T17:10:15.523842+00:00",
    "status": "success",
    "activities_found": 437,
    "activities_new": 4,
    "error_message": null
  },
  "stats": {
    "total_runs": 439,
    "pending_parse": 0,
    "pending_analyze": 397,
    "errors": 0
  }
}
```

## Push Notifications

### Register UnifiedPush Subscription
```bash
POST /api/v1/push/register
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "endpoint": "https://ntfy.sh/up-abc123def456",
  "topic": "up-abc123def456"
}

# Response 201
{
  "message": "Push subscription registered"
}
```

### Unregister Subscription
```bash
POST /api/v1/push/unregister
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "endpoint": "https://ntfy.sh/up-abc123def456"
}

# Response 200
{
  "message": "Push subscription removed"
}
```

### Test Notification
```bash
POST /api/v1/push/test
Authorization: Bearer <access_token>

# Response 200
{
  "message": "Test notification sent"
}

# Error 404 (no subscriptions)
{
  "error": "No push subscriptions found"
}
```

## Error Responses

### 401 Unauthorized
```json
{
  "error": "Missing or invalid authorization header"
}
```

```json
{
  "error": "Invalid or expired token"
}
```

### 400 Bad Request
```json
{
  "error": "Missing username or password"
}
```

### 404 Not Found
```json
{
  "error": "Run not found"
}
```

### 409 Conflict
```json
{
  "error": "Sync already in progress"
}
```

## UnifiedPush Notification Format

When analysis completes, the following notification is sent:

```json
{
  "title": "Analysis Ready",
  "message": "Your run \"Morning Tempo\" has been analyzed",
  "data": {
    "type": "analysis_complete",
    "run_id": 436,
    "run_name": "Morning Tempo"
  }
}
```

**Deep Link**: `runcoach://run/436`

## Authentication Flow

1. **Login**: POST to `/auth/login`, receive access_token and refresh_token
2. **Store tokens**: Save to secure storage (AsyncStorage, Keychain, etc.)
3. **API requests**: Include `Authorization: Bearer <access_token>` header
4. **Token expiry**: Access token expires after 1 hour
5. **Auto-refresh**: On 401 response, use refresh_token to get new access_token
6. **Logout**: Delete stored tokens locally

## Rate Limiting

Currently no rate limiting implemented. Consider adding in production:
- 100 requests per minute per user
- 10 login attempts per hour
- 5 sync triggers per hour

## CORS

API endpoints accept requests from any origin in development.
Configure CORS properly for production deployment.

## Testing

Run the test suite:
```bash
python test_api.py
```

Test individual endpoints with curl:
```bash
# Store token in variable
TOKEN=$(curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"athlete","password":"runcoach123"}' \
  | jq -r '.access_token')

# Use token for requests
curl http://localhost:5000/api/v1/runs \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.runs[0]'
```

## Next: React Native Client

See Phase 2 documentation for React Native implementation:
- Axios client with interceptors
- Token refresh logic
- AsyncStorage persistence
- Zustand state management
