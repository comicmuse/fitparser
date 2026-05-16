import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/providers/auth_provider.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/notification_service.dart';
import 'package:runcoach/services/secure_storage_service.dart';

class _NoOpApi extends ApiService {
  _NoOpApi() : super(SecureStorageService());

  @override
  Future<Map<String, String>> login(String u, String p) async => {
    'access_token': 'at',
    'refresh_token': 'rt',
  };

  @override
  Future<void> logout() async {}
}

class _RecordingNotifService extends NotificationService {
  _RecordingNotifService(_NoOpApi api) : super(api);
  int registerCalls = 0;
  int deregisterCalls = 0;

  @override
  Future<void> registerWithServer() async => registerCalls++;

  @override
  Future<void> deregister() async => deregisterCalls++;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _NoOpApi notifierApi;
  late _NoOpApi notifApi;
  late _RecordingNotifService notif;
  late AuthNotifier notifier;

  tearDown(() {
    notifierApi.close();
    notifApi.close();
  });

  void makeFixture({required Map<String, String> storageValues}) {
    FlutterSecureStorage.setMockInitialValues(storageValues);
    notifApi = _NoOpApi();
    notif = _RecordingNotifService(notifApi);
    notifierApi = _NoOpApi();
    notifier = AuthNotifier(SecureStorageService(), notifierApi, notif);
  }

  group('AuthNotifier', () {
    test(
      '_checkAuth calls registerWithServer when a stored token exists',
      () async {
        makeFixture(storageValues: {'access_token': 'stored'});
        await pumpEventQueue();

        expect(notifier.state, AuthStatus.authenticated);
        expect(notif.registerCalls, 1);
      },
    );

    test(
      '_checkAuth does NOT call registerWithServer when no token stored',
      () async {
        makeFixture(storageValues: {});
        await pumpEventQueue();

        expect(notifier.state, AuthStatus.unauthenticated);
        expect(notif.registerCalls, 0);
      },
    );

    test('login calls registerWithServer after successful auth', () async {
      makeFixture(storageValues: {});
      await pumpEventQueue(); // let _checkAuth settle (unauthenticated)

      await notifier.login('user', 'pass');

      expect(notifier.state, AuthStatus.authenticated);
      expect(notif.registerCalls, 1);
    });

    test('revalidate does NOT call registerWithServer', () async {
      makeFixture(storageValues: {'access_token': 'stored'});
      await pumpEventQueue(); // _checkAuth fires once (registerCalls = 1)

      notifier.revalidate();
      await pumpEventQueue();

      // revalidate() must not add a second registration call
      expect(notif.registerCalls, 1);
      // state must still reflect the stored token
      expect(notifier.state, AuthStatus.authenticated);
    });
  });
}
