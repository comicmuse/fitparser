# FCM Auth-Gated Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure FCM device token registration only happens when the app has valid auth, eliminating the spurious 401 on app startup when the session has expired.

**Architecture:** Split `NotificationService.initialize()` into two concerns: Firebase/OS setup (auth-independent, called on app start) and server registration (auth-gated, called only when auth state resolves to authenticated). `AuthNotifier` drives server registration — on `_checkAuth()` success and after `login()`. `revalidate()` (called by the API layer on 401s) is split from `_checkAuth()` so it does not trigger spurious FCM re-registration on every API error.

**Tech Stack:** Flutter, Riverpod, firebase_messaging, flutter_secure_storage

---

## Files

- Modify: `mobile/lib/services/notification_service.dart` — rename `registerCurrentToken()` → `registerWithServer()`, remove its call from `initialize()`
- Modify: `mobile/lib/providers/auth_provider.dart` — call `registerWithServer()` from `_checkAuth()` (authenticated branch); split `revalidate()` so it updates state without triggering registration; update `login()`
- Create: `mobile/test/providers/auth_provider_test.dart` — tests for the auth-gated dispatch logic
- No change: `mobile/lib/app.dart` — still calls `notifService.initialize()` on first frame; that is correct and unchanged

---

## Ordering note

`_checkAuth()` is called from the `AuthNotifier` constructor, which runs when Riverpod first reads `authProvider` (during `build()`). `notifService.initialize()` is scheduled via `addPostFrameCallback` in `initState`, so it runs after the first frame — potentially after `_checkAuth()` completes and calls `registerWithServer()`.

This is safe in practice:
- **Fresh install** — no stored token → `_checkAuth()` returns unauthenticated → `registerWithServer()` is never called → user logs in → `initialize()` has long since run by then.
- **Returning user (valid session)** — `_checkAuth()` resolves authenticated and calls `registerWithServer()` → `getToken()` is called. Firebase caches the permission grant from the previous session, so `getToken()` returns the current token without needing `requestPermission()` to be called first. No race condition.
- **Returning user (expired JWT)** — `_checkAuth()` finds a token in storage → calls `registerWithServer()` → API returns 401 → silently swallowed. The app redirects to login; after login `registerWithServer()` is called again and succeeds.

---

### Task 1: Refactor `NotificationService`

**Files:**
- Modify: `mobile/lib/services/notification_service.dart`

Remove `await registerCurrentToken()` from `initialize()`. The `onTokenRefresh` listener stays in `initialize()` — it calls `_registerToken` directly. If the token rotates while the user is logged out the call silently 401s; the next login or startup-when-authenticated re-registers. Moving the listener to `registerWithServer()` would risk duplicate listeners on each call. Rename the public method to `registerWithServer()`.

- [ ] **Step 1: Edit `notification_service.dart`**

Replace the entire file:

```dart
import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'api_service.dart';

/// Top-level handler for background FCM messages. Must be a top-level function.
@pragma('vm:entry-point')
Future<void> _firebaseBackgroundMessageHandler(RemoteMessage message) async {
  // No action needed — navigation on tap is handled by onMessageOpenedApp.
}

class NotificationService {
  final ApiService _api;
  final List<StreamSubscription<dynamic>> _subscriptions = [];

  /// Called when the user taps a notification (background or terminated).
  void Function(int runId)? onNotificationTap;

  /// Called when a notification arrives while the app is in the foreground.
  void Function(int runId, String runName)? onForegroundMessage;

  NotificationService(this._api);

  /// Sets up Firebase handlers and requests OS notification permission.
  /// Does NOT register the token with the server — call [registerWithServer]
  /// once auth is confirmed.
  Future<void> initialize() async {
    FirebaseMessaging.onBackgroundMessage(_firebaseBackgroundMessageHandler);

    final settings = await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    if (settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional) {
      _subscriptions.add(
        FirebaseMessaging.instance.onTokenRefresh.listen(_registerToken),
      );
    }

    _setupHandlers();
  }

  /// Registers the current FCM token with the server. Call this after auth
  /// is confirmed (on startup with a valid session, or after login).
  /// Intentionally fire-and-forget — a 401 is silently swallowed; the next
  /// successful login will retry.
  Future<void> registerWithServer() async {
    final token = await FirebaseMessaging.instance.getToken();
    if (token != null) await _registerToken(token);
  }

  /// Deregister the current FCM token on logout. Swallows all errors so
  /// logout always completes even if FCM is unavailable.
  Future<void> deregister() async {
    try {
      final token = await FirebaseMessaging.instance.getToken();
      if (token != null) await _api.deleteDeviceToken(token);
    } catch (e) {}
  }

  Future<void> _registerToken(String token) async {
    try {
      await _api.registerDeviceToken(token);
    } catch (e) {}
  }

  void _setupHandlers() {
    _subscriptions.add(
      FirebaseMessaging.onMessage.listen((message) {
        final runIdStr = message.data['run_id'];
        if (runIdStr == null) return;
        final runId = int.tryParse(runIdStr);
        if (runId == null) return;
        final runName = message.notification?.body ?? 'New run';
        onForegroundMessage?.call(runId, runName);
      }),
    );

    _subscriptions.add(FirebaseMessaging.onMessageOpenedApp.listen(_handleTap));

    FirebaseMessaging.instance.getInitialMessage().then((message) {
      if (message != null) _handleTap(message);
    });
  }

  void _handleTap(RemoteMessage message) {
    final runIdStr = message.data['run_id'];
    if (runIdStr == null) return;
    final runId = int.tryParse(runIdStr);
    if (runId != null) onNotificationTap?.call(runId);
  }

  void dispose() {
    for (final sub in _subscriptions) {
      sub.cancel();
    }
    _subscriptions.clear();
  }
}
```

- [ ] **Step 2: Verify formatting**

```bash
dart format --output=none --set-exit-if-changed .
```
Expected: `Formatted N files (0 changed)`

- [ ] **Step 3: Commit**

```bash
git add mobile/lib/services/notification_service.dart
git commit -m "refactor: remove server call from NotificationService.initialize()"
```

---

### Task 2: Update `AuthNotifier` to drive server registration

**Files:**
- Modify: `mobile/lib/providers/auth_provider.dart`
- Create: `mobile/test/providers/auth_provider_test.dart`

Three changes to `auth_provider.dart`:
1. `_checkAuth()` calls `_notifService.registerWithServer()` (unawaited — intentional) when a token is found.
2. `revalidate()` — currently delegates to `_checkAuth()`. After the change, `_checkAuth()` would trigger FCM registration on every API 401 that calls `revalidate()`. Split `revalidate()` to update state only, without registration.
3. `login()` — replace old `registerCurrentToken()` call with `registerWithServer()`.

- [ ] **Step 1: Write the failing tests**

Create `mobile/test/providers/auth_provider_test.dart`:

```dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/providers/auth_provider.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/notification_service.dart';
import 'package:runcoach/services/secure_storage_service.dart';

class _RecordingNotifService extends NotificationService {
  _RecordingNotifService() : super(_NoOpApi());
  int registerCalls = 0;
  int deregisterCalls = 0;

  @override
  Future<void> registerWithServer() async => registerCalls++;

  @override
  Future<void> deregister() async => deregisterCalls++;
}

class _NoOpApi extends ApiService {
  _NoOpApi() : super(SecureStorageService());

  @override
  Future<Map<String, String>> login(String u, String p) async =>
      {'access_token': 'at', 'refresh_token': 'rt'};

  @override
  Future<void> logout() async {}
}

AuthNotifier _makeNotifier({
  required Map<String, String> storageValues,
  required _RecordingNotifService notif,
}) {
  FlutterSecureStorage.setMockInitialValues(storageValues);
  final storage = SecureStorageService();
  final api = _NoOpApi();
  return AuthNotifier(storage, api, notif);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AuthNotifier', () {
    test('_checkAuth calls registerWithServer when a stored token exists',
        () async {
      final notif = _RecordingNotifService();
      final notifier = _makeNotifier(
        storageValues: {'access_token': 'stored'},
        notif: notif,
      );
      await pumpEventQueue();

      expect(notifier.state, AuthStatus.authenticated);
      expect(notif.registerCalls, 1);
    });

    test('_checkAuth does NOT call registerWithServer when no token stored',
        () async {
      final notif = _RecordingNotifService();
      final notifier = _makeNotifier(storageValues: {}, notif: notif);
      await pumpEventQueue();

      expect(notifier.state, AuthStatus.unauthenticated);
      expect(notif.registerCalls, 0);
    });

    test('login calls registerWithServer after successful auth', () async {
      final notif = _RecordingNotifService();
      final notifier = _makeNotifier(storageValues: {}, notif: notif);
      await pumpEventQueue(); // let _checkAuth settle (unauthenticated)

      await notifier.login('user', 'pass');

      expect(notifier.state, AuthStatus.authenticated);
      expect(notif.registerCalls, 1);
    });

    test('revalidate does NOT call registerWithServer', () async {
      final notif = _RecordingNotifService();
      final notifier = _makeNotifier(
        storageValues: {'access_token': 'stored'},
        notif: notif,
      );
      await pumpEventQueue(); // _checkAuth fires once (registerCalls = 1)

      notifier.revalidate();
      await pumpEventQueue();

      // revalidate() must not add a second registration call
      expect(notif.registerCalls, 1);
    });
  });
}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
flutter test test/providers/auth_provider_test.dart
```

Expected: compilation errors or assertion failures. Task 1 must be complete first (provides `registerWithServer()`). With Task 1 done, the tests will compile but assertions will fail because `AuthNotifier` hasn't been updated yet.

- [ ] **Step 3: Update `auth_provider.dart`**

Replace `_checkAuth()`, `revalidate()`, and `login()`:

```dart
Future<void> _checkAuth() async {
  final token = await _storage.getAccessToken();
  if (token != null) {
    state = AuthStatus.authenticated;
    // Intentionally unawaited — 401s are silently swallowed; login() retries.
    // ignore: unawaited_futures
    _notifService.registerWithServer();
  } else {
    state = AuthStatus.unauthenticated;
  }
}

// Called by ApiService on 401 — re-reads auth state from storage but does NOT
// trigger FCM re-registration to avoid spurious POSTs on every API error.
void revalidate() {
  _storage.getAccessToken().then((token) {
    state = token != null ? AuthStatus.authenticated : AuthStatus.unauthenticated;
  });
}

Future<void> login(String username, String password) async {
  final tokens = await _api.login(username, password);
  await _storage.saveTokens(
    access: tokens['access_token']!,
    refresh: tokens['refresh_token']!,
  );
  state = AuthStatus.authenticated;
  // Intentionally unawaited — see _checkAuth() note above.
  // ignore: unawaited_futures
  _notifService.registerWithServer();
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
flutter test test/providers/auth_provider_test.dart
```

Expected: `4 tests passed`

- [ ] **Step 5: Run full Flutter test suite**

```bash
flutter test
```

Expected: all tests pass

- [ ] **Step 6: Check formatting**

```bash
dart format --output=none --set-exit-if-changed .
```

Expected: `Formatted N files (0 changed)`

- [ ] **Step 7: Commit**

```bash
git add mobile/lib/providers/auth_provider.dart mobile/test/providers/auth_provider_test.dart
git commit -m "fix: gate FCM server registration on confirmed auth state"
```

---

## Pre-merge verification

```bash
flutter test && dart format --output=none --set-exit-if-changed .
```

Then build and install to phone:

```bash
flutter build apk --release
adb -s 192.168.1.138:40879 install -r build/app/outputs/flutter-apk/app-release.apk
```
