import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'api_service.dart';
import 'notification_service_base.dart';
import 'push_registrar.dart';
import 'secure_storage_service.dart';

/// Top-level handler for background FCM messages. Must be a top-level function.
@pragma('vm:entry-point')
Future<void> _firebaseBackgroundMessageHandler(RemoteMessage message) async {
  // No action needed — navigation on tap is handled by onMessageOpenedApp.
}

/// [PushPlatform] backed by the real firebase_messaging plugin.
class _FirebasePushPlatform implements PushPlatform {
  @override
  Future<void> register() => FirebaseMessaging.instance.register();

  @override
  Stream<String> get onRegistered => FirebaseMessaging.instance.onRegistered;

  @override
  Future<String?> legacyToken() =>
      // The only remaining use of the deprecated token API: looked up once,
      // so the server can drop this device's pre-FID registration (#77).
      // ignore: deprecated_member_use
      FirebaseMessaging.instance.getToken();
}

class NotificationService extends NotificationServiceBase {
  final PushRegistrar _registrar;
  final List<StreamSubscription<dynamic>> _subscriptions = [];

  /// Called when the user taps a notification (background or terminated).
  void Function(int runId)? onNotificationTap;

  /// Called when a notification arrives while the app is in the foreground.
  void Function(int runId, String runName)? onForegroundMessage;

  NotificationService(ApiService api, SecureStorageService storage)
    : _registrar = PushRegistrar(_FirebasePushPlatform(), api, storage);

  /// Sets up Firebase handlers and requests OS notification permission.
  /// Does NOT register with the server — call [registerWithServer] once auth
  /// is confirmed.
  Future<void> initialize() async {
    FirebaseMessaging.onBackgroundMessage(_firebaseBackgroundMessageHandler);

    // Listen for Firebase Installation IDs before anything that awaits (the
    // permission prompt can take a while); they're only sent to the server
    // once registerWithServer() confirms auth.
    _registrar.start();

    await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    _setupHandlers();
  }

  /// Registers this device (by Firebase Installation ID) with the server.
  /// Call after auth is confirmed (on startup with a valid session, or after
  /// login). Fire-and-forget: failures are swallowed and retried next login.
  @override
  Future<void> registerWithServer() => _registrar.registerWithServer();

  /// Removes this device from the server on logout. Swallows all errors so
  /// logout always completes even if FCM is unavailable.
  @override
  Future<void> deregister() => _registrar.deregister();

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
    _registrar.dispose();
  }
}
