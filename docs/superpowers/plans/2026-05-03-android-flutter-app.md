# RunCoach Flutter Android App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flutter Android app in `mobile/` that surfaces RSB training load, recent/historical activities, workout blocks, AI coaching commentary, and per-run chat against the RunCoach `/api/v1` REST API.

**Architecture:** Flutter + Riverpod for state, go_router for navigation (3-tab shell + push routes), dio for HTTP with automatic JWT refresh. Clean Light theme (white cards, `#6750a4` purple accent, `#2e7d32` green). All data from the existing API — no direct DB access.

**Tech Stack:** Flutter 3.x, Dart, Riverpod 2.x, go_router 14.x, dio 5.x, flutter_secure_storage 9.x, fl_chart 0.68.x, flutter_map 7.x, flutter_markdown 0.7.x.

**Prerequisite:** Complete the `2026-05-03-android-api-additions.md` plan first — this app depends on the `/dashboard` endpoint and updated run/profile responses.

---

## File Map

```
mobile/
  pubspec.yaml
  lib/
    main.dart                          # entry point, ProviderScope
    app.dart                           # MaterialApp.router, go_router, theme
    models/
      run.dart                         # Run, RunStage
      training_summary.dart            # TrainingSummary, RsbPoint, CurrentRsb
      workout_block.dart               # WorkoutBlock, BlockType, PowerCompliance
      planned_workout.dart             # PlannedWorkout
      dashboard.dart                   # Dashboard (latest_run + next_workout + training_summary)
      chat_message.dart                # ChatMessage
    services/
      api_service.dart                 # dio client, all API calls, JWT refresh interceptor
      secure_storage_service.dart      # token read/write via flutter_secure_storage
    providers/
      auth_provider.dart               # login, logout, token state (StateNotifier)
      dashboard_provider.dart          # GET /dashboard (AsyncNotifier)
      runs_provider.dart               # paginated run list with year/month filter
      run_detail_provider.dart         # GET /runs/:id (AsyncNotifier family)
      chat_provider.dart               # chat history + send message (StateNotifier family)
    screens/
      login_screen.dart
      home_screen.dart
      activities_screen.dart
      profile_screen.dart
      run_detail_screen.dart           # TabController host for Overview/Blocks/Coaching
    widgets/
      rsb_card.dart                    # RSB value + sparkline
      run_summary_card.dart            # latest/list run card (tappable)
      next_workout_card.dart           # next planned workout
      hr_zones_bar.dart                # segmented HR zone bar
      block_card.dart                  # single workout block card
      route_map_widget.dart            # flutter_map with polyline
      coaching_chat_widget.dart        # commentary + chat thread + input
      year_month_chips.dart            # scrollable filter chips
```

---

### Task 1: Project scaffold and pubspec

**Files:**
- Create: `mobile/pubspec.yaml`
- Create: `mobile/lib/main.dart`

- [ ] **Step 1: Create the Flutter project**

```bash
cd /home/colm/git/fitparser
flutter create mobile --org com.runcoach --platforms android
```

Expected: Flutter project created at `mobile/`

- [ ] **Step 2: Replace `mobile/pubspec.yaml` dependencies section**

Open `mobile/pubspec.yaml` and replace the `dependencies:` and `dev_dependencies:` sections with:

```yaml
dependencies:
  flutter:
    sdk: flutter
  flutter_riverpod: ^2.5.1
  riverpod_annotation: ^2.3.5
  go_router: ^14.2.7
  dio: ^5.4.3
  flutter_secure_storage: ^9.2.2
  fl_chart: ^0.68.0
  flutter_map: ^7.0.2
  latlong2: ^0.9.1
  flutter_markdown: ^0.7.3
  intl: ^0.19.0

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^4.0.0
  build_runner: ^2.4.9
  riverpod_generator: ^2.4.0
```

- [ ] **Step 3: Get dependencies**

```bash
cd mobile
flutter pub get
```

Expected: all packages resolved, no errors

- [ ] **Step 4: Replace `mobile/lib/main.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app.dart';

void main() {
  runApp(const ProviderScope(child: RunCoachApp()));
}
```

- [ ] **Step 5: Verify project builds**

```bash
cd mobile
flutter build apk --debug 2>&1 | tail -5
```

Expected: BUILD SUCCESSFUL (or just compiles without error — no logic yet)

- [ ] **Step 6: Commit**

```bash
git add mobile/
git commit -m "feat: scaffold Flutter mobile project"
```

---

### Task 2: Models

**Files:**
- Create: `mobile/lib/models/run.dart`
- Create: `mobile/lib/models/training_summary.dart`
- Create: `mobile/lib/models/workout_block.dart`
- Create: `mobile/lib/models/planned_workout.dart`
- Create: `mobile/lib/models/dashboard.dart`
- Create: `mobile/lib/models/chat_message.dart`

- [ ] **Step 1: Create `mobile/lib/models/run.dart`**

```dart
enum RunStage { synced, parsed, analyzed, error, unknown }

class Run {
  final int id;
  final String name;
  final String date;
  final double? distanceKm;
  final int? durationS;
  final String durationFormatted;
  final int? avgPowerW;
  final int? avgHr;
  final double? strydRss;
  final RunStage stage;
  final String? commentary;
  final String? analyzedAt;
  final String? stravaActivityId;
  final int? strydActivityId;
  final String? stravaMapPolyline;
  final Map<String, dynamic>? yamlData;

  const Run({
    required this.id,
    required this.name,
    required this.date,
    this.distanceKm,
    this.durationS,
    required this.durationFormatted,
    this.avgPowerW,
    this.avgHr,
    this.strydRss,
    required this.stage,
    this.commentary,
    this.analyzedAt,
    this.stravaActivityId,
    this.strydActivityId,
    this.stravaMapPolyline,
    this.yamlData,
  });

  factory Run.fromJson(Map<String, dynamic> json) {
    final stageStr = json['stage'] as String? ?? 'unknown';
    final stage = RunStage.values.firstWhere(
      (e) => e.name == stageStr,
      orElse: () => RunStage.unknown,
    );
    return Run(
      id: json['id'] as int,
      name: json['name'] as String? ?? '',
      date: json['date'] as String? ?? '',
      distanceKm: (json['distance_km'] as num?)?.toDouble(),
      durationS: json['duration_s'] as int?,
      durationFormatted: json['duration_formatted'] as String? ?? '—',
      avgPowerW: json['avg_power_w'] as int?,
      avgHr: json['avg_hr'] as int?,
      strydRss: (json['stryd_rss'] as num?)?.toDouble(),
      stage: stage,
      commentary: json['commentary'] as String?,
      analyzedAt: json['analyzed_at'] as String?,
      stravaActivityId: json['strava_activity_id'] as String?,
      strydActivityId: json['stryd_activity_id'] as int?,
      stravaMapPolyline: json['strava_map_polyline'] as String?,
      yamlData: json['yaml_data'] as Map<String, dynamic>?,
    );
  }
}
```

- [ ] **Step 2: Create `mobile/lib/models/training_summary.dart`**

```dart
class RsbPoint {
  final String date;
  final double? rsb;
  final double? ctl;
  final double? atl;

  const RsbPoint({required this.date, this.rsb, this.ctl, this.atl});

  factory RsbPoint.fromJson(Map<String, dynamic> json) => RsbPoint(
        date: json['date'] as String,
        rsb: (json['rsb'] as num?)?.toDouble(),
        ctl: (json['ctl'] as num?)?.toDouble(),
        atl: (json['atl'] as num?)?.toDouble(),
      );
}

class CurrentRsb {
  final double? rsb;
  final double? ctl;
  final double? atl;
  final String interpretation;

  const CurrentRsb({this.rsb, this.ctl, this.atl, required this.interpretation});

  factory CurrentRsb.fromJson(Map<String, dynamic> json) => CurrentRsb(
        rsb: (json['rsb'] as num?)?.toDouble(),
        ctl: (json['ctl'] as num?)?.toDouble(),
        atl: (json['atl'] as num?)?.toDouble(),
        interpretation: json['interpretation'] as String? ?? 'unknown',
      );
}

class TrainingSummary {
  final CurrentRsb currentRsb;
  final List<RsbPoint> rsbHistory;

  const TrainingSummary({required this.currentRsb, required this.rsbHistory});

  factory TrainingSummary.fromJson(Map<String, dynamic> json) => TrainingSummary(
        currentRsb: CurrentRsb.fromJson(json['current_rsb'] as Map<String, dynamic>),
        rsbHistory: (json['rsb_history'] as List<dynamic>)
            .map((e) => RsbPoint.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
```

- [ ] **Step 3: Create `mobile/lib/models/workout_block.dart`**

```dart
enum BlockType { warmup, work, rest, cooldown, unknown }

class PowerCompliance {
  final double belowPct;
  final double inZonePct;
  final double abovePct;

  const PowerCompliance({
    required this.belowPct,
    required this.inZonePct,
    required this.abovePct,
  });
}

class WorkoutBlock {
  final String type;
  final BlockType blockType;
  final int? durationS;
  final double? avgPowerW;
  final int? avgHr;
  final double? avgPaceSecPerKm;
  final double? targetPowerLow;
  final double? targetPowerHigh;
  final PowerCompliance? powerCompliance;

  const WorkoutBlock({
    required this.type,
    required this.blockType,
    this.durationS,
    this.avgPowerW,
    this.avgHr,
    this.avgPaceSecPerKm,
    this.targetPowerLow,
    this.targetPowerHigh,
    this.powerCompliance,
  });

  factory WorkoutBlock.fromJson(Map<String, dynamic> json) {
    final typeStr = (json['type'] as String? ?? '').toLowerCase();
    final blockType = BlockType.values.firstWhere(
      (e) => e.name == typeStr,
      orElse: () => BlockType.unknown,
    );

    PowerCompliance? compliance;
    final comp = json['power_compliance'] as Map<String, dynamic>?;
    if (comp != null) {
      compliance = PowerCompliance(
        belowPct: (comp['below_pct'] as num?)?.toDouble() ?? 0,
        inZonePct: (comp['in_zone_pct'] as num?)?.toDouble() ?? 0,
        abovePct: (comp['above_pct'] as num?)?.toDouble() ?? 0,
      );
    }

    return WorkoutBlock(
      type: json['type'] as String? ?? '',
      blockType: blockType,
      durationS: json['duration_s'] as int?,
      avgPowerW: (json['avg_power_w'] as num?)?.toInt(),
      avgHr: (json['avg_hr'] as num?)?.toInt(),
      avgPaceSecPerKm: (json['avg_pace_sec_per_km'] as num?)?.toDouble(),
      targetPowerLow: (json['target_power_low'] as num?)?.toDouble(),
      targetPowerHigh: (json['target_power_high'] as num?)?.toDouble(),
      powerCompliance: compliance,
    );
  }

  String get formattedDuration {
    if (durationS == null) return '—';
    final m = durationS! ~/ 60;
    final s = durationS! % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }

  String get formattedPace {
    if (avgPaceSecPerKm == null) return '—';
    final m = avgPaceSecPerKm! ~/ 60;
    final s = (avgPaceSecPerKm! % 60).toInt();
    return '$m:${s.toString().padLeft(2, '0')}/km';
  }
}
```

- [ ] **Step 4: Create `mobile/lib/models/planned_workout.dart`**

```dart
class PlannedWorkout {
  final String date;
  final String name;
  final String description;

  const PlannedWorkout({
    required this.date,
    required this.name,
    required this.description,
  });

  factory PlannedWorkout.fromJson(Map<String, dynamic> json) => PlannedWorkout(
        date: json['date'] as String,
        name: json['name'] as String? ?? '',
        description: json['description'] as String? ?? '',
      );
}
```

- [ ] **Step 5: Create `mobile/lib/models/dashboard.dart`**

```dart
import 'run.dart';
import 'training_summary.dart';
import 'planned_workout.dart';

class Dashboard {
  final Run? latestRun;
  final PlannedWorkout? nextWorkout;
  final TrainingSummary trainingSummary;

  const Dashboard({
    this.latestRun,
    this.nextWorkout,
    required this.trainingSummary,
  });

  factory Dashboard.fromJson(Map<String, dynamic> json) => Dashboard(
        latestRun: json['latest_run'] != null
            ? Run.fromJson(json['latest_run'] as Map<String, dynamic>)
            : null,
        nextWorkout: json['next_workout'] != null
            ? PlannedWorkout.fromJson(json['next_workout'] as Map<String, dynamic>)
            : null,
        trainingSummary: TrainingSummary.fromJson(
            json['training_summary'] as Map<String, dynamic>),
      );
}
```

- [ ] **Step 6: Create `mobile/lib/models/chat_message.dart`**

```dart
class ChatMessage {
  final String role;
  final String message;
  final String? createdAt;

  const ChatMessage({
    required this.role,
    required this.message,
    this.createdAt,
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
        role: json['role'] as String,
        message: json['message'] as String? ?? '',
        createdAt: json['created_at'] as String?,
      );

  bool get isUser => role == 'user';
}
```

- [ ] **Step 7: Verify models compile**

```bash
cd mobile
flutter analyze lib/models/
```

Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add mobile/lib/models/
git commit -m "feat: add Dart data models for RunCoach API"
```

---

### Task 3: Services — secure storage and API client

**Files:**
- Create: `mobile/lib/services/secure_storage_service.dart`
- Create: `mobile/lib/services/api_service.dart`

- [ ] **Step 1: Create `mobile/lib/services/secure_storage_service.dart`**

```dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorageService {
  static const _storage = FlutterSecureStorage();
  static const _accessKey = 'access_token';
  static const _refreshKey = 'refresh_token';

  Future<void> saveTokens({required String access, required String refresh}) async {
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  Future<String?> getAccessToken() => _storage.read(key: _accessKey);
  Future<String?> getRefreshToken() => _storage.read(key: _refreshKey);

  Future<void> clearTokens() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
```

- [ ] **Step 2: Create `mobile/lib/services/api_service.dart`**

Replace `BASE_URL` with the actual server URL. During development this will be your local machine's IP (not `localhost` on Android emulator — use `10.0.2.2` for the Android emulator's loopback alias, or your LAN IP for a real device).

```dart
import 'package:dio/dio.dart';
import '../models/run.dart';
import '../models/dashboard.dart';
import '../models/chat_message.dart';
import 'secure_storage_service.dart';

class ApiService {
  static const String baseUrl = 'http://10.0.2.2:5000/api/v1';

  late final Dio _dio;
  final SecureStorageService _storage;

  ApiService(this._storage) {
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
    ));
    _dio.interceptors.add(_AuthInterceptor(_storage, _dio));
  }

  // Auth
  Future<Map<String, String>> login(String username, String password) async {
    final resp = await _dio.post('/auth/login', data: {
      'username': username,
      'password': password,
    });
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
      'runs': (data['runs'] as List).map((e) => Run.fromJson(e as Map<String, dynamic>)).toList(),
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
    return history.map((e) => ChatMessage.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<ChatMessage> sendChatMessage(int runId, String message) async {
    final resp = await _dio.post('/runs/$runId/chat', data: {'message': message});
    return ChatMessage(role: 'assistant', message: resp.data['message'] as String);
  }

  // Sync
  Future<void> triggerSync() async {
    await _dio.post('/sync');
  }

  // Athlete profile
  Future<Map<String, dynamic>> getAthleteProfile() async {
    final resp = await _dio.get('/athlete/profile');
    return resp.data as Map<String, dynamic>;
  }
}

class _AuthInterceptor extends Interceptor {
  final SecureStorageService _storage;
  final Dio _dio;

  _AuthInterceptor(this._storage, this._dio);

  @override
  Future<void> onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final token = await _storage.getAccessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode == 401) {
      final refreshToken = await _storage.getRefreshToken();
      if (refreshToken != null) {
        try {
          final refreshDio = Dio(BaseOptions(baseUrl: ApiService.baseUrl));
          final resp = await refreshDio.post('/auth/refresh',
              options: Options(headers: {'Authorization': 'Bearer $refreshToken'}));
          final newAccess = resp.data['access_token'] as String;
          await _storage.saveTokens(
              access: newAccess, refresh: refreshToken);
          err.requestOptions.headers['Authorization'] = 'Bearer $newAccess';
          final retryResp = await _dio.fetch(err.requestOptions);
          handler.resolve(retryResp);
          return;
        } catch (_) {
          await _storage.clearTokens();
        }
      }
    }
    handler.next(err);
  }
}
```

- [ ] **Step 3: Verify services compile**

```bash
cd mobile
flutter analyze lib/services/
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add mobile/lib/services/
git commit -m "feat: add API service and secure storage service"
```

---

### Task 4: Providers

**Files:**
- Create: `mobile/lib/providers/auth_provider.dart`
- Create: `mobile/lib/providers/dashboard_provider.dart`
- Create: `mobile/lib/providers/runs_provider.dart`
- Create: `mobile/lib/providers/run_detail_provider.dart`
- Create: `mobile/lib/providers/chat_provider.dart`

- [ ] **Step 1: Create `mobile/lib/providers/auth_provider.dart`**

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';
import '../services/secure_storage_service.dart';

final secureStorageProvider = Provider<SecureStorageService>((ref) => SecureStorageService());

final apiServiceProvider = Provider<ApiService>((ref) {
  return ApiService(ref.read(secureStorageProvider));
});

enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthNotifier extends StateNotifier<AuthStatus> {
  final SecureStorageService _storage;
  final ApiService _api;

  AuthNotifier(this._storage, this._api) : super(AuthStatus.unknown) {
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    final token = await _storage.getAccessToken();
    state = token != null ? AuthStatus.authenticated : AuthStatus.unauthenticated;
  }

  Future<void> login(String username, String password) async {
    final tokens = await _api.login(username, password);
    await _storage.saveTokens(
      access: tokens['access_token']!,
      refresh: tokens['refresh_token']!,
    );
    state = AuthStatus.authenticated;
  }

  Future<void> logout() async {
    await _api.logout();
    await _storage.clearTokens();
    state = AuthStatus.unauthenticated;
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthStatus>((ref) {
  return AuthNotifier(ref.read(secureStorageProvider), ref.read(apiServiceProvider));
});
```

- [ ] **Step 2: Create `mobile/lib/providers/dashboard_provider.dart`**

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/dashboard.dart';
import 'auth_provider.dart';

final dashboardProvider = FutureProvider.autoDispose<Dashboard>((ref) async {
  ref.watch(authProvider);
  final api = ref.read(apiServiceProvider);
  return api.getDashboard();
});
```

- [ ] **Step 3: Create `mobile/lib/providers/runs_provider.dart`**

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/run.dart';
import 'auth_provider.dart';

class RunsFilter {
  final int? year;
  final int? month;

  const RunsFilter({this.year, this.month});

  @override
  bool operator ==(Object other) =>
      other is RunsFilter && other.year == year && other.month == month;

  @override
  int get hashCode => Object.hash(year, month);
}

class RunsState {
  final List<Run> runs;
  final int currentPage;
  final int totalPages;
  final bool isLoading;
  final String? error;

  const RunsState({
    this.runs = const [],
    this.currentPage = 0,
    this.totalPages = 1,
    this.isLoading = false,
    this.error,
  });

  bool get hasMore => currentPage < totalPages;

  RunsState copyWith({
    List<Run>? runs,
    int? currentPage,
    int? totalPages,
    bool? isLoading,
    String? error,
  }) =>
      RunsState(
        runs: runs ?? this.runs,
        currentPage: currentPage ?? this.currentPage,
        totalPages: totalPages ?? this.totalPages,
        isLoading: isLoading ?? this.isLoading,
        error: error,
      );
}

class RunsNotifier extends StateNotifier<RunsState> {
  final Ref _ref;
  RunsFilter _filter;

  RunsNotifier(this._ref, this._filter) : super(const RunsState()) {
    loadMore();
  }

  void setFilter(RunsFilter filter) {
    _filter = filter;
    state = const RunsState();
    loadMore();
  }

  Future<void> loadMore() async {
    if (state.isLoading || !state.hasMore) return;
    state = state.copyWith(isLoading: true);
    try {
      final api = _ref.read(apiServiceProvider);
      final result = await api.getRuns(
        page: state.currentPage + 1,
        year: _filter.year,
        month: _filter.month,
      );
      final newRuns = result['runs'] as List<Run>;
      final pagination = result['pagination'] as Map<String, dynamic>;
      state = state.copyWith(
        runs: [...state.runs, ...newRuns],
        currentPage: pagination['page'] as int,
        totalPages: pagination['total_pages'] as int,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }
}

final runsFilterProvider = StateProvider<RunsFilter>((ref) => const RunsFilter());

final runsProvider = StateNotifierProvider.autoDispose<RunsNotifier, RunsState>((ref) {
  final filter = ref.watch(runsFilterProvider);
  return RunsNotifier(ref, filter);
});
```

- [ ] **Step 4: Create `mobile/lib/providers/run_detail_provider.dart`**

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/run.dart';
import 'auth_provider.dart';

final runDetailProvider = FutureProvider.autoDispose.family<Run, int>((ref, runId) async {
  final api = ref.read(apiServiceProvider);
  return api.getRun(runId);
});
```

- [ ] **Step 5: Create `mobile/lib/providers/chat_provider.dart`**

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/chat_message.dart';
import 'auth_provider.dart';

class ChatState {
  final List<ChatMessage> messages;
  final bool isLoading;
  final bool isSending;

  const ChatState({
    this.messages = const [],
    this.isLoading = false,
    this.isSending = false,
  });

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? isLoading,
    bool? isSending,
  }) =>
      ChatState(
        messages: messages ?? this.messages,
        isLoading: isLoading ?? this.isLoading,
        isSending: isSending ?? this.isSending,
      );
}

class ChatNotifier extends StateNotifier<ChatState> {
  final Ref _ref;
  final int _runId;

  ChatNotifier(this._ref, this._runId) : super(const ChatState()) {
    _load();
  }

  Future<void> _load() async {
    state = state.copyWith(isLoading: true);
    try {
      final api = _ref.read(apiServiceProvider);
      final history = await api.getChatHistory(_runId);
      state = state.copyWith(messages: history, isLoading: false);
    } catch (_) {
      state = state.copyWith(isLoading: false);
    }
  }

  Future<void> send(String message) async {
    if (message.trim().isEmpty || state.isSending) return;
    final userMsg = ChatMessage(role: 'user', message: message);
    state = state.copyWith(
      messages: [...state.messages, userMsg],
      isSending: true,
    );
    try {
      final api = _ref.read(apiServiceProvider);
      final response = await api.sendChatMessage(_runId, message);
      state = state.copyWith(
        messages: [...state.messages, response],
        isSending: false,
      );
    } catch (_) {
      state = state.copyWith(isSending: false);
    }
  }
}

final chatProvider =
    StateNotifierProvider.autoDispose.family<ChatNotifier, ChatState, int>((ref, runId) {
  return ChatNotifier(ref, runId);
});
```

- [ ] **Step 6: Verify providers compile**

```bash
cd mobile
flutter analyze lib/providers/
```

Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add mobile/lib/providers/
git commit -m "feat: add Riverpod providers for auth, dashboard, runs, and chat"
```

---

### Task 5: Theme and app router

**Files:**
- Create: `mobile/lib/app.dart`

- [ ] **Step 1: Create `mobile/lib/app.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'providers/auth_provider.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'screens/activities_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/run_detail_screen.dart';

final _rootNavKey = GlobalKey<NavigatorState>();
final _shellNavKey = GlobalKey<NavigatorState>();

final routerProvider = Provider<GoRouter>((ref) {
  final authStatus = ref.watch(authProvider);

  return GoRouter(
    navigatorKey: _rootNavKey,
    redirect: (context, state) {
      final isLoginRoute = state.matchedLocation == '/login';
      if (authStatus == AuthStatus.unauthenticated && !isLoginRoute) return '/login';
      if (authStatus == AuthStatus.authenticated && isLoginRoute) return '/home';
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (_, __) => const LoginScreen(),
      ),
      ShellRoute(
        navigatorKey: _shellNavKey,
        builder: (context, state, child) => ScaffoldWithNavBar(child: child),
        routes: [
          GoRoute(
            path: '/home',
            builder: (_, __) => const HomeScreen(),
            routes: [
              GoRoute(
                path: 'run/:id',
                parentNavigatorKey: _rootNavKey,
                builder: (_, state) => RunDetailScreen(
                  runId: int.parse(state.pathParameters['id']!),
                ),
              ),
            ],
          ),
          GoRoute(
            path: '/activities',
            builder: (_, __) => const ActivitiesScreen(),
            routes: [
              GoRoute(
                path: 'run/:id',
                parentNavigatorKey: _rootNavKey,
                builder: (_, state) => RunDetailScreen(
                  runId: int.parse(state.pathParameters['id']!),
                ),
              ),
            ],
          ),
          GoRoute(
            path: '/profile',
            builder: (_, __) => const ProfileScreen(),
          ),
        ],
      ),
    ],
    initialLocation: '/home',
  );
});

class ScaffoldWithNavBar extends ConsumerWidget {
  final Widget child;
  const ScaffoldWithNavBar({required this.child, super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;
    final index = switch (location) {
      String l when l.startsWith('/home') => 0,
      String l when l.startsWith('/activities') => 1,
      String l when l.startsWith('/profile') => 2,
      _ => 0,
    };

    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) {
          switch (i) {
            case 0: context.go('/home');
            case 1: context.go('/activities');
            case 2: context.go('/profile');
          }
        },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.list_outlined), selectedIcon: Icon(Icons.list), label: 'Activities'),
          NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
}

class RunCoachApp extends ConsumerWidget {
  const RunCoachApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'RunCoach',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6750A4),
          brightness: Brightness.light,
        ).copyWith(
          surface: Colors.white,
          onSurface: const Color(0xFF1A1A1A),
        ),
        scaffoldBackgroundColor: const Color(0xFFF5F5F5),
        cardTheme: const CardTheme(
          color: Colors.white,
          elevation: 1,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(12)),
          ),
        ),
        useMaterial3: true,
      ),
      routerConfig: router,
    );
  }
}
```

- [ ] **Step 2: Create stub screens so the app compiles**

Create each of these files with a minimal stub:

`mobile/lib/screens/login_screen.dart`:
```dart
import 'package:flutter/material.dart';
class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(body: Center(child: Text('Login')));
}
```

`mobile/lib/screens/home_screen.dart`:
```dart
import 'package:flutter/material.dart';
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(body: Center(child: Text('Home')));
}
```

`mobile/lib/screens/activities_screen.dart`:
```dart
import 'package:flutter/material.dart';
class ActivitiesScreen extends StatelessWidget {
  const ActivitiesScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(body: Center(child: Text('Activities')));
}
```

`mobile/lib/screens/profile_screen.dart`:
```dart
import 'package:flutter/material.dart';
class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(body: Center(child: Text('Profile')));
}
```

`mobile/lib/screens/run_detail_screen.dart`:
```dart
import 'package:flutter/material.dart';
class RunDetailScreen extends StatelessWidget {
  final int runId;
  const RunDetailScreen({required this.runId, super.key});
  @override
  Widget build(BuildContext context) => Scaffold(body: Center(child: Text('Run $runId')));
}
```

- [ ] **Step 3: Verify the app compiles and runs on emulator**

```bash
cd mobile
flutter run
```

Expected: app launches, shows "Home" tab with stub text, bottom nav switches between Home/Activities/Profile, login redirect works if no token stored.

- [ ] **Step 4: Commit**

```bash
git add mobile/lib/app.dart mobile/lib/screens/
git commit -m "feat: add app router, theme, and screen stubs"
```

---

### Task 6: Login screen

**Files:**
- Modify: `mobile/lib/screens/login_screen.dart`

- [ ] **Step 1: Implement `login_screen.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/auth_provider.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() { _loading = true; _error = null; });
    try {
      await ref.read(authProvider.notifier).login(
        _usernameController.text.trim(),
        _passwordController.text,
      );
    } catch (e) {
      setState(() { _error = 'Invalid username or password'; });
    } finally {
      if (mounted) setState(() { _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F5F5),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('RunCoach',
                  style: TextStyle(fontSize: 32, fontWeight: FontWeight.w800, color: Color(0xFF1A1A1A)),
                  textAlign: TextAlign.center),
              const SizedBox(height: 4),
              const Text('Your AI running coach',
                  style: TextStyle(fontSize: 14, color: Color(0xFF888888)),
                  textAlign: TextAlign.center),
              const SizedBox(height: 40),
              TextField(
                controller: _usernameController,
                decoration: const InputDecoration(
                  labelText: 'Username',
                  border: OutlineInputBorder(),
                  filled: true,
                  fillColor: Colors.white,
                ),
                textInputAction: TextInputAction.next,
                autofillHints: const [AutofillHints.username],
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _passwordController,
                decoration: const InputDecoration(
                  labelText: 'Password',
                  border: OutlineInputBorder(),
                  filled: true,
                  fillColor: Colors.white,
                ),
                obscureText: true,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _submit(),
                autofillHints: const [AutofillHints.password],
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!, style: const TextStyle(color: Color(0xFFEF4444)), textAlign: TextAlign.center),
              ],
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _loading ? null : _submit,
                child: _loading
                    ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Sign In'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Test login on emulator**

Run the app, verify:
- Login form shows on launch (no stored token)
- Wrong credentials shows error message
- Correct credentials navigates to Home tab

- [ ] **Step 3: Commit**

```bash
git add mobile/lib/screens/login_screen.dart
git commit -m "feat: implement login screen"
```

---

### Task 7: Widgets — RSB card, run summary card, next workout card

**Files:**
- Create: `mobile/lib/widgets/rsb_card.dart`
- Create: `mobile/lib/widgets/run_summary_card.dart`
- Create: `mobile/lib/widgets/next_workout_card.dart`

- [ ] **Step 1: Create `mobile/lib/widgets/rsb_card.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../models/training_summary.dart';

class RsbCard extends StatelessWidget {
  final TrainingSummary summary;
  const RsbCard({required this.summary, super.key});

  Color get _rsbColor {
    final rsb = summary.currentRsb.rsb;
    if (rsb == null) return Colors.grey;
    if (rsb > 5) return const Color(0xFF2E7D32);
    if (rsb < -10) return const Color(0xFFEF4444);
    return const Color(0xFF888888);
  }

  String get _rsbLabel {
    final interp = summary.currentRsb.interpretation.toLowerCase();
    return interp[0].toUpperCase() + interp.substring(1);
  }

  @override
  Widget build(BuildContext context) {
    final rsb = summary.currentRsb;
    final history = summary.rsbHistory;

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('TRAINING STATUS',
                style: TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text(
                  rsb.rsb != null ? (rsb.rsb! >= 0 ? '+${rsb.rsb!.toStringAsFixed(1)}' : rsb.rsb!.toStringAsFixed(1)) : '—',
                  style: TextStyle(fontSize: 36, fontWeight: FontWeight.w800, color: _rsbColor),
                ),
                const SizedBox(width: 8),
                Text(_rsbLabel, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: _rsbColor)),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                _statChip('CTL', rsb.ctl?.toStringAsFixed(1) ?? '—'),
                const SizedBox(width: 16),
                _statChip('ATL', rsb.atl?.toStringAsFixed(1) ?? '—'),
                const SizedBox(width: 16),
                _statChip('RSB', rsb.rsb != null ? rsb.rsb!.toStringAsFixed(1) : '—', color: _rsbColor),
              ],
            ),
            if (history.isNotEmpty) ...[
              const SizedBox(height: 12),
              SizedBox(
                height: 40,
                child: LineChart(
                  LineChartData(
                    gridData: const FlGridData(show: false),
                    titlesData: const FlTitlesData(show: false),
                    borderData: FlBorderData(show: false),
                    lineTouchData: const LineTouchData(enabled: false),
                    lineBarsData: [
                      LineChartBarData(
                        spots: history.asMap().entries
                            .where((e) => e.value.rsb != null)
                            .map((e) => FlSpot(e.key.toDouble(), e.value.rsb!))
                            .toList(),
                        isCurved: true,
                        color: const Color(0xFF2E7D32),
                        barWidth: 2,
                        dotData: const FlDotData(show: false),
                        belowBarData: BarAreaData(
                          show: true,
                          color: const Color(0xFF2E7D32).withOpacity(0.1),
                        ),
                      ),
                      LineChartBarData(
                        spots: history.asMap().entries
                            .where((e) => e.value.ctl != null)
                            .map((e) => FlSpot(e.key.toDouble(), e.value.ctl!))
                            .toList(),
                        isCurved: true,
                        color: const Color(0xFF6750A4),
                        barWidth: 1.5,
                        dashArray: [4, 4],
                        dotData: const FlDotData(show: false),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _statChip(String label, String value, {Color? color}) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: const TextStyle(fontSize: 10, color: Color(0xFF888888))),
      Text(value, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: color ?? const Color(0xFF1A1A1A))),
    ],
  );
}
```

- [ ] **Step 2: Create `mobile/lib/widgets/run_summary_card.dart`**

```dart
import 'package:flutter/material.dart';
import '../models/run.dart';

class RunSummaryCard extends StatelessWidget {
  final Run run;
  final VoidCallback onTap;
  final String? label;

  const RunSummaryCard({required this.run, required this.onTap, this.label, super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (label != null)
                Text(label!.toUpperCase(),
                    style: const TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
              if (label != null) const SizedBox(height: 4),
              Row(
                children: [
                  Expanded(
                    child: Text(run.name,
                        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                  ),
                  const Icon(Icons.chevron_right, size: 18, color: Color(0xFF888888)),
                ],
              ),
              const SizedBox(height: 2),
              Text(_formatDate(run.date), style: const TextStyle(fontSize: 12, color: Color(0xFF888888))),
              const SizedBox(height: 10),
              Row(
                children: [
                  _metric('${run.distanceKm?.toStringAsFixed(1) ?? '—'} km', 'dist'),
                  _metric(run.durationFormatted, 'time'),
                  if (run.avgPowerW != null) _metric('${run.avgPowerW}W', 'power'),
                  if (run.avgHr != null) _metric('${run.avgHr}', 'HR'),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _metric(String value, String label) => Expanded(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(value, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
        Text(label, style: const TextStyle(fontSize: 10, color: Color(0xFF888888))),
      ],
    ),
  );

  String _formatDate(String isoDate) {
    try {
      final dt = DateTime.parse(isoDate);
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
      return '${days[dt.weekday - 1]} ${dt.day} ${months[dt.month - 1]} ${dt.year}';
    } catch (_) {
      return isoDate;
    }
  }
}
```

- [ ] **Step 3: Create `mobile/lib/widgets/next_workout_card.dart`**

```dart
import 'package:flutter/material.dart';
import '../models/planned_workout.dart';

class NextWorkoutCard extends StatelessWidget {
  final PlannedWorkout workout;
  const NextWorkoutCard({required this.workout, super.key});

  String _formatDate(String isoDate) {
    try {
      final dt = DateTime.parse(isoDate);
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
      return '${days[dt.weekday - 1]} ${dt.day} ${months[dt.month - 1]}';
    } catch (_) {
      return isoDate;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: const Border(left: BorderSide(color: Color(0xFFF59E0B), width: 3)),
        ),
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('NEXT · ${_formatDate(workout.date)}'.toUpperCase(),
                style: const TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Text(workout.name, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
            if (workout.description.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(workout.description, style: const TextStyle(fontSize: 12, color: Color(0xFFB45309))),
            ],
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Verify widgets compile**

```bash
cd mobile
flutter analyze lib/widgets/
```

Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/widgets/rsb_card.dart mobile/lib/widgets/run_summary_card.dart mobile/lib/widgets/next_workout_card.dart
git commit -m "feat: add RSB card, run summary card, and next workout card widgets"
```

---

### Task 8: Home screen

**Files:**
- Modify: `mobile/lib/screens/home_screen.dart`

- [ ] **Step 1: Implement `home_screen.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/dashboard_provider.dart';
import '../widgets/rsb_card.dart';
import '../widgets/run_summary_card.dart';
import '../widgets/next_workout_card.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dashAsync = ref.watch(dashboardProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('RunCoach', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 20)),
            Text('Your AI running coach', style: TextStyle(fontSize: 12, color: Color(0xFF888888))),
          ],
        ),
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
      ),
      body: dashAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (dashboard) => RefreshIndicator(
          onRefresh: () => ref.refresh(dashboardProvider.future),
          child: ListView(
            children: [
              const SizedBox(height: 8),
              RsbCard(summary: dashboard.trainingSummary),
              if (dashboard.latestRun != null) ...[
                const SizedBox(height: 4),
                RunSummaryCard(
                  run: dashboard.latestRun!,
                  label: 'Latest Run',
                  onTap: () => context.push('/home/run/${dashboard.latestRun!.id}'),
                ),
              ],
              if (dashboard.nextWorkout != null) ...[
                const SizedBox(height: 4),
                NextWorkoutCard(workout: dashboard.nextWorkout!),
              ],
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Test Home screen on emulator**

Run the app, verify:
- RSB card shows with training status and sparkline
- Latest run card shows and tapping navigates to (stub) RunDetail
- Next workout card shows if available
- Pull-to-refresh works

- [ ] **Step 3: Commit**

```bash
git add mobile/lib/screens/home_screen.dart
git commit -m "feat: implement Home screen with dashboard data"
```

---

### Task 9: Year/month chips and Activities screen

**Files:**
- Create: `mobile/lib/widgets/year_month_chips.dart`
- Modify: `mobile/lib/screens/activities_screen.dart`

- [ ] **Step 1: Create `mobile/lib/widgets/year_month_chips.dart`**

```dart
import 'package:flutter/material.dart';

class YearMonthChips extends StatelessWidget {
  final int? selectedYear;
  final int? selectedMonth;
  final List<Map<String, int>> available; // [{year, month, count}]
  final void Function(int? year, int? month) onChanged;

  const YearMonthChips({
    required this.available,
    required this.selectedYear,
    required this.selectedMonth,
    required this.onChanged,
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    final years = available.map((e) => e['year']!).toSet().toList()..sort((a, b) => b.compareTo(a));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: years.map((year) => Padding(
              padding: const EdgeInsets.only(right: 8),
              child: FilterChip(
                label: Text('$year'),
                selected: selectedYear == year,
                onSelected: (_) => onChanged(year, null),
              ),
            )).toList(),
          ),
        ),
        if (selectedYear != null) ...[
          const SizedBox(height: 4),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: _monthsForYear(selectedYear!).map((month) => Padding(
                padding: const EdgeInsets.only(right: 8),
                child: FilterChip(
                  label: Text(_monthName(month)),
                  selected: selectedMonth == month,
                  onSelected: (_) => onChanged(selectedYear, selectedMonth == month ? null : month),
                ),
              )).toList(),
            ),
          ),
        ],
      ],
    );
  }

  List<int> _monthsForYear(int year) {
    return available
        .where((e) => e['year'] == year)
        .map((e) => e['month']!)
        .toList()
      ..sort((a, b) => b.compareTo(a));
  }

  String _monthName(int month) {
    const names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return names[month];
  }
}
```

- [ ] **Step 2: Implement `activities_screen.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/runs_provider.dart';
import '../providers/auth_provider.dart';
import '../models/run.dart';
import '../widgets/year_month_chips.dart';

final _yearMonthSummaryProvider = FutureProvider.autoDispose<List<Map<String, int>>>((ref) async {
  final api = ref.read(apiServiceProvider);
  // The existing API has GET /runs which returns pagination — we derive year/month from loaded runs
  // Use a lightweight summary if available, otherwise derive from first page
  final result = await api.getRuns(perPage: 100);
  final runs = result['runs'] as List<Run>;
  final map = <String, Map<String, int>>{};
  for (final r in runs) {
    try {
      final dt = DateTime.parse(r.date);
      final key = '${dt.year}-${dt.month}';
      map[key] = {'year': dt.year, 'month': dt.month, 'count': (map[key]?['count'] ?? 0) + 1};
    } catch (_) {}
  }
  return map.values.toList()..sort((a, b) {
    final yCmp = b['year']!.compareTo(a['year']!);
    return yCmp != 0 ? yCmp : b['month']!.compareTo(a['month']!);
  });
});

class ActivitiesScreen extends ConsumerWidget {
  const ActivitiesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(runsFilterProvider);
    final runsState = ref.watch(runsProvider);
    final ymAsync = ref.watch(_yearMonthSummaryProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Activities', style: TextStyle(fontWeight: FontWeight.w700)),
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        actions: [
          IconButton(
            icon: const Icon(Icons.sync),
            tooltip: 'Sync Now',
            onPressed: () async {
              await ref.read(apiServiceProvider).triggerSync();
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Sync started')),
                );
              }
            },
          ),
        ],
      ),
      body: Column(
        children: [
          const SizedBox(height: 8),
          ymAsync.when(
            loading: () => const SizedBox(height: 40),
            error: (_, __) => const SizedBox.shrink(),
            data: (ym) => YearMonthChips(
              available: ym,
              selectedYear: filter.year,
              selectedMonth: filter.month,
              onChanged: (year, month) {
                ref.read(runsFilterProvider.notifier).state = RunsFilter(year: year, month: month);
              },
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: _RunList(runsState: runsState, onLoadMore: () => ref.read(runsProvider.notifier).loadMore()),
          ),
        ],
      ),
    );
  }
}

class _RunList extends StatelessWidget {
  final RunsState runsState;
  final VoidCallback onLoadMore;

  const _RunList({required this.runsState, required this.onLoadMore});

  @override
  Widget build(BuildContext context) {
    if (runsState.runs.isEmpty && runsState.isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (runsState.error != null && runsState.runs.isEmpty) {
      return Center(child: Text('Error: ${runsState.error}'));
    }

    final grouped = <String, List<Run>>{};
    for (final run in runsState.runs) {
      try {
        final dt = DateTime.parse(run.date);
        const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        final key = '${months[dt.month - 1]} ${dt.year}';
        grouped.putIfAbsent(key, () => []).add(run);
      } catch (_) {
        grouped.putIfAbsent('Unknown', () => []).add(run);
      }
    }

    final sections = grouped.entries.toList();

    return ListView.builder(
      itemCount: sections.fold(0, (sum, e) => sum + e.value.length + 1) + (runsState.hasMore ? 1 : 0),
      itemBuilder: (context, idx) {
        int cursor = 0;
        for (final section in sections) {
          if (idx == cursor) {
            return Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Text(section.key,
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600,
                      color: Color(0xFF888888), letterSpacing: 0.5)),
            );
          }
          cursor++;
          for (final run in section.value) {
            if (idx == cursor) {
              return _RunRow(run: run, onTap: () => context.push('/activities/run/${run.id}'));
            }
            cursor++;
          }
        }
        // Load more trigger
        if (runsState.hasMore) {
          WidgetsBinding.instance.addPostFrameCallback((_) => onLoadMore());
          return const Padding(
            padding: EdgeInsets.all(16),
            child: Center(child: CircularProgressIndicator()),
          );
        }
        return null;
      },
    );
  }
}

class _RunRow extends StatelessWidget {
  final Run run;
  final VoidCallback onTap;

  const _RunRow({required this.run, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 3),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(run.name,
                        style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 2),
                    Text(
                      '${run.distanceKm?.toStringAsFixed(1) ?? '—'} km · ${run.durationFormatted}'
                      '${run.avgPowerW != null ? ' · ${run.avgPowerW}W' : ''}'
                      '${run.avgHr != null ? ' · HR ${run.avgHr}' : ''}',
                      style: const TextStyle(fontSize: 12, color: Color(0xFF888888)),
                    ),
                  ],
                ),
              ),
              _stageBadge(run.stage),
              const SizedBox(width: 4),
              const Icon(Icons.chevron_right, size: 16, color: Color(0xFF888888)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _stageBadge(RunStage stage) {
    final (label, color) = switch (stage) {
      RunStage.analyzed => ('analysed', const Color(0xFF2E7D32)),
      RunStage.parsed => ('parsed', const Color(0xFFF59E0B)),
      RunStage.synced => ('synced', const Color(0xFF888888)),
      RunStage.error => ('error', const Color(0xFFEF4444)),
      _ => ('—', const Color(0xFF888888)),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(label, style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600)),
    );
  }
}
```

- [ ] **Step 3: Test Activities screen on emulator**

Run the app, verify:
- Activities list loads with runs grouped by month
- Year chips appear; selecting a year filters the list
- Month chips appear below the year row; selecting filters further
- Infinite scroll loads more runs when reaching the bottom
- Sync Now button shows a snackbar

- [ ] **Step 4: Commit**

```bash
git add mobile/lib/widgets/year_month_chips.dart mobile/lib/screens/activities_screen.dart
git commit -m "feat: implement Activities screen with year/month filtering and pagination"
```

---

### Task 10: Profile screen

**Files:**
- Modify: `mobile/lib/screens/profile_screen.dart`

- [ ] **Step 1: Implement `profile_screen.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import '../providers/auth_provider.dart';

// Add url_launcher to pubspec.yaml first — see step below
final _profileDataProvider = FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  return api.getAthleteProfile();
});

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profileAsync = ref.watch(_profileDataProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Profile', style: TextStyle(fontWeight: FontWeight.w700)),
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
      ),
      body: profileAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (profile) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Athlete info
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('ATHLETE', style: TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Text(
                      profile['display_name'] as String? ?? profile['username'] as String? ?? '',
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 4),
                    Text(profile['username'] as String? ?? '',
                        style: const TextStyle(fontSize: 13, color: Color(0xFF888888))),
                    if ((profile['profile'] as String?)?.isNotEmpty == true) ...[
                      const SizedBox(height: 12),
                      const Divider(),
                      const SizedBox(height: 8),
                      Text(profile['profile'] as String,
                          style: const TextStyle(fontSize: 13, color: Color(0xFF444444))),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),

            // Connected services
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('CONNECTED SERVICES', style: TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        if (profile['strava_athlete_id'] != null)
                          _ServiceButton(
                            label: 'STRAVA',
                            color: const Color(0xFFFC4C02),
                            onTap: () => launchUrl(Uri.parse('https://www.strava.com/athletes/${profile['strava_athlete_id']}')),
                          ),
                        const SizedBox(width: 12),
                        _ServiceButton(
                          label: 'STRYD',
                          color: const Color(0xFF00A0DF),
                          onTap: () => launchUrl(Uri.parse('https://www.stryd.com')),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),

            // App actions
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('APP', style: TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.sync),
                        label: const Text('Sync Now'),
                        onPressed: () async {
                          await ref.read(apiServiceProvider).triggerSync();
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Sync started')),
                            );
                          }
                        },
                      ),
                    ),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.logout, color: Color(0xFFEF4444)),
                        label: const Text('Logout', style: TextStyle(color: Color(0xFFEF4444))),
                        style: OutlinedButton.styleFrom(side: const BorderSide(color: Color(0xFFEF4444))),
                        onPressed: () async {
                          await ref.read(authProvider.notifier).logout();
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),

            // Notifications placeholder (reserved for future firebase_messaging integration)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: const [
                    Text('NOTIFICATIONS', style: TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
                    SizedBox(height: 8),
                    Text('Coming soon', style: TextStyle(fontSize: 13, color: Color(0xFFBBBBBB))),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ServiceButton extends StatelessWidget {
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _ServiceButton({required this.label, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: onTap,
      style: ElevatedButton.styleFrom(
        backgroundColor: color,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      ),
      child: Text(label, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
    );
  }
}
```

- [ ] **Step 2: Add `url_launcher` to pubspec.yaml**

In `mobile/pubspec.yaml`, add to `dependencies:`:

```yaml
  url_launcher: ^6.3.0
```

Then run:

```bash
cd mobile
flutter pub get
```

- [ ] **Step 3: Test Profile screen on emulator**

Verify: athlete name, profile text, STRAVA/STRYD buttons (STRAVA hidden if no strava_athlete_id), Sync Now snackbar, Logout redirects to Login.

- [ ] **Step 4: Commit**

```bash
git add mobile/lib/screens/profile_screen.dart mobile/pubspec.yaml mobile/pubspec.lock
git commit -m "feat: implement Profile screen with athlete info, service links, sync, and logout"
```

---

### Task 11: Run Detail widgets — HR zones bar, block card, route map, coaching chat

**Files:**
- Create: `mobile/lib/widgets/hr_zones_bar.dart`
- Create: `mobile/lib/widgets/block_card.dart`
- Create: `mobile/lib/widgets/route_map_widget.dart`
- Create: `mobile/lib/widgets/coaching_chat_widget.dart`

- [ ] **Step 1: Create `mobile/lib/widgets/hr_zones_bar.dart`**

The YAML data structure stores HR zone percentages. The key in yaml_data to look for is `hr_zone_distribution` which is a map like `{"z1": 8.2, "z2": 12.1, ...}`.

```dart
import 'package:flutter/material.dart';

class HrZonesBar extends StatelessWidget {
  final Map<String, dynamic> hrZones;
  const HrZonesBar({required this.hrZones, super.key});

  static const _zoneColors = [
    Color(0xFF60A5FA), // Z1 blue
    Color(0xFF34D399), // Z2 green
    Color(0xFFFBBF24), // Z3 yellow
    Color(0xFFF97316), // Z4 orange
    Color(0xFFEF4444), // Z5 red
  ];

  @override
  Widget build(BuildContext context) {
    final zones = [
      (hrZones['z1'] as num?)?.toDouble() ?? 0.0,
      (hrZones['z2'] as num?)?.toDouble() ?? 0.0,
      (hrZones['z3'] as num?)?.toDouble() ?? 0.0,
      (hrZones['z4'] as num?)?.toDouble() ?? 0.0,
      (hrZones['z5'] as num?)?.toDouble() ?? 0.0,
    ];
    final total = zones.fold(0.0, (a, b) => a + b);
    if (total == 0) return const SizedBox.shrink();

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('HR ZONES', style: TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(5),
              child: Row(
                children: zones.asMap().entries.map((e) {
                  final pct = e.value / total;
                  return Expanded(
                    flex: (pct * 1000).toInt(),
                    child: Container(height: 12, color: _zoneColors[e.key]),
                  );
                }).toList(),
              ),
            ),
            const SizedBox(height: 6),
            Row(
              children: zones.asMap().entries.map((e) => Expanded(
                child: Text(
                  'Z${e.key + 1}\n${e.value.toStringAsFixed(0)}%',
                  style: const TextStyle(fontSize: 9, color: Color(0xFF888888)),
                  textAlign: TextAlign.center,
                ),
              )).toList(),
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Create `mobile/lib/widgets/block_card.dart`**

```dart
import 'package:flutter/material.dart';
import '../models/workout_block.dart';

class BlockCard extends StatelessWidget {
  final WorkoutBlock block;
  const BlockCard({required this.block, super.key});

  Color get _borderColor => switch (block.blockType) {
    BlockType.warmup || BlockType.cooldown => const Color(0xFF2563EB),
    BlockType.work => const Color(0xFFF97316),
    BlockType.rest => const Color(0xFF9CA3AF),
    _ => const Color(0xFFCCCCCC),
  };

  String get _typeLabel => block.type.toUpperCase();

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 3),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border(left: BorderSide(color: _borderColor, width: 3)),
        ),
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_typeLabel,
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700,
                        color: _borderColor, letterSpacing: 0.5)),
                Text(block.formattedDuration,
                    style: const TextStyle(fontSize: 12, color: Color(0xFF888888))),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                if (block.avgPowerW != null)
                  _metric('${block.avgPowerW}W', 'power'),
                if (block.targetPowerLow != null && block.targetPowerHigh != null)
                  _metric('${block.targetPowerLow!.toInt()}–${block.targetPowerHigh!.toInt()}W', 'target'),
                if (block.avgHr != null)
                  _metric('${block.avgHr}', 'HR'),
                _metric(block.formattedPace, 'pace'),
              ],
            ),
            if (block.powerCompliance != null) ...[
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: Row(
                  children: [
                    Expanded(
                      flex: (block.powerCompliance!.belowPct * 10).toInt(),
                      child: Container(height: 5, color: const Color(0xFF60A5FA)),
                    ),
                    Expanded(
                      flex: (block.powerCompliance!.inZonePct * 10).toInt(),
                      child: Container(height: 5, color: const Color(0xFF4ADE80)),
                    ),
                    Expanded(
                      flex: (block.powerCompliance!.abovePct * 10).toInt(),
                      child: Container(height: 5, color: const Color(0xFFF97316)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 3),
              Text(
                '${block.powerCompliance!.belowPct.toStringAsFixed(0)}% below · '
                '${block.powerCompliance!.inZonePct.toStringAsFixed(0)}% in zone · '
                '${block.powerCompliance!.abovePct.toStringAsFixed(0)}% above',
                style: const TextStyle(fontSize: 9, color: Color(0xFF888888)),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _metric(String value, String label) => Padding(
    padding: const EdgeInsets.only(right: 16),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(value, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        Text(label, style: const TextStyle(fontSize: 9, color: Color(0xFF888888))),
      ],
    ),
  );
}
```

- [ ] **Step 3: Create `mobile/lib/widgets/route_map_widget.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

class RouteMapWidget extends StatelessWidget {
  final String encodedPolyline;
  const RouteMapWidget({required this.encodedPolyline, super.key});

  List<LatLng> _decode(String encoded) {
    final List<LatLng> points = [];
    int index = 0, lat = 0, lng = 0;
    while (index < encoded.length) {
      int shift = 0, result = 0, b;
      do {
        b = encoded.codeUnitAt(index++) - 63;
        result |= (b & 0x1F) << shift;
        shift += 5;
      } while (b >= 0x20);
      lat += (result & 1) != 0 ? ~(result >> 1) : (result >> 1);
      shift = 0; result = 0;
      do {
        b = encoded.codeUnitAt(index++) - 63;
        result |= (b & 0x1F) << shift;
        shift += 5;
      } while (b >= 0x20);
      lng += (result & 1) != 0 ? ~(result >> 1) : (result >> 1);
      points.add(LatLng(lat / 1E5, lng / 1E5));
    }
    return points;
  }

  @override
  Widget build(BuildContext context) {
    final points = _decode(encodedPolyline);
    if (points.isEmpty) return const SizedBox.shrink();

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      clipBehavior: Clip.hardEdge,
      child: SizedBox(
        height: 160,
        child: FlutterMap(
          options: MapOptions(
            initialCameraFit: CameraFit.coordinates(
              coordinates: points,
              padding: const EdgeInsets.all(16),
            ),
            interactionOptions: const InteractionOptions(flags: InteractiveFlag.none),
          ),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'com.runcoach.app',
            ),
            PolylineLayer(
              polylines: [
                Polyline(points: points, color: const Color(0xFF6750A4), strokeWidth: 3),
              ],
            ),
            MarkerLayer(markers: [
              Marker(point: points.first, child: const Icon(Icons.circle, color: Color(0xFF4ADE80), size: 12)),
              Marker(point: points.last, child: const Icon(Icons.circle, color: Color(0xFFEF4444), size: 12)),
            ]),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Create `mobile/lib/widgets/coaching_chat_widget.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../providers/chat_provider.dart';
import '../models/run.dart';

class CoachingChatWidget extends ConsumerStatefulWidget {
  final Run run;
  const CoachingChatWidget({required this.run, super.key});

  @override
  ConsumerState<CoachingChatWidget> createState() => _CoachingChatWidgetState();
}

class _CoachingChatWidgetState extends ConsumerState<CoachingChatWidget> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final chatState = ref.watch(chatProvider(widget.run.id));

    ref.listen(chatProvider(widget.run.id), (_, __) => _scrollToBottom());

    return Column(
      children: [
        Expanded(
          child: ListView(
            controller: _scrollController,
            padding: const EdgeInsets.all(16),
            children: [
              // AI commentary as the first message
              if (widget.run.stage == RunStage.analyzed && widget.run.commentary != null)
                _AiCommentaryBubble(
                  commentary: widget.run.commentary!,
                  timestamp: widget.run.analyzedAt,
                ),
              if (widget.run.stage != RunStage.analyzed)
                const Padding(
                  padding: EdgeInsets.all(32),
                  child: Center(child: Text('Analysis not yet available',
                      style: TextStyle(color: Color(0xFF888888)))),
                ),
              // Chat history
              if (chatState.isLoading)
                const Center(child: CircularProgressIndicator()),
              ...chatState.messages.map((msg) => msg.isUser
                  ? _UserBubble(message: msg.message)
                  : _AiBubble(message: msg.message)),
              if (chatState.isSending)
                const Padding(
                  padding: EdgeInsets.only(top: 8),
                  child: Row(children: [
                    SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                    SizedBox(width: 8),
                    Text('Thinking…', style: TextStyle(color: Color(0xFF888888), fontSize: 12)),
                  ]),
                ),
            ],
          ),
        ),
        if (widget.run.stage == RunStage.analyzed)
          _ChatInput(
            controller: _controller,
            onSend: () {
              final text = _controller.text.trim();
              if (text.isEmpty) return;
              ref.read(chatProvider(widget.run.id).notifier).send(text);
              _controller.clear();
            },
          ),
      ],
    );
  }
}

class _AiCommentaryBubble extends StatelessWidget {
  final String commentary;
  final String? timestamp;

  const _AiCommentaryBubble({required this.commentary, this.timestamp});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.06), blurRadius: 4)],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 14,
                backgroundColor: const Color(0xFF6750A4),
                child: const Text('AI', style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: 8),
              const Text('RunCoach', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Color(0xFF6750A4))),
              const Spacer(),
              if (timestamp != null)
                Text(_formatTimestamp(timestamp!),
                    style: const TextStyle(fontSize: 10, color: Color(0xFFAAAAAA))),
            ],
          ),
          const SizedBox(height: 10),
          MarkdownBody(
            data: commentary,
            styleSheet: MarkdownStyleSheet(
              p: const TextStyle(fontSize: 13, color: Color(0xFF222222), height: 1.5),
              strong: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: Color(0xFF111111)),
            ),
          ),
        ],
      ),
    );
  }

  String _formatTimestamp(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      return '${dt.day} ${months[dt.month - 1]}, ${dt.hour}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }
}

class _UserBubble extends StatelessWidget {
  final String message;
  const _UserBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8, left: 48),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: const BoxDecoration(
          color: Color(0xFF6750A4),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(14),
            topRight: Radius.circular(14),
            bottomLeft: Radius.circular(14),
            bottomRight: Radius.circular(3),
          ),
        ),
        child: Text(message, style: const TextStyle(color: Colors.white, fontSize: 13, height: 1.4)),
      ),
    );
  }
}

class _AiBubble extends StatelessWidget {
  final String message;
  const _AiBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8, right: 48),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(14),
            topRight: Radius.circular(14),
            bottomLeft: Radius.circular(3),
            bottomRight: Radius.circular(14),
          ),
          boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.06), blurRadius: 4)],
        ),
        child: Text(message, style: const TextStyle(fontSize: 13, color: Color(0xFF222222), height: 1.4)),
      ),
    );
  }
}

class _ChatInput extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSend;

  const _ChatInput({required this.controller, required this.onSend});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      color: Colors.white,
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              decoration: const InputDecoration(
                hintText: 'Ask a follow-up question…',
                border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(24))),
                contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                isDense: true,
              ),
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => onSend(),
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            onPressed: onSend,
            style: FilledButton.styleFrom(
              shape: const CircleBorder(),
              padding: const EdgeInsets.all(12),
            ),
            child: const Icon(Icons.arrow_upward, size: 18),
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 5: Verify widgets compile**

```bash
cd mobile
flutter analyze lib/widgets/
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add mobile/lib/widgets/
git commit -m "feat: add HR zones bar, block card, route map, and coaching chat widgets"
```

---

### Task 12: Run Detail screen

**Files:**
- Modify: `mobile/lib/screens/run_detail_screen.dart`

- [ ] **Step 1: Check the YAML data structure for blocks and HR zones**

The `yaml_data` from the API is the parsed YAML from `fit_parser.py`. Check the structure:

```bash
source .venv/bin/activate
python -c "
import yaml, glob
files = glob.glob('data/activities/**/*.yaml', recursive=True)
if files:
    with open(files[0]) as f:
        d = yaml.safe_load(f)
    print('Top-level keys:', list(d.keys()))
    if 'blocks' in d and d['blocks']:
        print('Block keys:', list(d['blocks'][0].keys()))
        if 'power_compliance' in d['blocks'][0]:
            print('Compliance keys:', list(d['blocks'][0]['power_compliance'].keys()))
    if 'hr_zone_distribution' in d:
        print('HR zones:', d['hr_zone_distribution'])
"
```

Note the exact key names for `hr_zone_distribution`, block fields (`avg_power_w`, `avg_hr`, `duration_s`, `type`), and compliance fields. Adjust `WorkoutBlock.fromJson` and `HrZonesBar` in the preceding tasks if key names differ.

- [ ] **Step 2: Implement `run_detail_screen.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import '../providers/run_detail_provider.dart';
import '../models/run.dart';
import '../models/workout_block.dart';
import '../widgets/hr_zones_bar.dart';
import '../widgets/block_card.dart';
import '../widgets/route_map_widget.dart';
import '../widgets/coaching_chat_widget.dart';

class RunDetailScreen extends ConsumerStatefulWidget {
  final int runId;
  const RunDetailScreen({required this.runId, super.key});

  @override
  ConsumerState<RunDetailScreen> createState() => _RunDetailScreenState();
}

class _RunDetailScreenState extends ConsumerState<RunDetailScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final runAsync = ref.watch(runDetailProvider(widget.runId));

    return runAsync.when(
      loading: () => const Scaffold(body: Center(child: CircularProgressIndicator())),
      error: (e, _) => Scaffold(body: Center(child: Text('Error: $e'))),
      data: (run) => Scaffold(
        appBar: AppBar(
          backgroundColor: Colors.white,
          surfaceTintColor: Colors.transparent,
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(run.name,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
              Text(_formatDate(run.date), style: const TextStyle(fontSize: 11, color: Color(0xFF888888))),
            ],
          ),
          actions: [
            if (run.stravaActivityId != null)
              TextButton(
                onPressed: () => launchUrl(Uri.parse('https://www.strava.com/activities/${run.stravaActivityId}')),
                style: TextButton.styleFrom(foregroundColor: const Color(0xFFFC4C02)),
                child: const Text('STRAVA', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
              ),
            if (run.strydActivityId != null)
              TextButton(
                onPressed: () => launchUrl(Uri.parse('https://www.stryd.com/training/run/${run.strydActivityId}')),
                style: TextButton.styleFrom(foregroundColor: const Color(0xFF00A0DF)),
                child: const Text('STRYD', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
              ),
          ],
          bottom: TabBar(
            controller: _tabs,
            labelColor: const Color(0xFF6750A4),
            unselectedLabelColor: const Color(0xFF888888),
            indicatorColor: const Color(0xFF6750A4),
            tabs: const [Tab(text: 'Overview'), Tab(text: 'Blocks'), Tab(text: 'Coaching')],
          ),
        ),
        body: TabBarView(
          controller: _tabs,
          children: [
            _OverviewTab(run: run),
            _BlocksTab(run: run),
            CoachingChatWidget(run: run),
          ],
        ),
      ),
    );
  }

  String _formatDate(String isoDate) {
    try {
      final dt = DateTime.parse(isoDate);
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
      return '${days[dt.weekday - 1]} ${dt.day} ${months[dt.month - 1]} ${dt.year}';
    } catch (_) {
      return isoDate;
    }
  }
}

class _OverviewTab extends StatelessWidget {
  final Run run;
  const _OverviewTab({required this.run});

  @override
  Widget build(BuildContext context) {
    final yaml = run.yamlData;

    return ListView(
      children: [
        const SizedBox(height: 8),
        // 4-metric row
        Card(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            child: Row(
              children: [
                _metric('${run.distanceKm?.toStringAsFixed(1) ?? '—'}', 'km'),
                _metric(run.durationFormatted, 'time'),
                if (run.avgPowerW != null) _metric('${run.avgPowerW}W', 'power'),
                if (run.avgHr != null) _metric('${run.avgHr}', 'HR'),
              ],
            ),
          ),
        ),
        // Badges
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: Row(
            children: [
              if (run.strydRss != null)
                _badge('RSS ${run.strydRss!.toStringAsFixed(1)}', const Color(0xFF6750A4)),
              const SizedBox(width: 8),
              _stageBadge(run.stage),
            ],
          ),
        ),
        // HR zones
        if (yaml != null && yaml['hr_zone_distribution'] != null)
          HrZonesBar(hrZones: yaml['hr_zone_distribution'] as Map<String, dynamic>),
        // Stryd prescribed workout
        if (yaml != null && yaml['prescribed_workout'] != null)
          _StrydWorkoutCard(prescribed: yaml['prescribed_workout'] as Map<String, dynamic>),
        // Route map — polyline comes from run directly (stored in runs.strava_map_polyline)
        if (run.stravaMapPolyline != null)
          RouteMapWidget(encodedPolyline: run.stravaMapPolyline!),
        const SizedBox(height: 16),
      ],
    );
  }

  Widget _metric(String value, String label) => Expanded(
    child: Column(
      children: [
        Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        Text(label, style: const TextStyle(fontSize: 10, color: Color(0xFF888888))),
      ],
    ),
  );

  Widget _badge(String text, Color color) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
    decoration: BoxDecoration(color: color.withOpacity(0.12), borderRadius: BorderRadius.circular(20)),
    child: Text(text, style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600)),
  );

  Widget _stageBadge(RunStage stage) {
    final (label, color) = switch (stage) {
      RunStage.analyzed => ('✓ analysed', const Color(0xFF2E7D32)),
      RunStage.parsed => ('parsed', const Color(0xFFF59E0B)),
      RunStage.synced => ('synced', const Color(0xFF888888)),
      RunStage.error => ('error', const Color(0xFFEF4444)),
      _ => ('—', const Color(0xFF888888)),
    };
    return _badge(label, color);
  }
}

class _StrydWorkoutCard extends StatelessWidget {
  final Map<String, dynamic> prescribed;
  const _StrydWorkoutCard({required this.prescribed});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Container(
        decoration: const BoxDecoration(
          borderRadius: BorderRadius.all(Radius.circular(12)),
          border: Border(left: BorderSide(color: Color(0xFF00A0DF), width: 3)),
        ),
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('STRYD PRESCRIBED WORKOUT',
                style: TextStyle(fontSize: 10, color: Color(0xFF0077A8), letterSpacing: 1, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Text(prescribed['title'] as String? ?? '',
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
            if ((prescribed['description'] as String?)?.isNotEmpty == true) ...[
              const SizedBox(height: 4),
              Text(prescribed['description'] as String,
                  style: const TextStyle(fontSize: 12, color: Color(0xFF555555))),
            ],
          ],
        ),
      ),
    );
  }
}

class _BlocksTab extends StatelessWidget {
  final Run run;
  const _BlocksTab({required this.run});

  @override
  Widget build(BuildContext context) {
    final yaml = run.yamlData;
    if (yaml == null || yaml['blocks'] == null) {
      return const Center(child: Text('No block data available',
          style: TextStyle(color: Color(0xFF888888))));
    }

    final blocks = (yaml['blocks'] as List<dynamic>)
        .map((e) => WorkoutBlock.fromJson(e as Map<String, dynamic>))
        .toList();

    return ListView.builder(
      padding: const EdgeInsets.only(top: 8, bottom: 24),
      itemCount: blocks.length,
      itemBuilder: (_, i) => BlockCard(block: blocks[i]),
    );
  }
}
```

- [ ] **Step 3: Check the Stryd activity URL format**

The Stryd web app URL for an activity may differ from the pattern used above. Check by opening a Stryd activity in the browser and copying the URL format, then update the `launchUrl` call in `run_detail_screen.dart` if needed. The `stryd_activity_id` in the DB is an integer.

- [ ] **Step 4: Test Run Detail screen on emulator**

Navigate to a run detail from both Home and Activities. Verify:
- Header shows run name, date, STRAVA/STRYD buttons (hidden when no ID)
- Overview: metrics, badges, HR zones, Stryd prescription card, route map
- Blocks: colour-coded cards with compliance bars on work blocks
- Coaching: AI commentary rendered as markdown, chat thread, input bar

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/screens/run_detail_screen.dart
git commit -m "feat: implement Run Detail screen with Overview, Blocks, and Coaching tabs"
```

---

### Task 13: Final integration check and polish

- [ ] **Step 1: Run Flutter analyze**

```bash
cd mobile
flutter analyze
```

Fix any warnings. Expected: no errors, at most minor info messages.

- [ ] **Step 2: Test the complete user journey on emulator**

Walk through the full journey:
1. Launch with no stored token → Login screen appears
2. Login with valid credentials → Home screen loads with RSB card and latest run
3. Tap latest run → RunDetail opens on Overview tab, STRAVA/STRYD buttons visible
4. Swipe to Blocks → workout blocks shown with compliance bars
5. Swipe to Coaching → commentary shown, type a follow-up question
6. Back → Activities tab, year/month chips, scroll down to load more
7. Profile tab → athlete info, STRAVA/STRYD buttons, Sync Now, Logout
8. Logout → Login screen

- [ ] **Step 3: Build release APK**

```bash
cd mobile
flutter build apk --release 2>&1 | tail -10
```

Expected: `✓ Built build/app/outputs/flutter-apk/app-release.apk`

- [ ] **Step 4: Final commit**

```bash
git add mobile/
git commit -m "feat: complete RunCoach Flutter Android app v1"
```

- [ ] **Step 5: Add `.superpowers/` to `.gitignore` if not already present**

```bash
grep -q '.superpowers' /home/colm/git/fitparser/.gitignore || echo '.superpowers/' >> /home/colm/git/fitparser/.gitignore
git add .gitignore
git commit -m "chore: ignore .superpowers/ brainstorm directory"
```
