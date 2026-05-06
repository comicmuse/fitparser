import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../lib/widgets/power_zone_bar.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  group('PowerZoneBar', () {
    testWidgets('shows nothing when zones are null', (tester) async {
      await tester.pumpWidget(_wrap(const PowerZoneBar(zones: null)));
      expect(find.text('POWER ZONES'), findsNothing);
    });

    testWidgets('shows nothing when all zones are zero', (tester) async {
      await tester.pumpWidget(
        _wrap(const PowerZoneBar(zones: [0, 0, 0, 0, 0])),
      );
      expect(find.text('POWER ZONES'), findsNothing);
    });

    testWidgets('renders header when at least one zone is non-zero', (tester) async {
      await tester.pumpWidget(
        _wrap(const PowerZoneBar(zones: [2340, 0, 0, 60, 0])),
      );
      expect(find.text('POWER ZONES'), findsOneWidget);
    });

    testWidgets('formats seconds as MM:SS label', (tester) async {
      await tester.pumpWidget(
        _wrap(const PowerZoneBar(zones: [2340, 0, 0, 60, 0])),
      );
      // 2340s = 39:00, 60s = 1:00
      expect(find.textContaining('Z1 39:00'), findsOneWidget);
      expect(find.textContaining('Z4 1:00'), findsOneWidget);
    });

    testWidgets('suppresses zero-zone labels', (tester) async {
      await tester.pumpWidget(
        _wrap(const PowerZoneBar(zones: [2340, 0, 0, 60, 0])),
      );
      expect(find.textContaining('Z2'), findsNothing);
      expect(find.textContaining('Z3'), findsNothing);
      expect(find.textContaining('Z5'), findsNothing);
    });

    testWidgets('renders all non-zero zones', (tester) async {
      await tester.pumpWidget(
        _wrap(const PowerZoneBar(zones: [600, 1200, 300, 0, 0])),
      );
      expect(find.textContaining('Z1'), findsOneWidget);
      expect(find.textContaining('Z2'), findsOneWidget);
      expect(find.textContaining('Z3'), findsOneWidget);
      expect(find.textContaining('Z4'), findsNothing);
    });
  });
}
