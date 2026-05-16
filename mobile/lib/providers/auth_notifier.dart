import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';
import '../services/notification_service_base.dart';
import '../services/secure_storage_service.dart';

enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthNotifier extends StateNotifier<AuthStatus> {
  final SecureStorageService _storage;
  final ApiService _api;
  final NotificationServiceBase _notifService;

  // Exposed for tests so they can await startup without pumpEventQueue().
  @visibleForTesting
  late final Future<void> initializationComplete;

  AuthNotifier(this._storage, this._api, this._notifService)
    : super(AuthStatus.unknown) {
    initializationComplete = _checkAuth();
  }

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
    _storage
        .getAccessToken()
        .then((token) {
          state = token != null
              ? AuthStatus.authenticated
              : AuthStatus.unauthenticated;
        })
        .catchError((_) {
          state = AuthStatus.unauthenticated;
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

  Future<void> logout() async {
    await _notifService.deregister();
    await _api.logout();
    await _storage.clearTokens();
    state = AuthStatus.unauthenticated;
  }
}
