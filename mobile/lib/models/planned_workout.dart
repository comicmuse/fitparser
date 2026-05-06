class PlannedWorkoutSegment {
  final String intensityClass;
  final int durationS;
  final int? powerMinPct;
  final int? powerMaxPct;

  const PlannedWorkoutSegment({
    required this.intensityClass,
    required this.durationS,
    this.powerMinPct,
    this.powerMaxPct,
  });

  factory PlannedWorkoutSegment.fromJson(Map<String, dynamic> json) =>
      PlannedWorkoutSegment(
        intensityClass: json['intensity_class'] as String? ?? 'work',
        durationS: (json['duration_s'] as num?)?.toInt() ?? 0,
        powerMinPct: (json['power_min_pct'] as num?)?.toInt(),
        powerMaxPct: (json['power_max_pct'] as num?)?.toInt(),
      );

  String get formattedDuration {
    final m = durationS ~/ 60;
    final s = durationS % 60;
    if (m == 0) return '${s}s';
    return s == 0 ? '${m}m' : '${m}m ${s}s';
  }
}

class PlannedWorkoutBlock {
  final int repeat;
  final List<PlannedWorkoutSegment> segments;

  const PlannedWorkoutBlock({required this.repeat, required this.segments});

  factory PlannedWorkoutBlock.fromJson(Map<String, dynamic> json) =>
      PlannedWorkoutBlock(
        repeat: (json['repeat'] as num?)?.toInt() ?? 1,
        segments: (json['segments'] as List<dynamic>? ?? [])
            .map(
              (e) => PlannedWorkoutSegment.fromJson(e as Map<String, dynamic>),
            )
            .toList(),
      );
}

class PlannedWorkout {
  final int? id;
  final String date;
  final String name;
  final String description;
  final double? distanceM;
  final double? durationS;
  final List<int>? intensityZones;
  final List<PlannedWorkoutBlock>? structure;

  const PlannedWorkout({
    this.id,
    required this.date,
    required this.name,
    required this.description,
    this.distanceM,
    this.durationS,
    this.intensityZones,
    this.structure,
  });

  factory PlannedWorkout.fromJson(Map<String, dynamic> json) => PlannedWorkout(
    id: json['id'] as int?,
    date: json['date'] as String,
    name: json['name'] as String? ?? '',
    description: json['description'] as String? ?? '',
    distanceM: (json['distance_m'] as num?)?.toDouble(),
    durationS: (json['duration_s'] as num?)?.toDouble(),
    intensityZones: json['intensity_zones'] != null
        ? (json['intensity_zones'] as List<dynamic>)
              .map((e) => (e as num).toInt())
              .toList()
        : null,
    structure: json['structure'] != null
        ? (json['structure'] as List<dynamic>)
              .map(
                (e) => PlannedWorkoutBlock.fromJson(e as Map<String, dynamic>),
              )
              .toList()
        : null,
  );
}
