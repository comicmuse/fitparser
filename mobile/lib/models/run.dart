enum RunStage { synced, parsed, analyzed, error, unknown }

class Run {
  final int id;
  final String name;
  final String date;
  final double? distanceKm;
  final int? durationS;
  final String durationFormatted;
  final int? avgPowerW;
  final int? avgHr;
  final double? strydRss;
  final RunStage stage;
  final String? commentary;
  final String? analyzedAt;
  final String? stravaActivityId;
  final int? strydActivityId;
  final String? stravaMapPolyline;
  final Map<String, dynamic>? yamlData;

  const Run({
    required this.id,
    required this.name,
    required this.date,
    this.distanceKm,
    this.durationS,
    required this.durationFormatted,
    this.avgPowerW,
    this.avgHr,
    this.strydRss,
    required this.stage,
    this.commentary,
    this.analyzedAt,
    this.stravaActivityId,
    this.strydActivityId,
    this.stravaMapPolyline,
    this.yamlData,
  });

  factory Run.fromJson(Map<String, dynamic> json) {
    final stageStr = json['stage'] as String? ?? 'unknown';
    final stage = RunStage.values.firstWhere(
      (e) => e.name == stageStr,
      orElse: () => RunStage.unknown,
    );
    return Run(
      id: json['id'] as int,
      name: json['name'] as String? ?? '',
      date: json['date'] as String? ?? '',
      distanceKm: (json['distance_km'] as num?)?.toDouble(),
      durationS: json['duration_s'] as int?,
      durationFormatted: json['duration_formatted'] as String? ?? '—',
      avgPowerW: json['avg_power_w'] as int?,
      avgHr: json['avg_hr'] as int?,
      strydRss: (json['stryd_rss'] as num?)?.toDouble(),
      stage: stage,
      commentary: json['commentary'] as String?,
      analyzedAt: json['analyzed_at'] as String?,
      stravaActivityId: json['strava_activity_id'] as String?,
      strydActivityId: json['stryd_activity_id'] as int?,
      stravaMapPolyline: json['strava_map_polyline'] as String?,
      yamlData: json['yaml_data'] as Map<String, dynamic>?,
    );
  }
}
