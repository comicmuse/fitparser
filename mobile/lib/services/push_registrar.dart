import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api_service.dart';
import 'secure_storage_service.dart';

/// The parts of Firebase Cloud Messaging that [PushRegistrar] needs.
///
/// Kept as a plain interface so the registration logic can be unit-tested
/// without loading the firebase_messaging plugin.
abstract class PushPlatform {
  /// Ask FCM to register this app instance; the result arrives on
  /// [onRegistered].
  Future<void> register();

  /// Firebase Installation IDs (FIDs) as FCM registers this app instance.
  Stream<String> get onRegistered;

  /// The legacy FCM registration token, used once to tell the server which
  /// pre-migration registration to replace. May return null.
  Future<String?> legacyToken();
}

/// Registers this device with the RunCoach server by Firebase Installation ID.
///
/// The server must accept `kind: "fid"` (issue #77, part 1). FIDs can arrive
/// before login, more than once, or not at all in a given session, so every
/// FID is stored and (re)sent idempotently once the user is authenticated.
class PushRegistrar {
  PushRegistrar(this._platform, this._api, this._storage);

  final PushPlatform _platform;
  final ApiService _api;
  final SecureStorageService _storage;

  StreamSubscription<String>? _subscription;
  bool _authenticated = false;

  /// Start listening for FIDs. Safe to call more than once.
  void start() {
    _subscription ??= _platform.onRegistered.listen(_onFid);
  }

  /// Call once auth is confirmed (startup with a session, or after login).
  /// Never throws.
  Future<void> registerWithServer() async {
    _authenticated = true;
    // onRegistered is a broadcast stream that drops events nobody is
    // listening to, and register() below can emit straight away. At startup
    // this runs before NotificationService.initialize() has called start(),
    // so make sure we're listening first.
    start();
    final known = await _storage.getPushFid();
    if (known != null) await _send(known);
    try {
      await _platform.register();
    } catch (e) {
      debugPrint('FCM register() failed: $e');
    }
  }

  /// Remove this device from the server on logout. Never throws, so logout
  /// always completes.
  Future<void> deregister() async {
    _authenticated = false;
    try {
      final fid = await _storage.getPushFid();
      if (fid != null) await _api.deleteDeviceToken(fid);
    } catch (e) {
      debugPrint('FCM deregistration failed: $e');
    }
  }

  Future<void> dispose() async {
    await _subscription?.cancel();
    _subscription = null;
  }

  Future<void> _onFid(String fid) async {
    final previous = await _storage.getPushFid();
    await _storage.savePushFid(fid);
    // Before login there's no session to register under; registerWithServer
    // sends the stored FID once auth is confirmed.
    if (!_authenticated) return;
    await _send(fid, previousFid: previous == fid ? null : previous);
  }

  Future<void> _send(String fid, {String? previousFid}) async {
    final migrated = await _storage.isLegacyTokenMigrated();
    String? replaces = previousFid;
    var legacyLookupOk = true;
    if (!migrated) {
      // A legacy token is still valid, so replacing it matters more than a
      // previous FID (stale FIDs are removed by the server when sends fail).
      final (ok, token) = await _lookUpLegacyToken();
      legacyLookupOk = ok;
      replaces = token ?? previousFid;
    }
    try {
      await _api.registerDeviceToken(fid, kind: 'fid', replaces: replaces);
      // Only stop looking up the legacy token once the server has been told
      // to replace it (or we know there isn't one); otherwise retry later so
      // the device isn't left registered twice.
      if (!migrated && legacyLookupOk) await _storage.markLegacyTokenMigrated();
    } catch (e) {
      // Swallowed like before: the next login or FID refresh retries.
      debugPrint('FCM FID registration failed: $e');
    }
  }

  /// Returns (succeeded, token). A null token with success means there is
  /// no legacy token to replace.
  Future<(bool, String?)> _lookUpLegacyToken() async {
    try {
      final token = await _platform.legacyToken().timeout(
        const Duration(seconds: 10),
      );
      return (true, token);
    } catch (e) {
      debugPrint('Legacy FCM token lookup failed: $e');
      return (false, null);
    }
  }
}
