import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/models/training_summary.dart';
import 'package:runcoach/widgets/rsb_card.dart';

TrainingSummary _summary(List<Map<String, dynamic>> history) =>
    TrainingSummary.fromJson({
      'current_rsb': {
        'rsb': 4.2,
        'ctl': 50.0,
        'atl': 45.8,
        'interpretation': 'fresh',
      },
      'rsb_history': history,
    });

Widget _wrap(TrainingSummary s) => MaterialApp(
  home: Scaffold(
    body: SingleChildScrollView(child: RsbCard(summary: s)),
  ),
);

void main() {
  testWidgets('renders the RSB line chart with history (incl. gaps)', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        _summary([
          {'date': '2026-10-01', 'rsb': -5.0, 'ctl': 48.0, 'atl': 53.0},
          {'date': '2026-10-02', 'rsb': null, 'ctl': null, 'atl': null},
          {'date': '2026-10-03', 'rsb': 2.5, 'ctl': 49.0, 'atl': 46.5},
          {'date': '2026-10-04', 'rsb': 4.2, 'ctl': 50.0, 'atl': 45.8},
        ]),
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('+4.2'), findsOneWidget);
    expect(find.text('Fresh'), findsOneWidget);
    expect(find.byType(LineChart), findsWidgets);
  });

  testWidgets('renders without history', (tester) async {
    await tester.pumpWidget(_wrap(_summary([])));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('+4.2'), findsOneWidget);
  });
}
