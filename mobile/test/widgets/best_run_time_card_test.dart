import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/widgets/best_run_time_card.dart';
import 'package:runcoach/providers/best_run_time_provider.dart';

Map<String, dynamic> _fakeData({
  int bestScore = 8,
  bool isTomorrow = false,
  int startHour = 5,
  int hourCount = 6,
}) => {
  'date': '2026-05-10',
  'is_tomorrow': isTomorrow,
  'hours': List.generate(
    hourCount,
    (i) => {
      'hour': i + startHour,
      'score': (i + startHour) == 9 ? bestScore : 4,
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

  testWidgets('renders bar chart row', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('brt-bars')), findsOneWidget);
  });

  testWidgets('title shows today when is_tomorrow is false', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    expect(find.text('Best time to run today'), findsOneWidget);
  });

  testWidgets('title shows tomorrow when is_tomorrow is true', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData(isTomorrow: true)));
    await tester.pumpAndSettle();
    expect(find.text('Best time to run tomorrow'), findsOneWidget);
  });

  testWidgets('axis shows first and last hour labels', (tester) async {
    // _fakeData hours: 5,6,7,8,9,10 → first=5am, last=10am
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    expect(find.text('5am'), findsOneWidget);
    expect(find.text('10am'), findsOneWidget);
  });

  testWidgets('shows late-evening label with scroll container for long windows', (
    tester,
  ) async {
    // 19-hour window (5am–11pm): verify the scroll container and last-hour label are present.
    // Drag-to-scroll is not asserted here because the Ahem test font renders characters as
    // fontSize-pixel squares, making the header Row overflow at any narrow viewport needed
    // to trigger the scroll physics. Actual scroll behaviour is verified on-device.
    await tester.pumpWidget(_wrap(_fakeData(hourCount: 19)));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('brt-scroll')), findsOneWidget);
    expect(find.text('11pm'), findsOneWidget);
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
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    completer.complete(null);
    await tester.pumpAndSettle();
  });
}
