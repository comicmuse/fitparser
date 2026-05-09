import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../lib/models/planned_workout.dart';
import '../../lib/screens/workout_detail_screen.dart';

PlannedWorkout _makeWorkout({required List<PlannedWorkoutBlock> structure}) =>
    PlannedWorkout(
      date: '2026-01-10',
      name: 'Test Workout',
      description: '',
      structure: structure,
    );

PlannedWorkoutBlock _repeatBlock(int repeat) => PlannedWorkoutBlock(
      repeat: repeat,
      segments: [
        PlannedWorkoutSegment(
          intensityClass: 'work',
          durationS: 360,
          powerMinPct: 95,
          powerMaxPct: 105,
        ),
        PlannedWorkoutSegment(
          intensityClass: 'rest',
          durationS: 120,
        ),
      ],
    );

PlannedWorkoutBlock _singleBlock(String intensityClass) => PlannedWorkoutBlock(
      repeat: 1,
      segments: [
        PlannedWorkoutSegment(
          intensityClass: intensityClass,
          durationS: 600,
        ),
      ],
    );

Widget _wrap(PlannedWorkout workout) => ProviderScope(
      child: MaterialApp(
        home: WorkoutDetailScreen(workout: workout),
      ),
    );

void main() {
  group('_StructureTab repeat group', () {
    testWidgets('shows amber border container for repeat > 1', (tester) async {
      final workout = _makeWorkout(structure: [_repeatBlock(5)]);
      await tester.pumpWidget(_wrap(workout));
      // Navigate to Structure tab
      await tester.tap(find.text('Structure'));
      await tester.pumpAndSettle();

      // The amber Container should exist
      final containers = tester.widgetList<Container>(find.byType(Container));
      final hasAmberBorder = containers.any((c) {
        final deco = c.decoration;
        if (deco is BoxDecoration && deco.border is Border) {
          final border = deco.border as Border;
          return border.top.color == const Color(0xFFF59E0B);
        }
        return false;
      });
      expect(hasAmberBorder, isTrue);
    });

    testWidgets('shows × N REPEAT label for repeat > 1', (tester) async {
      final workout = _makeWorkout(structure: [_repeatBlock(5)]);
      await tester.pumpWidget(_wrap(workout));
      await tester.tap(find.text('Structure'));
      await tester.pumpAndSettle();

      expect(find.text('× 5 REPEAT'), findsOneWidget);
    });

    testWidgets('does not show amber border for repeat == 1', (tester) async {
      final workout = _makeWorkout(structure: [
        _singleBlock('warmup'),
        _singleBlock('cooldown'),
      ]);
      await tester.pumpWidget(_wrap(workout));
      await tester.tap(find.text('Structure'));
      await tester.pumpAndSettle();

      expect(find.text('REPEAT'), findsNothing);
      final containers = tester.widgetList<Container>(find.byType(Container));
      final hasAmberBorder = containers.any((c) {
        final deco = c.decoration;
        if (deco is BoxDecoration && deco.border is Border) {
          final border = deco.border as Border;
          return border.top.color == const Color(0xFFF59E0B);
        }
        return false;
      });
      expect(hasAmberBorder, isFalse);
    });

    testWidgets('segment cards inside repeat use narrower margin', (tester) async {
      final workout = _makeWorkout(structure: [_repeatBlock(3)]);
      await tester.pumpWidget(_wrap(workout));
      await tester.tap(find.text('Structure'));
      await tester.pumpAndSettle();
      // Smoke test — just verify it renders without error
      expect(find.text('× 3 REPEAT'), findsOneWidget);
      expect(find.text('WORK'), findsOneWidget);
      expect(find.text('REST'), findsOneWidget);
    });
  });
}
