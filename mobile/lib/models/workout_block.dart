enum BlockType { warmup, work, rest, cooldown, unknown }

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
  final String type;
  final BlockType blockType;
  final int? durationS;
  final double? avgPowerW;
  final int? avgHr;
  final double? avgPaceSecPerKm;
  final double? targetPowerLow;
  final double? targetPowerHigh;
  final PowerCompliance? powerCompliance;

  const WorkoutBlock({
    required this.type,
    required this.blockType,
    this.durationS,
    this.avgPowerW,
    this.avgHr,
    this.avgPaceSecPerKm,
    this.targetPowerLow,
    this.targetPowerHigh,
    this.powerCompliance,
  });

  factory WorkoutBlock.fromJson(Map<String, dynamic> json) {
    final typeStr = (json['type'] as String? ?? '').toLowerCase();
    final blockType = BlockType.values.firstWhere(
      (e) => e.name == typeStr,
      orElse: () => BlockType.unknown,
    );

    PowerCompliance? compliance;
    final comp = json['power_compliance'] as Map<String, dynamic>?;
    if (comp != null) {
      compliance = PowerCompliance(
        belowPct: (comp['below_pct'] as num?)?.toDouble() ?? 0,
        inZonePct: (comp['in_zone_pct'] as num?)?.toDouble() ?? 0,
        abovePct: (comp['above_pct'] as num?)?.toDouble() ?? 0,
      );
    }

    return WorkoutBlock(
      type: json['type'] as String? ?? '',
      blockType: blockType,
      durationS: json['duration_s'] as int?,
      avgPowerW: (json['avg_power_w'] as num?)?.toDouble(),
      avgHr: (json['avg_hr'] as num?)?.toInt(),
      avgPaceSecPerKm: (json['avg_pace_sec_per_km'] as num?)?.toDouble(),
      targetPowerLow: (json['target_power_low'] as num?)?.toDouble(),
      targetPowerHigh: (json['target_power_high'] as num?)?.toDouble(),
      powerCompliance: compliance,
    );
  }

  String get formattedDuration {
    if (durationS == null) return '—';
    final m = durationS! ~/ 60;
    final s = durationS! % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }

  String get formattedPace {
    if (avgPaceSecPerKm == null) return '—';
    final m = avgPaceSecPerKm! ~/ 60;
    final s = (avgPaceSecPerKm! % 60).toInt();
    return '$m:${s.toString().padLeft(2, '0')}/km';
  }
}
