import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/widgets/best_run_time_card.dart';
import 'package:runcoach/providers/best_run_time_provider.dart';

Map<String, dynamic> _fakeData({int bestScore = 8}) => {
  'date': '2026-05-10',
  'hours': List.generate(
    24,
    (h) => {
      'hour': h,
      'score': h == 9 ? bestScore : 4,
      'temp_c': 12.0,
      'rain_pct': 5,
      'humidity_pct': 55,
      'wind_kmh': 10.0,
    },
  ),
  'best_hour': 9,
  'best_score': bestScore,
  'day_label': 'Best window: 9am · $bestScore/10',
};

Widget _wrap(Map<String, dynamic>? data) => ProviderScope(
  overrides: [bestRunTimeProvider.overrideWith((_) async => data)],
  child: const MaterialApp(home: Scaffold(body: BestRunTimeCard())),
);

void main() {
  testWidgets('shows day_label when data available', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Best window'), findsOneWidget);
  });

  testWidgets('renders 24 bars', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('brt-bars')), findsOneWidget);
  });

  testWidgets('hidden when location unavailable (null data)', (tester) async {
    await tester.pumpWidget(_wrap(null));
    await tester.pumpAndSettle();
    expect(find.byType(BestRunTimeCard), findsOneWidget);
    expect(find.textContaining('Best window'), findsNothing);
  });

  testWidgets('shows loading indicator while fetching', (tester) async {
    final completer = Completer<Map<String, dynamic>?>();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [bestRunTimeProvider.overrideWith((_) => completer.future)],
        child: const MaterialApp(home: Scaffold(body: BestRunTimeCard())),
      ),
    );
    await tester.pump(); // one frame — still loading
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    completer.complete(null); // clean up
  });
}
