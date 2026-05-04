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
