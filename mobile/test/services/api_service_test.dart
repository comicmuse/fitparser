import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/secure_storage_service_base.dart';

/// Queues pre-built JSON responses and records every RequestOptions received.
class _MockAdapter implements HttpClientAdapter {
  final _queue = <(int, dynamic)>[];
  final List<RequestOptions> requests = [];

  void enqueue(int status, dynamic body) => _queue.add((status, body));

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (_queue.isEmpty) {
      throw StateError(
        'No response queued for ${options.method} ${options.path}',
      );
    }
    final (status, body) = _queue.removeAt(0);
    return ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

/// In-memory fake. Implements the base interface so the test binary does
/// not link `flutter_secure_storage`, which on Linux CI causes
/// `flutter_tester` to SIGSEGV during `--coverage` finalization.
class _FakeStorage implements SecureStorageServiceBase {
  final Map<String, String?> _store;

  _FakeStorage([Map<String, String> initial = const {}])
    : _store = Map.from(initial);

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

Map<String, dynamic> _dashboardOk() => {
  'latest_run': null,
  'next_workout': null,
  'training_summary': {
    'current_rsb': {'interpretation': 'unknown'},
    'rsb_history': <dynamic>[],
  },
};

const _baseUrl = 'http://test.local/api/v1';

void main() {
  late _MockAdapter mainAdapter;
  late Dio mainDio;
  late _MockAdapter refreshAdapter;
  late Dio refreshDio;
  late _FakeStorage storage;
  late ApiService service;

  tearDown(() {
    mainDio.close(force: true);
    refreshDio.close(force: true);
  });

  setUp(() {
    storage = _FakeStorage({
      'access_token': 'stored-access',
      'refresh_token': 'stored-refresh',
    });

    mainDio = Dio(BaseOptions(baseUrl: _baseUrl));
    mainAdapter = _MockAdapter();
    mainDio.httpClientAdapter = mainAdapter;

    refreshDio = Dio(BaseOptions(baseUrl: _baseUrl));
    refreshAdapter = _MockAdapter();
    refreshDio.httpClientAdapter = refreshAdapter;

    service = ApiService(
      storage,
      baseUrl: _baseUrl,
      testDio: mainDio,
      testRefreshDioFactory: (_) => refreshDio,
    );
  });

  group('_AuthInterceptor', () {
    test('attaches stored access token as Bearer header', () async {
      // Capture headers after _AuthInterceptor.onRequest has run (added last = runs after).
      String? capturedAuth;
      mainDio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            capturedAuth = options.headers['Authorization'] as String?;
            handler.next(options);
          },
        ),
      );
      mainAdapter.enqueue(200, _dashboardOk());

      await service.getDashboard();

      expect(capturedAuth, equals('Bearer stored-access'));
    });

    test(
      'on 401, sends refresh token in request body — not Authorization header',
      () async {
        // Capture the refresh request before it hits the adapter.
        Map<String, dynamic>? capturedBody;
        String? capturedAuthHeader;
        refreshDio.interceptors.add(
          InterceptorsWrapper(
            onRequest: (options, handler) {
              capturedBody = options.data as Map<String, dynamic>?;
              capturedAuthHeader = options.headers['Authorization'] as String?;
              handler.next(options);
            },
          ),
        );

        mainAdapter.enqueue(401, {'error': 'token expired'});
        refreshAdapter.enqueue(200, {'access_token': 'new-access'});
        mainAdapter.enqueue(200, _dashboardOk()); // retry succeeds

        await service.getDashboard();

        expect(capturedBody, containsPair('refresh_token', 'stored-refresh'));
        expect(capturedAuthHeader, isNull);
      },
    );

    test(
      'on successful refresh, retries with new token and persists it',
      () async {
        mainAdapter.enqueue(401, {'error': 'token expired'});
        refreshAdapter.enqueue(200, {'access_token': 'new-access'});
        mainAdapter.enqueue(200, _dashboardOk());

        await service.getDashboard();

        // New token written to storage.
        expect(await storage.getAccessToken(), equals('new-access'));

        // Retry (requests[1]) carried the new token. The interceptor sets it
        // directly on RequestOptions before calling _dio.fetch(), so it arrives
        // at the adapter regardless of whether fetch() re-runs interceptors.
        final retryAuth = mainAdapter.requests[1].headers['Authorization'];
        expect(retryAuth, equals('Bearer new-access'));
      },
    );

    test('on refresh failure, clears tokens and calls onAuthFailed', () async {
      var authFailedCalled = false;
      service.onAuthFailed = () => authFailedCalled = true;

      mainAdapter.enqueue(401, {'error': 'token expired'});
      refreshAdapter.enqueue(401, {'error': 'refresh token expired'});

      await expectLater(service.getDashboard(), throwsA(isA<DioException>()));

      expect(authFailedCalled, isTrue);
      expect(await storage.getAccessToken(), isNull);
      expect(await storage.getRefreshToken(), isNull);
    });

    test(
      'on 401 with no stored refresh token, passes error through without refresh attempt',
      () async {
        // Fresh setup: only access token, no refresh token.
        final freshStorage = _FakeStorage({'access_token': 'stored-access'});
        final freshMainDio = Dio(BaseOptions(baseUrl: _baseUrl));
        final freshMainAdapter = _MockAdapter();
        freshMainDio.httpClientAdapter = freshMainAdapter;
        final freshRefreshAdapter = _MockAdapter();
        final freshRefreshDio = Dio(BaseOptions(baseUrl: _baseUrl));
        freshRefreshDio.httpClientAdapter = freshRefreshAdapter;

        final freshService = ApiService(
          freshStorage,
          baseUrl: _baseUrl,
          testDio: freshMainDio,
          testRefreshDioFactory: (_) => freshRefreshDio,
        );

        freshMainAdapter.enqueue(401, {'error': 'unauthorized'});

        await expectLater(
          freshService.getDashboard(),
          throwsA(
            isA<DioException>().having(
              (e) => e.response?.statusCode,
              'statusCode',
              equals(401),
            ),
          ),
        );
        expect(freshRefreshAdapter.requests, isEmpty);
      },
    );
  });

  group('getPlannedWorkouts', () {
    test('GET /planned-workouts returns parsed list', () async {
      mainAdapter.enqueue(200, [
        {
          'id': 10,
          'date': '2026-05-15',
          'name': 'Easy Run',
          'description': 'Recovery',
          'distance_m': 8000.0,
          'duration_s': 2700.0,
          'stress': 35.0,
          'intensity_zones': null,
          'structure': null,
        },
        {
          'id': 11,
          'date': '2026-05-17',
          'name': 'Intervals',
          'description': 'Hard',
          'distance_m': null,
          'duration_s': null,
          'stress': null,
          'intensity_zones': null,
          'structure': null,
        },
      ]);

      final result = await service.getPlannedWorkouts();

      expect(result, hasLength(2));
      expect(result[0].id, 10);
      expect(result[0].name, 'Easy Run');
      expect(result[0].stress, closeTo(35.0, 0.001));
      expect(result[1].name, 'Intervals');
      expect(result[1].stress, isNull);

      expect(mainAdapter.requests.last.path, '/planned-workouts');
      expect(mainAdapter.requests.last.method, 'GET');
    });

    test('returns empty list when server returns []', () async {
      mainAdapter.enqueue(200, <dynamic>[]);
      final result = await service.getPlannedWorkouts();
      expect(result, isEmpty);
    });
  });
}
