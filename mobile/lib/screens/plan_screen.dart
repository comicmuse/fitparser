import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../models/planned_workout.dart';
import '../providers/plan_provider.dart';
import '../widgets/plan_workout_card.dart';

class PlanScreen extends ConsumerWidget {
  const PlanScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final planAsync = ref.watch(planProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Plan',
          style: TextStyle(fontWeight: FontWeight.w700, color: Colors.white),
        ),
        backgroundColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        iconTheme: const IconThemeData(color: Colors.white),
        flexibleSpace: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              stops: [0.0, 0.38, 0.68, 1.0],
              colors: [
                Color(0xFF1c1917),
                Color(0xFF7c2d00),
                Color(0xFFea580c),
                Color(0xFFfed7aa),
              ],
            ),
          ),
        ),
      ),
      body: planAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (workouts) {
          if (workouts.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(32),
                child: Text(
                  'No upcoming workouts. Sync to fetch your training plan.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Color(0xFF888888)),
                ),
              ),
            );
          }
          final items = _buildItems(workouts);
          return RefreshIndicator(
            onRefresh: () => ref.refresh(planProvider.future),
            child: ListView.builder(
              itemCount: items.length,
              itemBuilder: (context, i) {
                final item = items[i];
                if (item is String) {
                  return Padding(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
                    child: Text(
                      item,
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF888888),
                        letterSpacing: 0.8,
                      ),
                    ),
                  );
                }
                final workout = item as PlannedWorkout;
                return PlanWorkoutCard(
                  workout: workout,
                  onTap: () => context.push('/workout-detail', extra: workout),
                );
              },
            ),
          );
        },
      ),
    );
  }

  List<Object> _buildItems(List<PlannedWorkout> workouts) {
    final items = <Object>[];
    String? lastHeader;
    for (final w in workouts) {
      final header = _weekHeader(w.date);
      if (header != lastHeader) {
        items.add(header);
        lastHeader = header;
      }
      items.add(w);
    }
    return items;
  }

  String _weekHeader(String isoDate) {
    try {
      final dt = DateTime.parse(isoDate);
      final monday = dt.subtract(Duration(days: dt.weekday - 1));
      const months = [
        'JAN',
        'FEB',
        'MAR',
        'APR',
        'MAY',
        'JUN',
        'JUL',
        'AUG',
        'SEP',
        'OCT',
        'NOV',
        'DEC',
      ];
      return 'WEEK OF ${monday.day} ${months[monday.month - 1]}';
    } catch (_) {
      return isoDate;
    }
  }
}
