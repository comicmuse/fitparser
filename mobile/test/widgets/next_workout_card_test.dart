import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../lib/models/planned_workout.dart';
import '../../lib/widgets/next_workout_card.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

PlannedWorkout _workout({String description = ''}) => PlannedWorkout(
  date: '2026-05-09',
  name: 'Easy Run',
  description: description,
);

void main() {
  group('NextWorkoutCard', () {
    testWidgets('shows workout name', (tester) async {
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: _workout())));
      expect(find.text('Easy Run'), findsOneWidget);
    });

    testWidgets('shows chevron_right icon', (tester) async {
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: _workout())));
      expect(find.byIcon(Icons.chevron_right), findsOneWidget);
    });

    testWidgets('truncates description to first paragraph', (tester) async {
      final w = _workout(
        description: 'First paragraph.\n\nSecond paragraph.',
      );
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: w)));
      expect(find.text('First paragraph.'), findsOneWidget);
      expect(find.text('Second paragraph.'), findsNothing);
    });

    testWidgets('shows full description when no double newline', (tester) async {
      final w = _workout(description: 'Single paragraph text here.');
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: w)));
      expect(find.text('Single paragraph text here.'), findsOneWidget);
    });

    testWidgets('hides description section when empty', (tester) async {
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: _workout())));
      // No description text should appear
      expect(find.byType(Text), findsNWidgets(2)); // label + name only
    });
  });
}
