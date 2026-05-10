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

  Future<void> initialize() async {
    FirebaseMessaging.onBackgroundMessage(_firebaseBackgroundMessageHandler);

    final settings = await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    if (settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional) {
      await _registerCurrentToken();
      _subscriptions.add(
        FirebaseMessaging.instance.onTokenRefresh.listen(_registerToken),
      );
    }

    _setupHandlers();
  }

  /// Deregister the current FCM token on logout. Swallows all errors so
  /// logout always completes even if FCM is unavailable.
  Future<void> deregister() async {
    try {
      final token = await FirebaseMessaging.instance.getToken();
      if (token != null) await _api.deleteDeviceToken(token);
    } catch (e) {}
  }

  Future<void> _registerCurrentToken() async {
    final token = await FirebaseMessaging.instance.getToken();
    if (token != null) await _registerToken(token);
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
