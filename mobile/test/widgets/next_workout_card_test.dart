import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import '../../lib/models/planned_workout.dart';
import '../../lib/widgets/next_workout_card.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

Widget _wrapWithRouter(Widget card, {void Function(Object?)? onNavigate}) {
  final router = GoRouter(
    routes: [
      GoRoute(
        path: '/',
        builder: (_, __) => Scaffold(body: card),
        routes: [
          GoRoute(
            path: 'workout-detail',
            builder: (context, state) {
              onNavigate?.call(state.extra);
              return const Scaffold(body: Text('detail'));
            },
          ),
        ],
      ),
    ],
  );
  return MaterialApp.router(routerConfig: router);
}

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
      final w = _workout(description: 'First paragraph.\n\nSecond paragraph.');
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: w)));
      expect(find.text('First paragraph.'), findsOneWidget);
      expect(find.text('Second paragraph.'), findsNothing);
    });

    testWidgets('shows full description when no double newline', (
      tester,
    ) async {
      final w = _workout(description: 'Single paragraph text here.');
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: w)));
      expect(find.text('Single paragraph text here.'), findsOneWidget);
    });

    testWidgets('hides description section when empty', (tester) async {
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: _workout())));
      // No description text should appear
      expect(find.byType(Text), findsNWidgets(2)); // label + name only
    });

    testWidgets('tapping navigates to /workout-detail with workout as extra', (
      tester,
    ) async {
      final workout = _workout(description: 'Some description.');
      Object? capturedExtra;
      await tester.pumpWidget(
        _wrapWithRouter(
          NextWorkoutCard(workout: workout),
          onNavigate: (extra) => capturedExtra = extra,
        ),
      );
      await tester.tap(find.byType(GestureDetector));
      await tester.pumpAndSettle();
      expect(identical(capturedExtra, workout), isTrue);
    });
  });
}
