import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';
import '../services/secure_storage_service.dart';

final secureStorageProvider = Provider<SecureStorageService>(
  (ref) => SecureStorageService(),
);

const _defaultServerUrl = String.fromEnvironment(
  'BASE_URL',
  defaultValue: 'https://runcoach.linehan.me.uk/api/v1',
);

class ServerUrlNotifier extends AsyncNotifier<String> {
  @override
  Future<String> build() async {
    final storage = ref.read(secureStorageProvider);
    return await storage.getServerUrl() ?? _defaultServerUrl;
  }

  Future<void> setUrl(String url) async {
    final trimmed = url.trimRight().replaceAll(RegExp(r'/$'), '');
    await ref.read(secureStorageProvider).saveServerUrl(trimmed);
    state = AsyncData(trimmed);
  }
}

final serverUrlProvider = AsyncNotifierProvider<ServerUrlNotifier, String>(
  ServerUrlNotifier.new,
);

final apiServiceProvider = Provider<ApiService>((ref) {
  final urlAsync = ref.watch(serverUrlProvider);
  final url = urlAsync.valueOrNull ?? _defaultServerUrl;
  return ApiService(ref.read(secureStorageProvider), baseUrl: url);
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
    state = token != null
        ? AuthStatus.authenticated
        : AuthStatus.unauthenticated;
  }

  void revalidate() => _checkAuth();

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
  final api = ref.read(apiServiceProvider);
  final notifier = AuthNotifier(ref.read(secureStorageProvider), api);
  api.onAuthFailed = notifier.revalidate;
  return notifier;
});

final athleteProfileProvider = FutureProvider<Map<String, dynamic>>((
  ref,
) async {
  return ref.watch(apiServiceProvider).getAthleteProfile();
});
