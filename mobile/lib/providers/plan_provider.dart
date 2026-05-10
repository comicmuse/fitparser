import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/planned_workout.dart';
import 'auth_provider.dart';

final planProvider = FutureProvider.autoDispose<List<PlannedWorkout>>((ref) async {
  ref.watch(authProvider);
  final api = ref.read(apiServiceProvider);
  return api.getPlannedWorkouts();
});
