import 'package:flutter/material.dart';

class HrZonesBar extends StatelessWidget {
  final Map<String, dynamic> hrZones;
  const HrZonesBar({required this.hrZones, super.key});

  static const _zoneColors = [
    Color(0xFF60A5FA),
    Color(0xFF34D399),
    Color(0xFFFBBF24),
    Color(0xFFF97316),
    Color(0xFFEF4444),
  ];

  @override
  Widget build(BuildContext context) {
    final zones = [
      (hrZones['Z1_pct'] as num?)?.toDouble() ??
          (hrZones['z1'] as num?)?.toDouble() ??
          0.0,
      (hrZones['Z2_pct'] as num?)?.toDouble() ??
          (hrZones['z2'] as num?)?.toDouble() ??
          0.0,
      (hrZones['Z3_pct'] as num?)?.toDouble() ??
          (hrZones['z3'] as num?)?.toDouble() ??
          0.0,
      (hrZones['Z4_pct'] as num?)?.toDouble() ??
          (hrZones['z4'] as num?)?.toDouble() ??
          0.0,
      (hrZones['Z5_pct'] as num?)?.toDouble() ??
          (hrZones['z5'] as num?)?.toDouble() ??
          0.0,
    ];
    final total = zones.fold(0.0, (a, b) => a + b);
    if (total == 0) return const SizedBox.shrink();

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'HR ZONES',
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
                children: zones.asMap().entries.map((e) {
                  final pct = e.value / total;
                  return Expanded(
                    flex: (pct * 1000).toInt(),
                    child: Container(height: 12, color: _zoneColors[e.key]),
                  );
                }).toList(),
              ),
            ),
            const SizedBox(height: 6),
            Row(
              children: zones
                  .asMap()
                  .entries
                  .map(
                    (e) => Expanded(
                      child: Text(
                        'Z${e.key + 1}\n${e.value.toStringAsFixed(0)}%',
                        style: const TextStyle(
                          fontSize: 9,
                          color: Color(0xFF888888),
                        ),
                        textAlign: TextAlign.center,
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
