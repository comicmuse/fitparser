# Push Notifications Design

**Feature:** Android push notifications when a new run analysis is ready, with a tap that deep-links to the run detail screen.

---

## Overview

When the RunCoach server finishes analysing a run — whether via the automated pipeline (Strava webhook → sync → analyse) or manual on-demand analysis from the app — it sends an FCM push notification to all registered devices for that user. Tapping the notification opens the RunCoach app directly at the run detail screen.

The feature is fully opt-in on the server: if `FCM_SERVICE_ACCOUNT_PATH` is not configured, the system behaves exactly as before.

---

## Delivery Mechanism

**Firebase Cloud Messaging (FCM)** via the Firebase Admin Python SDK on the server, and `firebase_core` + `firebase_messaging` on the Flutter client.

- `google-services.json` is included in the Android app build (not secret; not committed to git)
- Firebase Admin service account JSON lives on the server only (secret; never in the app or git)
- Any Google account can own the Firebase project; no link to Google Play is required until the app is published (at which point Play App Signing's SHA-1 must be registered in Firebase)

---

## Server Side

### New: `device_tokens` table

```sql
CREATE TABLE device_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL DEFAULT 'android',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX idx_device_tokens_user_id ON device_tokens(user_id);
```

Token uniqueness is enforced at the DB level. Upserting on conflict updates `user_id`, handling reinstalls where the same token is re-registered.

### New: `runcoach/notifications.py`

Single public function:

```
send_analysis_notification(run_id, run_name, user_id, db, config) -> int
```

Behaviour:
1. Returns 0 immediately if `config.fcm_service_account_path` is empty (opt-in no-op)
2. Fetches all device tokens for the user
3. Initialises Firebase Admin app (idempotent singleton)
4. Sends one FCM message per token:
   - `notification.title`: `"New Analysis Ready"`
   - `notification.body`: `"Your coach has analysed: {run_name}"`
   - `data`: `{"run_id": str(run_id), "type": "analysis_ready"}`
5. On `UnregisteredError`: deletes the stale token, continues
6. On any other FCM error: logs warning, continues — notification failure never blocks or fails the analysis write
7. Returns count of messages successfully sent

### Modified: `runcoach/config.py`

New field: `fcm_service_account_path: str = ""`, populated from env var `FCM_SERVICE_ACCOUNT_PATH`.

### Modified: `pyproject.toml`

New optional extra:
```toml
fcm = ["firebase-admin>=6.0"]
```

### New: API endpoints

`POST /api/v1/device-tokens` (authenticated)
- Body: `{"token": "...", "platform": "android"}`
- Calls `db.upsert_device_token(user_id, token, platform)`
- Returns `200 {"message": "Device token registered"}`
- Returns `400` if token is missing or empty

`DELETE /api/v1/device-tokens` (authenticated)
- Body: `{"token": "..."}`
- Calls `db.delete_device_token(token)`
- Returns `200 {"message": "Device token removed"}`
- Returns `400` if token is missing

### Modified: `runcoach/pipeline.py`

After the `db.update_analyzed()` call in the analysis loop, inline call:

```python
try:
    from runcoach.notifications import send_analysis_notification
    send_analysis_notification(run["id"], run.get("name", "Run"), user_id, db, config)
except Exception:
    log.warning("Push notification failed for run %s (non-fatal)", run["id"])
```

### Modified: `runcoach/web/api.py` — `analyze_run` endpoint

Same inline call added inside the `analyze_task` background thread, after `db.update_analyzed()`. Because `request.user_id` is unavailable inside the thread (request context is gone), `user_id` must be captured into a local variable in the route handler before the thread is created — the same pattern already used for `run_id`.

---

## Mobile Side

### Prerequisites (manual)

1. Create Firebase project; add Android app with package ID `com.runcoach.mobile`
2. Download `google-services.json` → `mobile/android/app/google-services.json` (gitignored)
3. Download service account JSON → server only

### Dependencies

`mobile/pubspec.yaml`:
```yaml
firebase_core: ^3.13.1
firebase_messaging: ^15.2.5
```

### Android Gradle changes

- `settings.gradle.kts`: add `id("com.google.gms.google-services") version "4.4.2" apply false` to plugins block
- `app/build.gradle.kts`: add `id("com.google.gms.google-services")` to plugins block
- `AndroidManifest.xml`: add `<uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>`

### New: `mobile/lib/services/notification_service.dart`

Plain Dart class `NotificationService(ApiService api)`.

**`initialize()` sequence:**
1. Register top-level `_firebaseBackgroundMessageHandler` with FCM
2. Request notification permission (`alert`, `badge`, `sound`)
3. If granted: get current FCM token, call `api.registerDeviceToken(token)`
4. Listen to `onTokenRefresh` → re-register new token automatically
5. Set up message handlers (see below)

**Message handlers:**
- `onMessage` (foreground): show in-app banner
- `onMessageOpenedApp` (background tap): call `_handleTap(message)`
- `getInitialMessage()` (terminated tap): call `_handleTap(message)` if non-null

**`_handleTap(message)`**: parses `message.data['run_id']` as int, calls `onNotificationTap(runId)` callback.

### Foreground banner widget

A custom overlay widget in **burnt orange** (`#C45C1A`) that slides down from the top of the screen when `onMessage` fires.

Layout: running emoji icon | title "New Analysis Ready" + subtitle "{run name} · Tap to view" | dismiss (×) button.

Behaviour:
- Auto-dismisses after 4 seconds
- Tapping anywhere on it navigates to `/home/run/{run_id}` and dismisses
- Tapping × dismisses without navigating

### Modified: `mobile/lib/services/api_service.dart`

```dart
Future<void> registerDeviceToken(String token) async {
  await _dio.post('/device-tokens', data: {'token': token, 'platform': 'android'});
}

Future<void> deleteDeviceToken(String token) async {
  await _dio.delete('/device-tokens', data: {'token': token});
}
```

### Modified: `mobile/lib/providers/auth_provider.dart`

```dart
final notificationServiceProvider = Provider<NotificationService>((ref) {
  return NotificationService(ref.read(apiServiceProvider));
});
```

`AuthNotifier` gets `NotificationService` injected alongside `ApiService`, and calls `_notifService.deregister()` during logout:

```dart
class AuthNotifier extends StateNotifier<AuthStatus> {
  final SecureStorageService _storage;
  final ApiService _api;
  final NotificationService _notifService;

  AuthNotifier(this._storage, this._api, this._notifService) : super(AuthStatus.unknown) {
    _checkAuth();
  }

  Future<void> logout() async {
    await _notifService.deregister();  // deregister FCM token before clearing auth
    await _api.logout();
    await _storage.clearTokens();
    state = AuthStatus.unauthenticated;
  }
  // ... rest unchanged
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthStatus>((ref) {
  final api = ref.read(apiServiceProvider);
  final notif = ref.read(notificationServiceProvider);
  final notifier = AuthNotifier(ref.read(secureStorageProvider), api, notif);
  api.onAuthFailed = notifier.revalidate;
  return notifier;
});
```

`NotificationService` gains a `deregister()` method that fetches the current FCM token and calls `api.deleteDeviceToken()`. If `getToken()` returns null or throws, logout proceeds silently.

### Modified: `mobile/lib/main.dart`

```dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  runApp(const ProviderScope(child: RunCoachApp()));
}
```

### Modified: `mobile/lib/app.dart`

`RunCoachApp` becomes `ConsumerStatefulWidget`. In `initState()`, via `addPostFrameCallback`:

```dart
final notifService = ref.read(notificationServiceProvider);
notifService.onNotificationTap = (runId) {
  _rootNavKey.currentContext?.go('/home/run/$runId');
};
notifService.initialize();
```

### Logout

`AuthNotifier.logout()` calls `notifService.deregister()` before clearing stored auth tokens. `NotificationService.deregister()` fetches the current FCM token via `FirebaseMessaging.instance.getToken()` and calls `api.deleteDeviceToken(token)`. If token retrieval fails, logout proceeds silently.

---

## Error Handling Summary

| Scenario | Behaviour |
|---|---|
| FCM not configured | `send_analysis_notification` no-ops, returns 0 |
| FCM send fails (non-stale) | Logged as warning, swallowed — analysis unaffected |
| Stale token (`UnregisteredError`) | Token deleted from DB, send continues for remaining tokens |
| Notification permission denied | Token registration skipped silently; app works normally |
| Token refresh | `onTokenRefresh` re-registers automatically via upsert |
| Logout | Token deregistered on server before local auth tokens cleared |
| Reinstall | New token upserted; old tokens cleaned lazily on next `UnregisteredError` |

---

## What Is Not In Scope

- iOS notifications (no Apple Developer account or APNs configured)
- Notification history / inbox in the app
- Per-run-type notification preferences
- Notifying on analysis failure
