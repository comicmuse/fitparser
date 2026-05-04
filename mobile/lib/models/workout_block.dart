enum BlockType { warmup, active, work, rest, cooldown, unknown }

class PowerCompliance {
  final double belowPct;
  final double inZonePct;
  final double abovePct;

  const PowerCompliance({
    required this.belowPct,
    required this.inZonePct,
    required this.abovePct,
  });
}

class WorkoutBlock {
  final String key;
  final String type;
  final BlockType blockType;
  final double? durationMin;
  final double? distanceKm;
  final double? avgPowerW;
  final double? avgHr;
  final double? targetPowerLow;
  final double? targetPowerHigh;
  final PowerCompliance? powerCompliance;
  final String? startUtc;

  const WorkoutBlock({
    required this.key,
    required this.type,
    required this.blockType,
    this.durationMin,
    this.distanceKm,
    this.avgPowerW,
    this.avgHr,
    this.targetPowerLow,
    this.targetPowerHigh,
    this.powerCompliance,
    this.startUtc,
  });

  factory WorkoutBlock.fromJson(String key, Map<String, dynamic> json) {
    final typeStr = (json['type'] as String? ?? '').toLowerCase();
    final blockType = BlockType.values.firstWhere(
      (e) => e.name == typeStr,
      orElse: () => BlockType.unknown,
    );

    PowerCompliance? compliance;
    final tp = json['target_power'] as Map<String, dynamic>?;
    double? targetLow;
    double? targetHigh;
    if (tp != null) {
      targetLow = (tp['min_w'] as num?)?.toDouble();
      targetHigh = (tp['max_w'] as num?)?.toDouble();
      final below = (tp['pct_time_below'] as num?)?.toDouble();
      final inRange = (tp['pct_time_in_range'] as num?)?.toDouble();
      final above = (tp['pct_time_above'] as num?)?.toDouble();
      if (below != null && inRange != null && above != null) {
        compliance = PowerCompliance(
          belowPct: below,
          inZonePct: inRange,
          abovePct: above,
        );
      }
    }

    return WorkoutBlock(
      key: key,
      type: json['type'] as String? ?? '',
      blockType: blockType,
      durationMin: (json['duration_min'] as num?)?.toDouble(),
      distanceKm: (json['distance_km'] as num?)?.toDouble(),
      avgPowerW: (json['avg_power'] as num?)?.toDouble(),
      avgHr: (json['avg_hr'] as num?)?.toDouble(),
      targetPowerLow: targetLow,
      targetPowerHigh: targetHigh,
      powerCompliance: compliance,
      startUtc: json['start_utc'] as String?,
    );
  }

  String get formattedDuration {
    if (durationMin == null) return '—';
    final totalS = (durationMin! * 60).round();
    final m = totalS ~/ 60;
    final s = totalS % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }

  String get formattedPace {
    if (durationMin == null || distanceKm == null || distanceKm! <= 0)
      return '—';
    final secPerKm = (durationMin! * 60) / distanceKm!;
    final m = secPerKm ~/ 60;
    final s = (secPerKm % 60).toInt();
    return '$m:${s.toString().padLeft(2, '0')}/km';
  }
}
