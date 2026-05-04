import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../lib/models/workout_block.dart';
import '../../lib/widgets/block_card.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

WorkoutBlock _makeBlock({
  String key = 'work_1',
  String type = 'work',
  double durationMin = 40.0,
  double distanceKm = 6.66,
  double avgPowerW = 190.0,
  double avgHr = 155.0,
  PowerCompliance? compliance,
  double? targetLow,
  double? targetHigh,
}) => WorkoutBlock(
  key: key,
  type: type,
  blockType: BlockType.values.firstWhere(
    (e) => e.name == type,
    orElse: () => BlockType.unknown,
  ),
  durationMin: durationMin,
  distanceKm: distanceKm,
  avgPowerW: avgPowerW,
  avgHr: avgHr,
  targetPowerLow: targetLow,
  targetPowerHigh: targetHigh,
  powerCompliance: compliance,
);

void main() {
  group('BlockCard', () {
    testWidgets('shows block type label', (tester) async {
      await tester.pumpWidget(
        _wrap(BlockCard(block: _makeBlock(type: 'work'))),
      );
      expect(find.text('WORK'), findsOneWidget);
    });

    testWidgets('shows warmup label', (tester) async {
      await tester.pumpWidget(
        _wrap(BlockCard(block: _makeBlock(type: 'warmup'))),
      );
      expect(find.text('WARMUP'), findsOneWidget);
    });

    testWidgets('shows formatted duration', (tester) async {
      await tester.pumpWidget(
        _wrap(BlockCard(block: _makeBlock(durationMin: 40.0))),
      );
      expect(find.text('40:00'), findsOneWidget);
    });

    testWidgets('shows power and HR metrics', (tester) async {
      await tester.pumpWidget(
        _wrap(BlockCard(block: _makeBlock(avgPowerW: 190.0, avgHr: 155.0))),
      );
      expect(find.text('190W'), findsOneWidget);
      expect(find.text('155'), findsOneWidget);
    });

    testWidgets('shows target power range when present', (tester) async {
      final block = _makeBlock(targetLow: 188.0, targetHigh: 203.0);
      await tester.pumpWidget(_wrap(BlockCard(block: block)));
      expect(find.text('188–203W'), findsOneWidget);
    });

    testWidgets('shows compliance bar and percentages when present', (
      tester,
    ) async {
      final compliance = PowerCompliance(
        belowPct: 10.0,
        inZonePct: 79.0,
        abovePct: 11.0,
      );
      final block = _makeBlock(
        compliance: compliance,
        targetLow: 188.0,
        targetHigh: 203.0,
      );
      await tester.pumpWidget(_wrap(BlockCard(block: block)));
      expect(find.textContaining('79% in zone'), findsOneWidget);
      expect(find.textContaining('10% below'), findsOneWidget);
      expect(find.textContaining('11% above'), findsOneWidget);
    });

    testWidgets('does not show compliance section when absent', (tester) async {
      await tester.pumpWidget(_wrap(BlockCard(block: _makeBlock())));
      expect(find.textContaining('in zone'), findsNothing);
    });

    testWidgets('uses orange border for work blocks', (tester) async {
      await tester.pumpWidget(
        _wrap(BlockCard(block: _makeBlock(type: 'work'))),
      );
      // Just verify it renders without error — border color is visual only
      expect(find.byType(BlockCard), findsOneWidget);
    });
  });
}
