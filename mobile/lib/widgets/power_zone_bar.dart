import 'package:flutter/material.dart';

class PowerZoneBar extends StatelessWidget {
  final List<int>? zones;
  const PowerZoneBar({required this.zones, super.key});

  static const _colors = [
    Color(0xFF4ade80), // Z1
    Color(0xFFa3e635), // Z2
    Color(0xFFfacc15), // Z3
    Color(0xFFf97316), // Z4
    Color(0xFFef4444), // Z5
  ];

  String _fmt(int seconds) {
    final m = seconds ~/ 60;
    final s = (seconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    if (zones == null) return const SizedBox.shrink();
    final total = zones!.fold(0, (a, b) => a + b);
    if (total == 0) return const SizedBox.shrink();

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'POWER ZONES',
              style: TextStyle(
                fontSize: 10,
                color: Color(0xFF888888),
                letterSpacing: 1,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(5),
              child: Row(
                children: zones!
                    .asMap()
                    .entries
                    .where((e) => e.value > 0)
                    .map(
                      (e) => Expanded(
                        flex: e.value,
                        child: Container(height: 12, color: _colors[e.key]),
                      ),
                    )
                    .toList(),
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 12,
              runSpacing: 4,
              children: zones!
                  .asMap()
                  .entries
                  .where((e) => e.value > 0)
                  .map(
                    (e) => Text(
                      'Z${e.key + 1} ${_fmt(e.value)}',
                      style: TextStyle(
                        fontSize: 11,
                        color: _colors[e.key],
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  )
                  .toList(),
            ),
          ],
        ),
      ),
    );
  }
}
