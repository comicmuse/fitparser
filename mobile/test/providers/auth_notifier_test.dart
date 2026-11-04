// Tests for the FCM auth-gating logic in AuthNotifier (issue #44).
//
// Everything AuthNotifier depends on is replaced with in-memory fakes that
// `implements` the real types, so no test here constructs a Dio client or
// calls into flutter_secure_storage / firebase_messaging platform code.
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/providers/auth_notifier.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/notification_service_base.dart';
import 'package:runcoach/services/secure_storage_service.dart';

class _FakeStorage implements SecureStorageService {
  _FakeStorage({String? access, this.throwOnRead = false}) : _access = access;

  String? _access;
  String? _refresh;
  bool throwOnRead;

  @override
  Future<String?> getAccessToken() async {
    if (throwOnRead) throw Exception('storage unavailable');
    return _access;
  }

  @override
  Future<String?> getRefreshToken() async => _refresh;

  @override
  Future<void> saveTokens({
    required String access,
    required String refresh,
  }) async {
    _access = access;
    _refresh = refresh;
  }

  @override
  Future<void> clearTokens() async {
    _access = null;
    _refresh = null;
  }

  @override
  Future<void> saveServerUrl(String url) async {}

  @override
  Future<String?> getServerUrl() async => null;

  @override
  Future<String?> getPushFid() async => null;

  @override
  Future<void> savePushFid(String fid) async {}

  @override
  Future<bool> isLegacyTokenMigrated() async => false;

  @override
  Future<void> markLegacyTokenMigrated() async {}
}

class _FakeApi implements ApiService {
  int logoutCalls = 0;

  @override
  Future<Map<String, String>> login(String username, String password) async => {
    'access_token': 'new-access',
    'refresh_token': 'new-refresh',
  };

  @override
  Future<void> logout() async => logoutCalls++;

  // AuthNotifier only uses login/logout; anything else is a test bug.
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('${invocation.memberName} not faked');
}

class _RecordingNotifService implements NotificationServiceBase {
  int registerCalls = 0;
  int deregisterCalls = 0;

  @override
  Future<void> registerWithServer() async => registerCalls++;

  @override
  Future<void> deregister() async => deregisterCalls++;
}

void main() {
  late _FakeStorage storage;
  late _FakeApi api;
  late _RecordingNotifService notif;

  setUp(() {
    api = _FakeApi();
    notif = _RecordingNotifService();
  });

  group('startup (_checkAuth)', () {
    test('stored token: authenticated and registers with server', () async {
      storage = _FakeStorage(access: 'stored');
      final notifier = AuthNotifier(storage, api, notif);
      await notifier.initializationComplete;

      expect(notifier.state, AuthStatus.authenticated);
      expect(notif.registerCalls, 1);
    });

    test(
      'storage read throws: unauthenticated, not stuck on unknown',
      () async {
        storage = _FakeStorage(access: 'stored', throwOnRead: true);
        final notifier = AuthNotifier(storage, api, notif);
        await notifier.initializationComplete;

        expect(notifier.state, AuthStatus.unauthenticated);
        expect(notif.registerCalls, 0);
      },
    );

    test('no stored token: unauthenticated and does NOT register', () async {
      storage = _FakeStorage();
      final notifier = AuthNotifier(storage, api, notif);
      await notifier.initializationComplete;

      expect(notifier.state, AuthStatus.unauthenticated);
      expect(notif.registerCalls, 0);
    });
  });

  group('login', () {
    test('saves tokens, authenticates and registers with server', () async {
      storage = _FakeStorage();
      final notifier = AuthNotifier(storage, api, notif);
      await notifier.initializationComplete;

      await notifier.login('user', 'pass');

      expect(notifier.state, AuthStatus.authenticated);
      expect(await storage.getAccessToken(), 'new-access');
      expect(await storage.getRefreshToken(), 'new-refresh');
      expect(notif.registerCalls, 1);
    });
  });

  group('revalidate', () {
    test('does NOT register with server (no spurious POSTs on 401)', () async {
      storage = _FakeStorage(access: 'stored');
      final notifier = AuthNotifier(storage, api, notif);
      await notifier.initializationComplete;
      expect(notif.registerCalls, 1); // from startup

      notifier.revalidate();
      await pumpEventQueue();

      expect(notifier.state, AuthStatus.authenticated);
      expect(notif.registerCalls, 1);
    });

    test('token cleared (failed refresh): becomes unauthenticated', () async {
      storage = _FakeStorage(access: 'stored');
      final notifier = AuthNotifier(storage, api, notif);
      await notifier.initializationComplete;

      await storage.clearTokens();
      notifier.revalidate();
      await pumpEventQueue();

      expect(notifier.state, AuthStatus.unauthenticated);
      expect(notif.registerCalls, 1);
    });

    test('storage error: becomes unauthenticated', () async {
      storage = _FakeStorage(access: 'stored');
      final notifier = AuthNotifier(storage, api, notif);
      await notifier.initializationComplete;

      storage.throwOnRead = true;
      notifier.revalidate();
      await pumpEventQueue();

      expect(notifier.state, AuthStatus.unauthenticated);
    });
  });

  group('logout', () {
    test('deregisters, logs out of the API and clears tokens', () async {
      storage = _FakeStorage(access: 'stored');
      final notifier = AuthNotifier(storage, api, notif);
      await notifier.initializationComplete;

      await notifier.logout();

      expect(notif.deregisterCalls, 1);
      expect(api.logoutCalls, 1);
      expect(await storage.getAccessToken(), isNull);
      expect(notifier.state, AuthStatus.unauthenticated);
    });
  });
}
