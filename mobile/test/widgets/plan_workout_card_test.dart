import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../lib/models/planned_workout.dart';
import '../../lib/widgets/plan_workout_card.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

PlannedWorkout _workout({
  String date = '2026-05-12',
  String name = 'Easy Run',
  double? durationS,
  double? distanceM,
  double? stress,
}) => PlannedWorkout(
  date: date,
  name: name,
  description: '',
  durationS: durationS,
  distanceM: distanceM,
  stress: stress,
);

void main() {
  group('PlanWorkoutCard', () {
    testWidgets('shows workout name', (tester) async {
      await tester.pumpWidget(
        _wrap(
          PlanWorkoutCard(
            workout: _workout(name: 'Threshold Cruise'),
            onTap: () {},
          ),
        ),
      );
      expect(find.text('Threshold Cruise'), findsOneWidget);
    });

    testWidgets('shows formatted date label', (tester) async {
      // 2026-05-12 is a Tuesday
      await tester.pumpWidget(
        _wrap(
          PlanWorkoutCard(
            workout: _workout(date: '2026-05-12'),
            onTap: () {},
          ),
        ),
      );
      expect(find.text('TUE 12 MAY'), findsOneWidget);
    });

    testWidgets('shows duration when present', (tester) async {
      await tester.pumpWidget(
        _wrap(
          PlanWorkoutCard(workout: _workout(durationS: 2700), onTap: () {}),
        ),
      );
      expect(find.textContaining('45 min'), findsOneWidget);
    });

    testWidgets('shows distance when present', (tester) async {
      await tester.pumpWidget(
        _wrap(
          PlanWorkoutCard(workout: _workout(distanceM: 8000), onTap: () {}),
        ),
      );
      expect(find.textContaining('8.0 km'), findsOneWidget);
    });

    testWidgets('shows RSS when stress present', (tester) async {
      await tester.pumpWidget(
        _wrap(PlanWorkoutCard(workout: _workout(stress: 45.7), onTap: () {})),
      );
      expect(find.textContaining('RSS 46'), findsOneWidget);
    });

    testWidgets('omits stats line when all stats null', (tester) async {
      await tester.pumpWidget(
        _wrap(PlanWorkoutCard(workout: _workout(), onTap: () {})),
      );
      expect(find.textContaining('min'), findsNothing);
      expect(find.textContaining('km'), findsNothing);
      expect(find.textContaining('RSS'), findsNothing);
    });

    testWidgets('calls onTap when tapped', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        _wrap(PlanWorkoutCard(workout: _workout(), onTap: () => tapped = true)),
      );
      await tester.tap(find.byType(InkWell));
      expect(tapped, isTrue);
    });
  });
}
