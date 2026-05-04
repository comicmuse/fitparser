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
    final dyn = yaml?['running_dynamics_summary'] as Map<String, dynamic>?;
    final hrZones = yaml?['session_hr_zones'] as Map<String, dynamic>?;
    final planned = run.plannedWorkout;

    String pace = '—';
    final distKm = (yaml?['distance_km'] as num?)?.toDouble() ?? run.distanceKm;
    final durMin = (yaml?['duration_min'] as num?)?.toDouble();
    if (distKm != null && distKm > 0 && durMin != null) {
      final secPerKm = (durMin * 60) / distKm;
      final m = secPerKm ~/ 60;
      final s = (secPerKm % 60).toInt();
      pace = '$m:${s.toString().padLeft(2, '0')}/km';
    }

    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        const SizedBox(height: 8),
        // Stage badge
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
          child: _stageBadge(run.stage),
        ),
        const SizedBox(height: 4),
        // Primary metrics grid
        _MetricSection(label: 'ACTIVITY', metrics: [
          _MetricTile(icon: Icons.straighten, label: 'Distance', value: run.distanceKm != null ? '${run.distanceKm!.toStringAsFixed(2)} km' : '—', color: const Color(0xFF6750A4)),
          _MetricTile(icon: Icons.timer_outlined, label: 'Duration', value: run.durationFormatted, color: const Color(0xFF6750A4)),
          _MetricTile(icon: Icons.speed_outlined, label: 'Pace', value: pace, color: const Color(0xFF6750A4)),
          _MetricTile(icon: Icons.favorite_outline, label: 'Avg HR', value: run.avgHr != null ? '${run.avgHr} bpm' : '—', color: const Color(0xFFEF4444)),
        ]),
        if (run.avgPowerW != null || yaml?['max_hr'] != null || yaml?['elev_gain_m'] != null || yaml?['calories_kcal'] != null)
          _MetricSection(label: 'PERFORMANCE', metrics: [
            if (run.avgPowerW != null) _MetricTile(icon: Icons.bolt_outlined, label: 'Avg Power', value: '${run.avgPowerW}W', color: const Color(0xFFF97316)),
            if (yaml?['max_hr'] != null) _MetricTile(icon: Icons.favorite, label: 'Max HR', value: '${(yaml!['max_hr'] as num).toInt()} bpm', color: const Color(0xFFEF4444)),
            if (yaml?['elev_gain_m'] != null) _MetricTile(icon: Icons.trending_up, label: 'Elev Gain', value: '${(yaml!['elev_gain_m'] as num).toInt()}m', color: const Color(0xFF2E7D32)),
            if (yaml?['calories_kcal'] != null) _MetricTile(icon: Icons.local_fire_department_outlined, label: 'Calories', value: '${(yaml!['calories_kcal'] as num).toInt()} kcal', color: const Color(0xFFF59E0B)),
          ]),
        if (yaml?['aerobic_te'] != null || yaml?['vo2_max'] != null || run.strydRss != null || yaml?['recovery_time_readable'] != null)
          _MetricSection(label: 'TRAINING LOAD', metrics: [
            if (yaml?['aerobic_te'] != null) _MetricTile(icon: Icons.air, label: 'Aerobic TE', value: (yaml!['aerobic_te'] as num).toStringAsFixed(1), color: const Color(0xFF0891B2)),
            if (yaml?['vo2_max'] != null) _MetricTile(icon: Icons.science_outlined, label: 'VO₂max', value: (yaml!['vo2_max'] as num).toStringAsFixed(1), color: const Color(0xFF0891B2)),
            if (run.strydRss != null) _MetricTile(icon: Icons.bar_chart, label: 'RSS', value: run.strydRss!.toStringAsFixed(1), color: const Color(0xFF6750A4)),
            if (yaml?['recovery_time_readable'] != null) _MetricTile(icon: Icons.bedtime_outlined, label: 'Recovery', value: yaml!['recovery_time_readable'] as String, color: const Color(0xFF7C3AED)),
          ]),
        if (dyn != null)
          _MetricSection(label: 'RUNNING DYNAMICS', metrics: [
            if (dyn['cadence_med'] != null) _MetricTile(icon: Icons.directions_run, label: 'Cadence', value: '${(dyn['cadence_med'] as num).toInt()} spm', color: const Color(0xFF059669)),
            if (dyn['gct_med'] != null) _MetricTile(icon: Icons.compress, label: 'GCT', value: '${(dyn['gct_med'] as num).toInt()} ms', color: const Color(0xFF059669)),
            if (dyn['vert_osc_med'] != null) _MetricTile(icon: Icons.swap_vert, label: 'Vert Osc', value: '${(dyn['vert_osc_med'] as num).toStringAsFixed(1)} cm', color: const Color(0xFF059669)),
            if (dyn['step_length_med'] != null) _MetricTile(icon: Icons.straighten, label: 'Stride', value: '${((dyn['step_length_med'] as num) * 100).toInt()} cm', color: const Color(0xFF059669)),
          ]),
        if (hrZones != null) HrZonesBar(hrZones: hrZones),
        if (run.stravaMapPolyline != null)
          RouteMapWidget(encodedPolyline: run.stravaMapPolyline!),
        if (planned != null) _StrydWorkoutCard(prescribed: planned),
      ],
    );
  }

  Widget _stageBadge(RunStage stage) {
    final (label, color) = switch (stage) {
      RunStage.analyzed => ('✓ analysed', const Color(0xFF2E7D32)),
      RunStage.parsed => ('parsed', const Color(0xFFF59E0B)),
      RunStage.synced => ('synced', const Color(0xFF888888)),
      RunStage.error => ('error', const Color(0xFFEF4444)),
      _ => ('—', const Color(0xFF888888)),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
      child: Text(label, style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600)),
    );
  }
}

class _MetricTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _MetricTile({required this.icon, required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(height: 6),
          Text(value, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: color)),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(fontSize: 10, color: Color(0xFF888888))),
        ],
      ),
    );
  }
}

class _MetricSection extends StatelessWidget {
  final String label;
  final List<_MetricTile> metrics;

  const _MetricSection({required this.label, required this.metrics});

  @override
  Widget build(BuildContext context) {
    if (metrics.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisSpacing: 8,
            mainAxisSpacing: 8,
            childAspectRatio: 2.2,
            children: metrics,
          ),
        ],
      ),
    );
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
    if (yaml == null) {
      return const Center(child: Text('No block data available',
          style: TextStyle(color: Color(0xFF888888))));
    }
    final blocksRaw = yaml['blocks'];
    if (blocksRaw == null) {
      return const Center(child: Text('No block data available',
          style: TextStyle(color: Color(0xFF888888))));
    }

    late final List<WorkoutBlock> blocks;
    if (blocksRaw is List) {
      blocks = blocksRaw
          .map((e) => WorkoutBlock.fromJson('', e as Map<String, dynamic>))
          .toList();
    } else if (blocksRaw is Map) {
      blocks = (blocksRaw as Map<String, dynamic>)
          .entries
          .map((e) => WorkoutBlock.fromJson(e.key, e.value as Map<String, dynamic>))
          .toList();
    } else {
      return const Center(child: Text('No block data available',
          style: TextStyle(color: Color(0xFF888888))));
    }

    blocks.sort((a, b) {
      if (a.startUtc == null && b.startUtc == null) return 0;
      if (a.startUtc == null) return 1;
      if (b.startUtc == null) return -1;
      return a.startUtc!.compareTo(b.startUtc!);
    });

    return ListView.builder(
      padding: const EdgeInsets.only(top: 8, bottom: 24),
      itemCount: blocks.length,
      itemBuilder: (_, i) => BlockCard(block: blocks[i]),
    );
  }
}
