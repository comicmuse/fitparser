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
            const Text(
              'TRAINING STATUS',
              style: TextStyle(
                fontSize: 10,
                color: Color(0xFF888888),
                letterSpacing: 1,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text(
                  rsb.rsb != null
                      ? (rsb.rsb! >= 0
                            ? '+${rsb.rsb!.toStringAsFixed(1)}'
                            : rsb.rsb!.toStringAsFixed(1))
                      : '—',
                  style: TextStyle(
                    fontSize: 36,
                    fontWeight: FontWeight.w800,
                    color: _rsbColor,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  _rsbLabel,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: _rsbColor,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                _statChip('CTL', rsb.ctl?.toStringAsFixed(1) ?? '—'),
                const SizedBox(width: 16),
                _statChip('ATL', rsb.atl?.toStringAsFixed(1) ?? '—'),
                const SizedBox(width: 16),
                _statChip(
                  'RSB',
                  rsb.rsb != null ? rsb.rsb!.toStringAsFixed(1) : '—',
                  color: _rsbColor,
                ),
              ],
            ),
            if (history.isNotEmpty) ...[
              const SizedBox(height: 12),
              SizedBox(
                height: 40,
                child: LineChart(
                  LineChartData(
                    gridData: FlGridData(
                      show: true,
                      drawVerticalLine: false,
                      getDrawingHorizontalLine: (value) {
                        if (value == 0) {
                          return const FlLine(
                            color: Color(0xFFAAAAAA),
                            strokeWidth: 1,
                            dashArray: null,
                          );
                        }
                        return const FlLine(strokeWidth: 0);
                      },
                      checkToShowHorizontalLine: (value) => value == 0,
                    ),
                    titlesData: const FlTitlesData(show: false),
                    borderData: FlBorderData(show: false),
                    lineTouchData: const LineTouchData(enabled: false),
                    lineBarsData: [
                      LineChartBarData(
                        spots: history
                            .asMap()
                            .entries
                            .where((e) => e.value.rsb != null)
                            .map((e) => FlSpot(e.key.toDouble(), e.value.rsb!))
                            .toList(),
                        isCurved: true,
                        color: const Color(0xFF2E7D32),
                        barWidth: 2,
                        dotData: const FlDotData(show: false),
                        belowBarData: BarAreaData(
                          show: true,
                          color: const Color(0xFF2E7D32).withValues(alpha: 0.1),
                        ),
                      ),
                      LineChartBarData(
                        spots: history
                            .asMap()
                            .entries
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
      Text(
        label,
        style: const TextStyle(fontSize: 10, color: Color(0xFF888888)),
      ),
      Text(
        value,
        style: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: color ?? const Color(0xFF1A1A1A),
        ),
      ),
    ],
  );
}
