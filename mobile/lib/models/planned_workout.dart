class PlannedWorkout {
  final String date;
  final String name;
  final String description;

  const PlannedWorkout({
    required this.date,
    required this.name,
    required this.description,
  });

  factory PlannedWorkout.fromJson(Map<String, dynamic> json) => PlannedWorkout(
        date: json['date'] as String,
        name: json['name'] as String? ?? '',
        description: json['description'] as String? ?? '',
      );
}
