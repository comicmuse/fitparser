import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/secure_storage_service.dart';

/// Queues pre-built JSON responses and records every RequestOptions received.
class _MockAdapter implements HttpClientAdapter {
  final _queue = <(int, Map<String, dynamic>)>[];
  final List<RequestOptions> requests = [];

  void enqueue(int status, Map<String, dynamic> body) =>
      _queue.add((status, body));

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (_queue.isEmpty) {
      throw StateError('No response queued for ${options.method} ${options.path}');
    }
    final (status, body) = _queue.removeAt(0);
    return ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: {Headers.contentTypeHeader: ['application/json']},
    );
  }

  @override
  void close({bool force = false}) {}
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
  TestWidgetsFlutterBinding.ensureInitialized();

  late _MockAdapter mainAdapter;
  late Dio mainDio;
  late _MockAdapter refreshAdapter;
  late Dio refreshDio;
  late SecureStorageService storage;
  late ApiService service;

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({
      'access_token': 'stored-access',
      'refresh_token': 'stored-refresh',
    });

    mainDio = Dio(BaseOptions(baseUrl: _baseUrl));
    mainAdapter = _MockAdapter();
    mainDio.httpClientAdapter = mainAdapter;

    refreshDio = Dio(BaseOptions(baseUrl: _baseUrl));
    refreshAdapter = _MockAdapter();
    refreshDio.httpClientAdapter = refreshAdapter;

    storage = SecureStorageService();

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
      mainDio.interceptors.add(InterceptorsWrapper(
        onRequest: (options, handler) {
          capturedAuth = options.headers['Authorization'] as String?;
          handler.next(options);
        },
      ));
      mainAdapter.enqueue(200, _dashboardOk());

      await service.getDashboard();

      expect(capturedAuth, equals('Bearer stored-access'));
    });

    test('on 401, sends refresh token in request body — not Authorization header', () async {
      // Capture the refresh request before it hits the adapter.
      Map<String, dynamic>? capturedBody;
      String? capturedAuthHeader;
      refreshDio.interceptors.add(InterceptorsWrapper(
        onRequest: (options, handler) {
          capturedBody = options.data as Map<String, dynamic>?;
          capturedAuthHeader = options.headers['Authorization'] as String?;
          handler.next(options);
        },
      ));

      mainAdapter.enqueue(401, {'error': 'token expired'});
      refreshAdapter.enqueue(200, {'access_token': 'new-access'});
      mainAdapter.enqueue(200, _dashboardOk()); // retry succeeds

      await service.getDashboard();

      expect(capturedBody, containsPair('refresh_token', 'stored-refresh'));
      expect(capturedAuthHeader, isNull);
    });

    test('on successful refresh, retries with new token and persists it', () async {
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
    });

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

    test('on 401 with no stored refresh token, passes error through without refresh attempt', () async {
      // Fresh setup: only access token, no refresh token.
      FlutterSecureStorage.setMockInitialValues({'access_token': 'stored-access'});
      final freshMainDio = Dio(BaseOptions(baseUrl: _baseUrl));
      final freshMainAdapter = _MockAdapter();
      freshMainDio.httpClientAdapter = freshMainAdapter;
      final freshRefreshAdapter = _MockAdapter();
      final freshRefreshDio = Dio(BaseOptions(baseUrl: _baseUrl));
      freshRefreshDio.httpClientAdapter = freshRefreshAdapter;

      final freshService = ApiService(
        SecureStorageService(),
        baseUrl: _baseUrl,
        testDio: freshMainDio,
        testRefreshDioFactory: (_) => freshRefreshDio,
      );

      freshMainAdapter.enqueue(401, {'error': 'unauthorized'});

      await expectLater(
        freshService.getDashboard(),
        throwsA(isA<DioException>().having(
          (e) => e.response?.statusCode,
          'statusCode',
          equals(401),
        )),
      );
      expect(freshRefreshAdapter.requests, isEmpty);
    });
  });
}
