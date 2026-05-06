import 'package:flutter_test/flutter_test.dart';
import '../../lib/models/planned_workout.dart';

void main() {
  group('PlannedWorkout.fromJson', () {
    Map<String, dynamic> baseJson() => {
      'id': 784,
      'date': '2026-05-09',
      'name': 'Easy Run / Strides #01',
      'description': 'Keep it easy',
      'distance_m': 6292.8,
      'duration_s': 2400.0,
      'intensity_zones': [2340, 0, 0, 60, 0],
    };

    test('parses all new fields', () {
      final w = PlannedWorkout.fromJson(baseJson());
      expect(w.id, 784);
      expect(w.distanceM, closeTo(6292.8, 0.01));
      expect(w.durationS, closeTo(2400.0, 0.01));
      expect(w.intensityZones, [2340, 0, 0, 60, 0]);
    });

    test('null optional fields are accepted', () {
      final json = baseJson()
        ..['id'] = null
        ..['distance_m'] = null
        ..['duration_s'] = null
        ..['intensity_zones'] = null;
      final w = PlannedWorkout.fromJson(json);
      expect(w.id, isNull);
      expect(w.distanceM, isNull);
      expect(w.durationS, isNull);
      expect(w.intensityZones, isNull);
    });

    test('existing fields still parse correctly', () {
      final w = PlannedWorkout.fromJson(baseJson());
      expect(w.date, '2026-05-09');
      expect(w.name, 'Easy Run / Strides #01');
      expect(w.description, 'Keep it easy');
    });

    test('intensityZones parses correct values', () {
      final w = PlannedWorkout.fromJson(baseJson());
      expect(w.intensityZones, equals([2340, 0, 0, 60, 0]));
    });
  });
}
