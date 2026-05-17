import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/providers/auth_notifier.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/notification_service_base.dart';
import 'package:runcoach/services/secure_storage_service_base.dart';

/// Pure-Dart storage: implements the base interface directly so the test
/// binary's link graph contains no `flutter_secure_storage`. Required to
/// avoid the Linux CI `flutter_tester` SIGSEGV during `--coverage`
/// finalization.
class _FakeStorage implements SecureStorageServiceBase {
  final Map<String, String?> _store;

  _FakeStorage(Map<String, String> initial) : _store = Map.from(initial);

  @override
  Future<String?> getAccessToken() async => _store['access_token'];

  @override
  Future<String?> getRefreshToken() async => _store['refresh_token'];

  @override
  Future<void> saveTokens({
    required String access,
    required String refresh,
  }) async {
    _store['access_token'] = access;
    _store['refresh_token'] = refresh;
  }

  @override
  Future<void> clearTokens() async {
    _store.remove('access_token');
    _store.remove('refresh_token');
  }

  @override
  Future<void> saveServerUrl(String url) async => _store['server_url'] = url;

  @override
  Future<String?> getServerUrl() async => _store['server_url'];
}

class _NoOpApi extends ApiService {
  _NoOpApi(SecureStorageServiceBase storage) : super(storage);

  @override
  Future<Map<String, String>> login(String u, String p) async => {
    'access_token': 'at',
    'refresh_token': 'rt',
  };

  @override
  Future<void> logout() async {}
}

/// Pure-Dart notification stub: no Firebase, no native code.
class _RecordingNotifService extends NotificationServiceBase {
  int registerCalls = 0;
  int deregisterCalls = 0;

  @override
  Future<void> registerWithServer() async => registerCalls++;

  @override
  Future<void> deregister() async => deregisterCalls++;
}

void main() {
  late _NoOpApi notifierApi;
  late _RecordingNotifService notif;
  late AuthNotifier notifier;

  tearDown(() {
    notifierApi.close();
  });

  void makeFixture({required Map<String, String> storageValues}) {
    notif = _RecordingNotifService();
    final storage = _FakeStorage(storageValues);
    notifierApi = _NoOpApi(storage);
    notifier = AuthNotifier(storage, notifierApi, notif);
  }

  group('AuthNotifier', () {
    test(
      '_checkAuth calls registerWithServer when a stored token exists',
      () async {
        makeFixture(storageValues: {'access_token': 'stored'});
        await notifier.initializationComplete;

        expect(notifier.state, AuthStatus.authenticated);
        expect(notif.registerCalls, 1);
      },
    );

    test(
      '_checkAuth does NOT call registerWithServer when no token stored',
      () async {
        makeFixture(storageValues: {});
        await notifier.initializationComplete;

        expect(notifier.state, AuthStatus.unauthenticated);
        expect(notif.registerCalls, 0);
      },
    );

    test('login calls registerWithServer after successful auth', () async {
      makeFixture(storageValues: {});
      await notifier.initializationComplete;

      await notifier.login('user', 'pass');

      expect(notifier.state, AuthStatus.authenticated);
      expect(notif.registerCalls, 1);
    });

    test('revalidate does NOT call registerWithServer', () async {
      makeFixture(storageValues: {'access_token': 'stored'});
      await notifier.initializationComplete; // registerCalls = 1

      notifier.revalidate();
      await Future.delayed(Duration.zero); // let revalidate's .then() settle

      expect(notif.registerCalls, 1);
      expect(notifier.state, AuthStatus.authenticated);
    });
  });
}
