import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';
import '../services/secure_storage_service.dart';

final secureStorageProvider = Provider<SecureStorageService>((ref) => SecureStorageService());

final apiServiceProvider = Provider<ApiService>((ref) {
  return ApiService(ref.read(secureStorageProvider));
});

enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthNotifier extends StateNotifier<AuthStatus> {
  final SecureStorageService _storage;
  final ApiService _api;

  AuthNotifier(this._storage, this._api) : super(AuthStatus.unknown) {
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    final token = await _storage.getAccessToken();
    state = token != null ? AuthStatus.authenticated : AuthStatus.unauthenticated;
  }

  Future<void> login(String username, String password) async {
    final tokens = await _api.login(username, password);
    await _storage.saveTokens(
      access: tokens['access_token']!,
      refresh: tokens['refresh_token']!,
    );
    state = AuthStatus.authenticated;
  }

  Future<void> logout() async {
    await _api.logout();
    await _storage.clearTokens();
    state = AuthStatus.unauthenticated;
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthStatus>((ref) {
  return AuthNotifier(ref.read(secureStorageProvider), ref.read(apiServiceProvider));
});
