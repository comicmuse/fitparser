import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/best_run_time_provider.dart';

class BestRunTimeCard extends ConsumerWidget {
  const BestRunTimeCard({super.key});

  Color _barColor(int score) {
    if (score >= 7) return const Color(0xFF4ade80);
    if (score >= 4) return const Color(0xFFfbbf24);
    return const Color(0xFFf87171);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(bestRunTimeProvider);

    return async.when(
      loading: () => const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Center(child: CircularProgressIndicator()),
        ),
      ),
      error: (_, __) => const SizedBox.shrink(),
      data: (data) {
        if (data == null) return const SizedBox.shrink();
        final hours = List<Map<String, dynamic>>.from(data['hours'] as List);
        final bestHour = data['best_hour'] as int;
        final dayLabel = data['day_label'] as String;
        const maxBarHeight = 48.0;

        return Card(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Best time to run today',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      dayLabel,
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF888888),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                SizedBox(
                  height: maxBarHeight + 4,
                  child: Row(
                    key: const ValueKey('brt-bars'),
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: hours.map((h) {
                      final score = h['score'] as int;
                      final isHour = h['hour'] as int;
                      final barH = (score / 10) * maxBarHeight;
                      return Expanded(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 0.5),
                          child: Container(
                            height: barH.clamp(2.0, maxBarHeight),
                            decoration: BoxDecoration(
                              color: _barColor(score),
                              borderRadius: const BorderRadius.vertical(
                                top: Radius.circular(2),
                              ),
                              border: isHour == bestHour
                                  ? Border.all(color: Colors.white70, width: 1)
                                  : null,
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ),
                const SizedBox(height: 2),
                const Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      '12am',
                      style: TextStyle(fontSize: 9, color: Color(0xFF888888)),
                    ),
                    Text(
                      '6am',
                      style: TextStyle(fontSize: 9, color: Color(0xFF888888)),
                    ),
                    Text(
                      '12pm',
                      style: TextStyle(fontSize: 9, color: Color(0xFF888888)),
                    ),
                    Text(
                      '6pm',
                      style: TextStyle(fontSize: 9, color: Color(0xFF888888)),
                    ),
                    Text(
                      '11pm',
                      style: TextStyle(fontSize: 9, color: Color(0xFF888888)),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
