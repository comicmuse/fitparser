import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/providers/auth_provider.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/notification_service.dart';
import 'package:runcoach/services/secure_storage_service.dart';

class _RecordingNotifService extends NotificationService {
  _RecordingNotifService() : super(_NoOpApi());
  int registerCalls = 0;
  int deregisterCalls = 0;

  @override
  Future<void> registerWithServer() async => registerCalls++;

  @override
  Future<void> deregister() async => deregisterCalls++;
}

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

AuthNotifier _makeNotifier({
  required Map<String, String> storageValues,
  required _RecordingNotifService notif,
}) {
  FlutterSecureStorage.setMockInitialValues(storageValues);
  final storage = SecureStorageService();
  final api = _NoOpApi();
  return AuthNotifier(storage, api, notif);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AuthNotifier', () {
    test(
      '_checkAuth calls registerWithServer when a stored token exists',
      () async {
        final notif = _RecordingNotifService();
        final notifier = _makeNotifier(
          storageValues: {'access_token': 'stored'},
          notif: notif,
        );
        await pumpEventQueue();

        expect(notifier.state, AuthStatus.authenticated);
        expect(notif.registerCalls, 1);
      },
    );

    test(
      '_checkAuth does NOT call registerWithServer when no token stored',
      () async {
        final notif = _RecordingNotifService();
        final notifier = _makeNotifier(storageValues: {}, notif: notif);
        await pumpEventQueue();

        expect(notifier.state, AuthStatus.unauthenticated);
        expect(notif.registerCalls, 0);
      },
    );

    test('login calls registerWithServer after successful auth', () async {
      final notif = _RecordingNotifService();
      final notifier = _makeNotifier(storageValues: {}, notif: notif);
      await pumpEventQueue(); // let _checkAuth settle (unauthenticated)

      await notifier.login('user', 'pass');

      expect(notifier.state, AuthStatus.authenticated);
      expect(notif.registerCalls, 1);
    });

    test('revalidate does NOT call registerWithServer', () async {
      final notif = _RecordingNotifService();
      final notifier = _makeNotifier(
        storageValues: {'access_token': 'stored'},
        notif: notif,
      );
      await pumpEventQueue(); // _checkAuth fires once (registerCalls = 1)

      notifier.revalidate();
      await pumpEventQueue();

      // revalidate() must not add a second registration call
      expect(notif.registerCalls, 1);
    });
  });
}
