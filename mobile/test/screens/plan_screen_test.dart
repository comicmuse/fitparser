import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import '../../lib/models/planned_workout.dart';
import '../../lib/providers/plan_provider.dart';
import '../../lib/screens/plan_screen.dart';

PlannedWorkout _w(
  String date,
  String name, {
  double? durationS,
  double? stress,
}) => PlannedWorkout(
  date: date,
  name: name,
  description: '',
  durationS: durationS,
  stress: stress,
);

Widget _wrap(List<PlannedWorkout> workouts) {
  final router = GoRouter(
    routes: [
      GoRoute(path: '/', builder: (_, __) => const PlanScreen()),
      GoRoute(
        path: '/workout-detail',
        builder: (_, __) => const Scaffold(body: Text('detail')),
      ),
    ],
  );
  return ProviderScope(
    overrides: [planProvider.overrideWith((ref) async => workouts)],
    child: MaterialApp.router(routerConfig: router),
  );
}

void main() {
  group('PlanScreen', () {
    testWidgets('shows empty state when no workouts', (tester) async {
      await tester.pumpWidget(_wrap([]));
      await tester.pumpAndSettle();
      expect(
        find.text('No upcoming workouts. Sync to fetch your training plan.'),
        findsOneWidget,
      );
    });

    testWidgets('shows loading indicator initially', (tester) async {
      final completer = Completer<List<PlannedWorkout>>();
      final router = GoRouter(
        routes: [GoRoute(path: '/', builder: (_, __) => const PlanScreen())],
      );
      await tester.pumpWidget(
        ProviderScope(
          overrides: [planProvider.overrideWith((ref) => completer.future)],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      completer.complete([]);
    });

    testWidgets('shows workout names', (tester) async {
      await tester.pumpWidget(
        _wrap([
          _w('2026-05-12', 'Easy Run'),
          _w('2026-05-14', 'Threshold Cruise'),
        ]),
      );
      await tester.pumpAndSettle();
      expect(find.text('Easy Run'), findsOneWidget);
      expect(find.text('Threshold Cruise'), findsOneWidget);
    });

    testWidgets('shows week header for workouts', (tester) async {
      // 2026-05-12 is Tuesday — week starts Mon 11 May
      await tester.pumpWidget(_wrap([_w('2026-05-12', 'Easy Run')]));
      await tester.pumpAndSettle();
      expect(find.text('WEEK OF 11 MAY'), findsOneWidget);
    });

    testWidgets('groups workouts in same week under one header', (
      tester,
    ) async {
      // Both in same Mon-Sun week (Mon 11 May)
      await tester.pumpWidget(
        _wrap([
          _w('2026-05-12', 'Easy Run'), // Tue
          _w('2026-05-14', 'Intervals'), // Thu
        ]),
      );
      await tester.pumpAndSettle();
      expect(find.text('WEEK OF 11 MAY'), findsOneWidget);
    });

    testWidgets('workouts in different weeks get separate headers', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap([
          _w('2026-05-12', 'Easy Run'), // week of 11 May
          _w('2026-05-19', 'Long Run'), // week of 18 May
        ]),
      );
      await tester.pumpAndSettle();
      expect(find.text('WEEK OF 11 MAY'), findsOneWidget);
      expect(find.text('WEEK OF 18 MAY'), findsOneWidget);
    });
  });
}
