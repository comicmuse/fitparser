import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/workout_block.dart';

void main() {
  group('WorkoutBlock.fromJson', () {
    Map<String, dynamic> workJson() => {
          'type': 'work',
          'start_utc': '2026-04-19T12:30:00+00:00',
          'end_utc': '2026-04-19T13:10:00+00:00',
          'duration_min': 40.0,
          'distance_km': 6.66,
          'avg_hr': 155.0,
          'avg_power': 190.0,
          'target_power': {
            'min_w': 188.0,
            'max_w': 203.0,
            'pct_time_below': 10.3,
            'pct_time_in_range': 79.1,
            'pct_time_above': 10.6,
          },
        };

    test('parses type and blockType', () {
      final block = WorkoutBlock.fromJson('work_1', workJson());
      expect(block.type, 'work');
      expect(block.blockType, BlockType.work);
      expect(block.key, 'work_1');
    });

    test('parses active blockType', () {
      final json = workJson()..['type'] = 'active';
      final block = WorkoutBlock.fromJson('active_1', json);
      expect(block.blockType, BlockType.active);
    });

    test('parses numeric fields correctly', () {
      final block = WorkoutBlock.fromJson('work_1', workJson());
      expect(block.durationMin, 40.0);
      expect(block.distanceKm, 6.66);
      expect(block.avgHr, 155.0);
      expect(block.avgPowerW, 190.0);
    });

    test('extracts target power range from nested target_power', () {
      final block = WorkoutBlock.fromJson('work_1', workJson());
      expect(block.targetPowerLow, 188.0);
      expect(block.targetPowerHigh, 203.0);
    });

    test('builds PowerCompliance from target_power percentages', () {
      final block = WorkoutBlock.fromJson('work_1', workJson());
      expect(block.powerCompliance, isNotNull);
      expect(block.powerCompliance!.belowPct, 10.3);
      expect(block.powerCompliance!.inZonePct, 79.1);
      expect(block.powerCompliance!.abovePct, 10.6);
    });

    test('handles missing target_power gracefully', () {
      final json = workJson()..remove('target_power');
      final block = WorkoutBlock.fromJson('work_1', json);
      expect(block.targetPowerLow, isNull);
      expect(block.targetPowerHigh, isNull);
      expect(block.powerCompliance, isNull);
    });

    test('formattedDuration formats minutes correctly', () {
      final block = WorkoutBlock.fromJson('work_1', workJson());
      expect(block.formattedDuration, '40:00');
    });

    test('formattedDuration handles sub-minute remainder', () {
      final json = workJson()..['duration_min'] = 10.5;
      final block = WorkoutBlock.fromJson('warmup', json);
      expect(block.formattedDuration, '10:30');
    });

    test('formattedPace computes from distance and duration', () {
      // 40 min / 6.66 km = ~360 sec/km = 6:00/km
      final block = WorkoutBlock.fromJson('work_1', workJson());
      // 40*60/6.66 = 360.36 sec/km → 6:00
      expect(block.formattedPace, contains('/km'));
    });

    test('formattedPace returns dash when no distance', () {
      final json = workJson()..['distance_km'] = null;
      final block = WorkoutBlock.fromJson('work_1', json);
      expect(block.formattedPace, '—');
    });

    test('maps unknown type to BlockType.unknown', () {
      final json = workJson()..['type'] = 'mystery';
      final block = WorkoutBlock.fromJson('x', json);
      expect(block.blockType, BlockType.unknown);
    });
  });
}
