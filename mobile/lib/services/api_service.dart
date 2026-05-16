import 'package:dio/dio.dart';
import '../models/run.dart';
import '../models/dashboard.dart';
import '../models/chat_message.dart';
import '../models/planned_workout.dart';
import 'secure_storage_service.dart';

class ApiService {
  static const String defaultBaseUrl = String.fromEnvironment(
    'BASE_URL',
    defaultValue: 'https://runcoach.linehan.me.uk/api/v1',
  );

  final String _baseUrl;
  late final Dio _dio;
  final SecureStorageService _storage;

  /// Called when token refresh fails and credentials are cleared.
  /// Wire this up to trigger re-authentication in the auth layer.
  void Function()? onAuthFailed;

  // testDio and testRefreshDioFactory are for unit tests only.
  ApiService(
    this._storage, {
    String? baseUrl,
    Dio? testDio,
    Dio Function(String baseUrl)? testRefreshDioFactory,
  }) : _baseUrl = baseUrl ?? defaultBaseUrl {
    _dio =
        testDio ??
        Dio(
          BaseOptions(
            baseUrl: _baseUrl,
            connectTimeout: const Duration(seconds: 10),
            receiveTimeout: const Duration(seconds: 30),
          ),
        );
    _dio.interceptors.add(
      _AuthInterceptor(
        _storage,
        _dio,
        _baseUrl,
        () => onAuthFailed?.call(),
        refreshDioFactory: testRefreshDioFactory,
      ),
    );
  }

  void close() => _dio.close(force: true);

  // Auth
  Future<Map<String, String>> login(String username, String password) async {
    final resp = await _dio.post(
      '/auth/login',
      data: {'username': username, 'password': password},
    );
    return {
      'access_token': resp.data['access_token'] as String,
      'refresh_token': resp.data['refresh_token'] as String,
    };
  }

  Future<void> logout() async {
    try {
      await _dio.post('/auth/logout');
    } catch (_) {}
  }

  // Dashboard
  Future<Dashboard> getDashboard() async {
    final resp = await _dio.get('/dashboard');
    return Dashboard.fromJson(resp.data as Map<String, dynamic>);
  }

  // Planned workouts
  Future<List<PlannedWorkout>> getPlannedWorkouts() async {
    final resp = await _dio.get('/planned-workouts');
    return (resp.data as List<dynamic>)
        .map((e) => PlannedWorkout.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // Runs
  Future<Map<String, dynamic>> getRuns({
    int page = 1,
    int perPage = 20,
    int? year,
    int? month,
  }) async {
    final params = <String, dynamic>{
      'page': page,
      'per_page': perPage,
      if (year != null) 'year': year,
      if (month != null) 'month': month,
    };
    final resp = await _dio.get('/runs', queryParameters: params);
    final data = resp.data as Map<String, dynamic>;
    return {
      'runs': (data['runs'] as List)
          .map((e) => Run.fromJson(e as Map<String, dynamic>))
          .toList(),
      'pagination': data['pagination'],
    };
  }

  Future<Run> getRun(int id) async {
    final resp = await _dio.get('/runs/$id');
    return Run.fromJson(resp.data as Map<String, dynamic>);
  }

  // Chat
  Future<List<ChatMessage>> getChatHistory(int runId) async {
    final resp = await _dio.get('/runs/$runId/chat');
    final history = resp.data['history'] as List<dynamic>;
    return history
        .map((e) => ChatMessage.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<ChatMessage> sendChatMessage(int runId, String message) async {
    final resp = await _dio.post(
      '/runs/$runId/chat',
      data: {'message': message},
    );
    return ChatMessage(
      role: 'assistant',
      message: resp.data['message'] as String,
    );
  }

  // Sync
  Future<void> triggerSync() async {
    await _dio.post('/sync');
  }

  // Analyze a specific run
  Future<void> analyzeRun(int runId) async {
    await _dio.post('/runs/$runId/analyze');
  }

  // Athlete profile
  Future<Map<String, dynamic>> getAthleteProfile() async {
    final resp = await _dio.get('/athlete/profile');
    return resp.data as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> postRouteSuggestion({
    required double lat,
    required double lng,
    required int distanceM,
    bool includeOrs = true,
  }) async {
    final resp = await _dio.post(
      '/route-suggestion',
      data: {
        'lat': lat,
        'lng': lng,
        'distance_m': distanceM,
        'include_ors': includeOrs,
      },
    );
    final routes = resp.data['routes'] as List<dynamic>;
    return routes.map((e) => e as Map<String, dynamic>).toList();
  }

  // Best run time
  Future<Map<String, dynamic>> getBestRunTime({
    required double lat,
    required double lng,
  }) async {
    final r = await _dio.get<Map<String, dynamic>>(
      '/best-run-time',
      queryParameters: {'lat': lat, 'lng': lng},
    );
    return r.data!;
  }

  // Device tokens
  Future<void> registerDeviceToken(String token) async {
    await _dio.post(
      '/device-tokens',
      data: {'token': token, 'platform': 'android'},
    );
  }

  Future<void> deleteDeviceToken(String token) async {
    await _dio.delete('/device-tokens', data: {'token': token});
  }
}

class _AuthInterceptor extends Interceptor {
  final SecureStorageService _storage;
  final Dio _dio;
  final String _baseUrl;
  final void Function() _onAuthFailed;
  final Dio Function(String baseUrl)? _refreshDioFactory;

  _AuthInterceptor(
    this._storage,
    this._dio,
    this._baseUrl,
    this._onAuthFailed, {
    Dio Function(String baseUrl)? refreshDioFactory,
  }) : _refreshDioFactory = refreshDioFactory;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final token = await _storage.getAccessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode == 401) {
      final refreshToken = await _storage.getRefreshToken();
      if (refreshToken != null) {
        try {
          final refreshDio =
              _refreshDioFactory?.call(_baseUrl) ??
              Dio(BaseOptions(baseUrl: _baseUrl));
          final resp = await refreshDio.post(
            '/auth/refresh',
            data: {'refresh_token': refreshToken},
          );
          final newAccess = resp.data['access_token'] as String;
          await _storage.saveTokens(access: newAccess, refresh: refreshToken);
          err.requestOptions.headers['Authorization'] = 'Bearer $newAccess';
          final retryResp = await _dio.fetch(err.requestOptions);
          handler.resolve(retryResp);
          return;
        } catch (_) {
          await _storage.clearTokens();
          _onAuthFailed();
        }
      }
    }
    handler.next(err);
  }
}
