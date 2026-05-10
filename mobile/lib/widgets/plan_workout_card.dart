import 'package:flutter/material.dart';
import '../models/planned_workout.dart';

class PlanWorkoutCard extends StatelessWidget {
  final PlannedWorkout workout;
  final VoidCallback onTap;

  const PlanWorkoutCard({
    required this.workout,
    required this.onTap,
    super.key,
  });

  String _dateLabel() {
    try {
      final dt = DateTime.parse(workout.date);
      const days = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];
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
      return '${days[dt.weekday - 1]} ${dt.day} ${months[dt.month - 1]}';
    } catch (_) {
      return workout.date;
    }
  }

  String _stats() {
    final parts = <String>[];
    if (workout.durationS != null) {
      parts.add('${(workout.durationS! / 60).round()} min');
    }
    if (workout.distanceM != null) {
      parts.add('${(workout.distanceM! / 1000).toStringAsFixed(1)} km');
    }
    if (workout.stress != null) {
      parts.add('RSS ${workout.stress!.round()}');
    }
    return parts.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final stats = _stats();
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 3),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Container(
          decoration: const BoxDecoration(
            borderRadius: BorderRadius.all(Radius.circular(12)),
            border: Border(
              left: BorderSide(color: Color(0xFFF59E0B), width: 3),
            ),
          ),
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _dateLabel(),
                      style: const TextStyle(
                        fontSize: 10,
                        color: Color(0xFF888888),
                        letterSpacing: 1,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      workout.name,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (stats.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        stats,
                        style: const TextStyle(
                          fontSize: 11,
                          color: Color(0xFF888888),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const Icon(
                Icons.chevron_right,
                size: 18,
                color: Color(0xFF888888),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
