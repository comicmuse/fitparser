class PlannedWorkout {
  final int? id;
  final String date;
  final String name;
  final String description;
  final double? distanceM;
  final double? durationS;
  final List<int>? intensityZones;

  const PlannedWorkout({
    this.id,
    required this.date,
    required this.name,
    required this.description,
    this.distanceM,
    this.durationS,
    this.intensityZones,
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
  );
}
