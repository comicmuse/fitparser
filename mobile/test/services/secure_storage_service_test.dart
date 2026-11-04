import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/services/secure_storage_service.dart';

/// In-memory FlutterSecureStorage whose reads can be made to throw, standing
/// in for data the plugin can no longer decrypt (e.g. written by v9).
class _FakePluginStorage implements FlutterSecureStorage {
  final Map<String, String> values = {};
  bool throwOnRead = false;

  @override
  Future<String?> read({
    required String key,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (throwOnRead) throw Exception('cannot decrypt');
    return values[key];
  }

  @override
  Future<void> write({
    required String key,
    required String? value,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (value == null) {
      values.remove(key);
    } else {
      values[key] = value;
    }
  }

  @override
  Future<void> delete({
    required String key,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async => values.remove(key);

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('${invocation.memberName} not faked');
}

void main() {
  late _FakePluginStorage plugin;
  late SecureStorageService service;

  setUp(() {
    plugin = _FakePluginStorage();
    service = SecureStorageService(storage: plugin);
  });

  test('round-trips tokens and server URL', () async {
    await service.saveTokens(access: 'a', refresh: 'r');
    await service.saveServerUrl('https://example.test/api/v1');

    expect(await service.getAccessToken(), 'a');
    expect(await service.getRefreshToken(), 'r');
    expect(await service.getServerUrl(), 'https://example.test/api/v1');
  });

  test('unreadable storage reads as empty instead of throwing', () async {
    plugin.values['access_token'] = 'old-v9-data';
    plugin.throwOnRead = true;

    expect(await service.getAccessToken(), isNull);
    expect(await service.getRefreshToken(), isNull);
    expect(await service.getServerUrl(), isNull);
  });

  test('clearTokens removes both tokens', () async {
    await service.saveTokens(access: 'a', refresh: 'r');
    await service.clearTokens();

    expect(await service.getAccessToken(), isNull);
    expect(await service.getRefreshToken(), isNull);
  });
}
