import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/runs_provider.dart';
import '../providers/auth_provider.dart';
import '../models/run.dart';
import '../widgets/year_month_chips.dart';

final _yearMonthSummaryProvider = FutureProvider.autoDispose<List<Map<String, int>>>((ref) async {
  final api = ref.read(apiServiceProvider);
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
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(label, style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600)),
    );
  }
}
