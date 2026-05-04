import 'run.dart';
import 'training_summary.dart';
import 'planned_workout.dart';

class Dashboard {
  final Run? latestRun;
  final PlannedWorkout? nextWorkout;
  final TrainingSummary trainingSummary;

  const Dashboard({
    this.latestRun,
    this.nextWorkout,
    required this.trainingSummary,
  });

  factory Dashboard.fromJson(Map<String, dynamic> json) => Dashboard(
        latestRun: json['latest_run'] != null
            ? Run.fromJson(json['latest_run'] as Map<String, dynamic>)
            : null,
        nextWorkout: json['next_workout'] != null
            ? PlannedWorkout.fromJson(json['next_workout'] as Map<String, dynamic>)
            : null,
        trainingSummary: TrainingSummary.fromJson(
            json['training_summary'] as Map<String, dynamic>),
      );
}
