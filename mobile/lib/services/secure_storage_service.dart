import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorageService {
  SecureStorageService({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;
  static const _accessKey = 'access_token';
  static const _refreshKey = 'refresh_token';
  static const _serverUrlKey = 'server_url';

  /// Reads a value, treating any storage failure as "not stored".
  ///
  /// flutter_secure_storage 11 can't decrypt data written by v9 (the app
  /// skipped v10's migration), and keystore errors can surface as exceptions.
  /// Either way the right outcome is the same as an empty store: the user
  /// logs in again and the default server URL is used.
  Future<String?> _read(String key) async {
    try {
      return await _storage.read(key: key);
    } catch (e) {
      debugPrint('Secure storage read of "$key" failed: $e');
      return null;
    }
  }

  Future<void> saveTokens({
    required String access,
    required String refresh,
  }) async {
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  Future<String?> getAccessToken() => _read(_accessKey);
  Future<String?> getRefreshToken() => _read(_refreshKey);

  Future<void> clearTokens() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }

  Future<void> saveServerUrl(String url) =>
      _storage.write(key: _serverUrlKey, value: url);
  Future<String?> getServerUrl() => _read(_serverUrlKey);
}
