// PushRegistrar logic, tested without the firebase_messaging plugin: every
// dependency is an in-memory fake implementing the real type.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/push_registrar.dart';
import 'package:runcoach/services/secure_storage_service.dart';

class _FakePlatform implements PushPlatform {
  // Broadcast, like firebase_messaging's onRegistered: events emitted while
  // nobody is listening are dropped.
  final controller = StreamController<String>.broadcast();
  int registerCalls = 0;

  /// When set, register() emits this FID immediately, as the real plugin
  /// can, before the caller has a chance to subscribe.
  String? emitOnRegister;
  int legacyLookups = 0;
  String? legacy = 'legacy-fcm-token';
  bool legacyThrows = false;

  @override
  Future<void> register() async {
    registerCalls++;
    if (emitOnRegister != null) controller.add(emitOnRegister!);
  }

  @override
  Stream<String> get onRegistered => controller.stream;

  @override
  Future<String?> legacyToken() async {
    legacyLookups++;
    if (legacyThrows) throw Exception('offline');
    return legacy;
  }
}

class _Call {
  _Call(this.token, this.kind, this.replaces);
  final String token;
  final String kind;
  final String? replaces;
  @override
  String toString() => '($token, $kind, replaces: $replaces)';
}

class _FakeApi implements ApiService {
  final registered = <_Call>[];
  final deleted = <String>[];
  bool failRegister = false;

  @override
  Future<void> registerDeviceToken(
    String token, {
    String kind = 'token',
    String? replaces,
  }) async {
    if (failRegister) throw Exception('server down');
    registered.add(_Call(token, kind, replaces));
  }

  @override
  Future<void> deleteDeviceToken(String token) async => deleted.add(token);

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('${invocation.memberName} not faked');
}

class _FakeStorage implements SecureStorageService {
  String? fid;
  bool migrated = false;

  @override
  Future<String?> getPushFid() async => fid;
  @override
  Future<void> savePushFid(String value) async => fid = value;
  @override
  Future<bool> isLegacyTokenMigrated() async => migrated;
  @override
  Future<void> markLegacyTokenMigrated() async => migrated = true;

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('${invocation.memberName} not faked');
}

void main() {
  late _FakePlatform platform;
  late _FakeApi api;
  late _FakeStorage storage;
  late PushRegistrar registrar;

  setUp(() {
    platform = _FakePlatform();
    api = _FakeApi();
    storage = _FakeStorage();
    registrar = PushRegistrar(platform, api, storage)..start();
  });

  tearDown(() => registrar.dispose());

  Future<void> emitFid(String fid) async {
    platform.controller.add(fid);
    await pumpEventQueue();
  }

  test('FID before login is stored but not sent', () async {
    await emitFid('fid-1');

    expect(storage.fid, 'fid-1');
    expect(api.registered, isEmpty);
  });

  test(
    'first registration sends the FID and replaces the legacy token',
    () async {
      await emitFid('fid-1');
      await registrar.registerWithServer();

      expect(platform.registerCalls, 1);
      expect(
        api.registered.single.toString(),
        '(fid-1, fid, replaces: legacy-fcm-token)',
      );
      expect(storage.migrated, isTrue);
    },
  );

  test('FID arriving after login is sent', () async {
    await registrar.registerWithServer();
    await emitFid('fid-1');

    expect(api.registered.single.token, 'fid-1');
    expect(api.registered.single.kind, 'fid');
  });

  test(
    'after migration: no legacy lookup, a new FID replaces the old',
    () async {
      await emitFid('fid-1');
      await registrar.registerWithServer();
      final lookups = platform.legacyLookups;

      await emitFid('fid-2');

      expect(platform.legacyLookups, lookups);
      expect(api.registered.last.toString(), '(fid-2, fid, replaces: fid-1)');
      expect(storage.fid, 'fid-2');
    },
  );

  test('re-emitted identical FID does not replace itself', () async {
    await emitFid('fid-1');
    await registrar.registerWithServer();
    await emitFid('fid-1');

    expect(api.registered.last.replaces, isNull);
  });

  test(
    'fresh install with no legacy token still completes migration',
    () async {
      platform.legacy = null;
      await emitFid('fid-1');
      await registrar.registerWithServer();

      expect(api.registered.single.replaces, isNull);
      expect(storage.migrated, isTrue);
    },
  );

  test('failed legacy lookup registers but retries migration later', () async {
    platform.legacyThrows = true;
    await emitFid('fid-1');
    await registrar.registerWithServer();

    expect(api.registered.single.replaces, isNull);
    expect(storage.migrated, isFalse);

    platform.legacyThrows = false;
    await registrar.registerWithServer();
    expect(api.registered.last.replaces, 'legacy-fcm-token');
    expect(storage.migrated, isTrue);
  });

  test('server failure is swallowed and migration not marked done', () async {
    api.failRegister = true;
    await emitFid('fid-1');
    await registrar.registerWithServer();

    expect(storage.migrated, isFalse);
  });

  test('logout deletes the stored FID and stops sending new ones', () async {
    await emitFid('fid-1');
    await registrar.registerWithServer();
    final sent = api.registered.length;

    await registrar.deregister();
    await emitFid('fid-2');

    expect(api.deleted, ['fid-1']);
    expect(api.registered.length, sent);
  });

  test('logout with nothing registered makes no request', () async {
    await registrar.deregister();
    expect(api.deleted, isEmpty);
  });

  test(
    'regression: FID emitted by register() before start() is not lost',
    () async {
      // At app startup AuthNotifier calls registerWithServer() before
      // NotificationService.initialize() has called start().
      final early = PushRegistrar(platform, api, storage); // no start()
      platform.emitOnRegister = 'fid-early';

      await early.registerWithServer();
      await pumpEventQueue();

      expect(storage.fid, 'fid-early');
      expect(api.registered.map((c) => c.token), contains('fid-early'));
      await early.dispose();
    },
  );
}
