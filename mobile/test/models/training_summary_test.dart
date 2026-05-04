import 'package:flutter_test/flutter_test.dart';
import '../../lib/models/training_summary.dart';

void main() {
  group('TrainingSummary.fromJson', () {
    Map<String, dynamic> summaryJson() => {
      'current_rsb': {
        'rsb': 5.2,
        'ctl': 45.1,
        'atl': 39.9,
        'interpretation': 'Fresh',
      },
      'rsb_history': <Map<String, dynamic>>[
        {
          'date': '2026-04-17',
          'date_label': '17 Apr',
          'rsb': 3.1,
          'ctl': 44.0,
          'atl': 40.9,
        },
        {
          'date': '2026-04-18',
          'date_label': '18 Apr',
          'rsb': 4.2,
          'ctl': 44.5,
          'atl': 40.3,
        },
        {
          'date': '2026-04-19',
          'date_label': '19 Apr',
          'rsb': 5.2,
          'ctl': 45.1,
          'atl': 39.9,
        },
      ],
    };

    test('parses current RSB values', () {
      final summary = TrainingSummary.fromJson(summaryJson());
      expect(summary.currentRsb.rsb, 5.2);
      expect(summary.currentRsb.ctl, 45.1);
      expect(summary.currentRsb.atl, 39.9);
      expect(summary.currentRsb.interpretation, 'Fresh');
    });

    test('parses rsb_history list', () {
      final summary = TrainingSummary.fromJson(summaryJson());
      expect(summary.rsbHistory.length, 3);
      expect(summary.rsbHistory.first.date, '2026-04-17');
      expect(summary.rsbHistory.last.rsb, 5.2);
    });

    test('handles null RSB values in history', () {
      final json = summaryJson();
      final history = json['rsb_history'] as List;
      history.add(<String, dynamic>{
        'date': '2026-04-20',
        'date_label': '20 Apr',
        'rsb': null,
        'ctl': null,
        'atl': null,
      });
      final summary = TrainingSummary.fromJson(json);
      expect(summary.rsbHistory.last.rsb, isNull);
      expect(summary.rsbHistory.last.ctl, isNull);
    });

    test('handles null current RSB fields', () {
      final json = summaryJson();
      json['current_rsb'] = {
        'rsb': null,
        'ctl': null,
        'atl': null,
        'interpretation': 'Unknown',
      };
      final summary = TrainingSummary.fromJson(json);
      expect(summary.currentRsb.rsb, isNull);
    });
  });
}
