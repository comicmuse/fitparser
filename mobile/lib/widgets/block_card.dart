import 'package:flutter/material.dart';
import '../models/workout_block.dart';

class BlockCard extends StatelessWidget {
  final WorkoutBlock block;
  const BlockCard({required this.block, super.key});

  Color get _borderColor => switch (block.blockType) {
    BlockType.warmup || BlockType.cooldown => const Color(0xFF2563EB),
    BlockType.work => const Color(0xFFF97316),
    BlockType.rest => const Color(0xFF9CA3AF),
    _ => const Color(0xFFCCCCCC),
  };

  String get _typeLabel => block.type.toUpperCase();

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 3),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border(left: BorderSide(color: _borderColor, width: 3)),
        ),
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_typeLabel,
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700,
                        color: _borderColor, letterSpacing: 0.5)),
                Text(block.formattedDuration,
                    style: const TextStyle(fontSize: 12, color: Color(0xFF888888))),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                if (block.avgPowerW != null)
                  _metric('${block.avgPowerW}W', 'power'),
                if (block.targetPowerLow != null && block.targetPowerHigh != null)
                  _metric('${block.targetPowerLow!.toInt()}–${block.targetPowerHigh!.toInt()}W', 'target'),
                if (block.avgHr != null)
                  _metric('${block.avgHr}', 'HR'),
                _metric(block.formattedPace, 'pace'),
              ],
            ),
            if (block.powerCompliance != null) ...[
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: Row(
                  children: [
                    Expanded(
                      flex: (block.powerCompliance!.belowPct * 10).toInt(),
                      child: Container(height: 5, color: const Color(0xFF60A5FA)),
                    ),
                    Expanded(
                      flex: (block.powerCompliance!.inZonePct * 10).toInt(),
                      child: Container(height: 5, color: const Color(0xFF4ADE80)),
                    ),
                    Expanded(
                      flex: (block.powerCompliance!.abovePct * 10).toInt(),
                      child: Container(height: 5, color: const Color(0xFFF97316)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 3),
              Text(
                '${block.powerCompliance!.belowPct.toStringAsFixed(0)}% below · '
                '${block.powerCompliance!.inZonePct.toStringAsFixed(0)}% in zone · '
                '${block.powerCompliance!.abovePct.toStringAsFixed(0)}% above',
                style: const TextStyle(fontSize: 9, color: Color(0xFF888888)),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _metric(String value, String label) => Padding(
    padding: const EdgeInsets.only(right: 16),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(value, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        Text(label, style: const TextStyle(fontSize: 9, color: Color(0xFF888888))),
      ],
    ),
  );
}
