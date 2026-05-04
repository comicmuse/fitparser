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
        Card(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            child: Row(
              children: [
                _metric(run.distanceKm?.toStringAsFixed(1) ?? '—', 'km'),
                _metric(run.durationFormatted, 'time'),
                if (run.avgPowerW != null) _metric('${run.avgPowerW}W', 'power'),
                if (run.avgHr != null) _metric('${run.avgHr}', 'HR'),
              ],
            ),
          ),
        ),
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
        if (yaml != null && yaml['hr_zone_distribution'] != null)
          HrZonesBar(hrZones: yaml['hr_zone_distribution'] as Map<String, dynamic>),
        if (yaml != null && yaml['prescribed_workout'] != null)
          _StrydWorkoutCard(prescribed: yaml['prescribed_workout'] as Map<String, dynamic>),
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
    decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
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
