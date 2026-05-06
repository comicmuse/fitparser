import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../models/planned_workout.dart';

class NextWorkoutCard extends StatelessWidget {
  final PlannedWorkout workout;
  const NextWorkoutCard({required this.workout, super.key});

  String _formatDate(String isoDate) {
    try {
      final dt = DateTime.parse(isoDate);
      const months = [
        'Jan',
        'Feb',
        'Mar',
        'Apr',
        'May',
        'Jun',
        'Jul',
        'Aug',
        'Sep',
        'Oct',
        'Nov',
        'Dec',
      ];
      const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      return '${days[dt.weekday - 1]} ${dt.day} ${months[dt.month - 1]}';
    } catch (_) {
      return isoDate;
    }
  }

  @override
  Widget build(BuildContext context) {
    final firstPara = workout.description.split('\n\n').first;
    return GestureDetector(
      onTap: () => context.push('/workout-detail', extra: workout),
      child: Card(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: const Border(
              left: BorderSide(color: Color(0xFFF59E0B), width: 3),
            ),
          ),
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'NEXT · ${_formatDate(workout.date)}'.toUpperCase(),
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
                    if (firstPara.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        firstPara,
                        style: const TextStyle(
                          fontSize: 12,
                          color: Color(0xFFB45309),
                        ),
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              const Icon(
                Icons.chevron_right,
                color: Color(0xFF888888),
                size: 20,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
