# Repeat Group Visualisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap repeat blocks on the Structure tab of the planned workout detail screen in an amber-bordered panel with a "× N REPEAT" chip label.

**Architecture:** `_StructureTab` in `workout_detail_screen.dart` is refactored to extract a `_buildSegmentCard` helper, then conditionally wraps blocks where `repeat > 1` in a `Stack`/`Container` with an amber border and a `Positioned` chip label. No backend, model, or API changes.

**Tech Stack:** Flutter/Dart, `flutter_test` for widget tests.

---

## Files

- **Modify**: `mobile/lib/screens/workout_detail_screen.dart` — extract helper, add amber band
- **Create**: `mobile/test/screens/workout_detail_screen_test.dart` — widget tests

---

### Task 1: Widget tests for repeat group visualisation

Write the failing tests first. The test file doesn't exist yet.

**Files:**
- Create: `mobile/test/screens/workout_detail_screen_test.dart`

- [ ] **Step 1: Create the test file**

```dart
// mobile/test/screens/workout_detail_screen_test.dart
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd mobile && flutter test test/screens/workout_detail_screen_test.dart --reporter expanded
```

Expected: compilation error or test failures — `WorkoutDetailScreen` doesn't show the amber border or label text yet.

---

### Task 2: Extract `_buildSegmentCard` helper and add amber band

**Files:**
- Modify: `mobile/lib/screens/workout_detail_screen.dart`

The current `_StructureTab.build` inlines the segment card widget inside a `map`. Extract it to a private method, then use it from both the repeat and non-repeat render paths.

- [ ] **Step 1: Replace the `_StructureTab` class**

Replace the entire `_StructureTab` class (lines 238–340 of `workout_detail_screen.dart`) with:

```dart
class _StructureTab extends StatelessWidget {
  final PlannedWorkout workout;
  const _StructureTab({required this.workout});

  Color _blockColor(String intensityClass) => switch (intensityClass) {
    'work' || 'active' => const Color(0xFFF97316),
    'rest' => const Color(0xFF9CA3AF),
    'warmup' || 'cooldown' => const Color(0xFF2563EB),
    _ => const Color(0xFFCCCCCC),
  };

  Widget _buildSegmentCard(PlannedWorkoutSegment seg,
      {double horizontalMargin = 16}) {
    final color = _blockColor(seg.intensityClass);
    final hasPower = seg.powerMinPct != null && seg.powerMaxPct != null;
    return Card(
      margin: EdgeInsets.symmetric(horizontal: horizontalMargin, vertical: 3),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border(left: BorderSide(color: color, width: 3)),
        ),
        padding: const EdgeInsets.all(12),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  seg.intensityClass.toUpperCase(),
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: color,
                    letterSpacing: 0.5,
                  ),
                ),
                if (hasPower) ...[
                  const SizedBox(height: 2),
                  Text(
                    '${seg.powerMinPct}–${seg.powerMaxPct}% CP',
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ],
            ),
            Text(
              seg.formattedDuration,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: Color(0xFF888888),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRepeatGroup(PlannedWorkoutBlock block, BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 14, 12, 4),
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            decoration: BoxDecoration(
              border: Border.all(color: const Color(0xFFF59E0B), width: 1.5),
              borderRadius: BorderRadius.circular(14),
              color: const Color(0xFFF59E0B).withOpacity(0.06),
            ),
            padding: const EdgeInsets.fromLTRB(0, 10, 0, 6),
            child: Column(
              children: block.segments
                  .map((seg) => _buildSegmentCard(seg, horizontalMargin: 8))
                  .toList(),
            ),
          ),
          Positioned(
            top: -9,
            left: 12,
            child: Container(
              color: Theme.of(context).scaffoldBackgroundColor,
              padding: const EdgeInsets.symmetric(horizontal: 6),
              child: Text(
                '× ${block.repeat} REPEAT',
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFFF59E0B),
                  letterSpacing: 0.5,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final structure = workout.structure;
    if (structure == null || structure.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'No structure data available for this workout',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFF888888)),
          ),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(vertical: 12),
      itemCount: structure.length,
      itemBuilder: (context, i) {
        final block = structure[i];
        if (block.repeat > 1) {
          return _buildRepeatGroup(block, context);
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: block.segments
              .map((seg) => _buildSegmentCard(seg))
              .toList(),
        );
      },
    );
  }
}
```

- [ ] **Step 2: Run the tests**

```bash
cd mobile && flutter test test/screens/workout_detail_screen_test.dart --reporter expanded
```

Expected: 4 tests pass.

- [ ] **Step 3: Run the full test suite**

```bash
cd mobile && flutter test --reporter expanded
```

Expected: all tests pass, no regressions.

- [ ] **Step 4: Commit**

```bash
git add mobile/lib/screens/workout_detail_screen.dart \
        mobile/test/screens/workout_detail_screen_test.dart
git commit -m "feat(mobile): amber band grouping for repeat blocks on Structure tab

Closes #17"
```

---

## Self-Review

**Spec coverage:**
- ✅ Amber border `1.5dp`, `Color(0xFFF59E0B)`, `BorderRadius.circular(14)` — in `_buildRepeatGroup`
- ✅ Background 6% amber opacity — `withOpacity(0.06)`
- ✅ `"× N REPEAT"` chip with scaffold background cutout — `Positioned` label
- ✅ Inner cards use `horizontalMargin: 8`, outer use default `16`
- ✅ `repeat == 1` blocks unchanged — fall through to existing `Column` path
- ✅ Three widget tests: amber border present, label visible, no amber for single blocks
- ✅ No backend/model/API changes

**Placeholder scan:** None found.

**Type consistency:** `PlannedWorkoutBlock`, `PlannedWorkoutSegment`, `_buildSegmentCard`, `_buildRepeatGroup` — consistent throughout.
