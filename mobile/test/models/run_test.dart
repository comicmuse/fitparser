import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/run.dart';

void main() {
  group('Run.fromJson', () {
    Map<String, dynamic> baseJson() => {
          'id': 42,
          'name': 'Morning Run',
          'date': '2026-04-19',
          'distance_km': 13.47,
          'duration_s': 4800,
          'duration_formatted': '1:20:00',
          'avg_power_w': 180,
          'avg_hr': 148,
          'stryd_rss': 69.4,
          'stage': 'analyzed',
          'commentary': 'Good effort.',
          'analyzed_at': '2026-04-19T14:00:00Z',
          'strava_activity_id': 'abc123',
          'stryd_activity_id': 9876543210.0, // API returns float
          'strava_map_polyline': null,
          'yaml_data': null,
          'planned_workout': null,
        };

    test('parses all basic fields', () {
      final run = Run.fromJson(baseJson());
      expect(run.id, 42);
      expect(run.name, 'Morning Run');
      expect(run.date, '2026-04-19');
      expect(run.distanceKm, 13.47);
      expect(run.durationS, 4800);
      expect(run.avgPowerW, 180);
      expect(run.avgHr, 148);
      expect(run.strydRss, 69.4);
      expect(run.stage, RunStage.analyzed);
      expect(run.commentary, 'Good effort.');
      expect(run.stravaActivityId, 'abc123');
    });

    test('converts float stryd_activity_id to int', () {
      final run = Run.fromJson(baseJson());
      expect(run.strydActivityId, 9876543210);
      expect(run.strydActivityId, isA<int>());
    });

    test('converts float numeric fields to correct types', () {
      final json = baseJson()
        ..['avg_power_w'] = 180.0
        ..['avg_hr'] = 148.0
        ..['duration_s'] = 4800.0;
      final run = Run.fromJson(json);
      expect(run.avgPowerW, 180);
      expect(run.avgHr, 148);
      expect(run.durationS, 4800);
    });

    test('handles null optional fields', () {
      final json = baseJson()
        ..['distance_km'] = null
        ..['avg_power_w'] = null
        ..['avg_hr'] = null
        ..['stryd_rss'] = null
        ..['stryd_activity_id'] = null
        ..['commentary'] = null;
      final run = Run.fromJson(json);
      expect(run.distanceKm, isNull);
      expect(run.avgPowerW, isNull);
      expect(run.avgHr, isNull);
      expect(run.strydRss, isNull);
      expect(run.strydActivityId, isNull);
      expect(run.commentary, isNull);
    });

    test('maps unknown stage to RunStage.unknown', () {
      final json = baseJson()..['stage'] = 'something_new';
      expect(Run.fromJson(json).stage, RunStage.unknown);
    });

    test('parses planned_workout when present', () {
      final json = baseJson()
        ..['planned_workout'] = {
          'title': 'Day 105 - Long Run',
          'description': 'Easy aerobic run',
          'duration_min': 80.0,
          'distance_km': 13.0,
        };
      final run = Run.fromJson(json);
      expect(run.plannedWorkout, isNotNull);
      expect(run.plannedWorkout!['title'], 'Day 105 - Long Run');
    });
  });
}
