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
