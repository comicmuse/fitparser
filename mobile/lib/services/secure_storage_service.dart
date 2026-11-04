import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorageService {
  SecureStorageService({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;
  static const _accessKey = 'access_token';
  static const _refreshKey = 'refresh_token';
  static const _serverUrlKey = 'server_url';
  static const _pushFidKey = 'push_fid';
  static const _legacyTokenMigratedKey = 'push_legacy_token_migrated';

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

  /// Firebase Installation ID last registered with the server, so logout can
  /// remove it even if Firebase doesn't re-emit it this session.
  Future<String?> getPushFid() => _read(_pushFidKey);
  Future<void> savePushFid(String fid) =>
      _storage.write(key: _pushFidKey, value: fid);

  /// Whether this install has told the server to drop its legacy FCM token
  /// in favour of an FID (issue #77), so the deprecated lookup runs once.
  Future<bool> isLegacyTokenMigrated() async =>
      await _read(_legacyTokenMigratedKey) == 'true';
  Future<void> markLegacyTokenMigrated() =>
      _storage.write(key: _legacyTokenMigratedKey, value: 'true');

  Future<void> saveServerUrl(String url) =>
      _storage.write(key: _serverUrlKey, value: url);
  Future<String?> getServerUrl() => _read(_serverUrlKey);
}
