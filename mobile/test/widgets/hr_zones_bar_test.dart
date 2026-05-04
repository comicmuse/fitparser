import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/widgets/hr_zones_bar.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  group('HrZonesBar', () {
    test('parses Z1_pct style keys', () {
      // Tested indirectly via widget rendering
    });

    testWidgets('renders zone labels Z1–Z5', (tester) async {
      final zones = {
        'Z1_pct': 7.0,
        'Z2_pct': 54.0,
        'Z3_pct': 15.0,
        'Z4_pct': 24.0,
        'Z5_pct': 0.0,
      };
      await tester.pumpWidget(_wrap(HrZonesBar(hrZones: zones)));
      for (final z in ['Z1', 'Z2', 'Z3', 'Z4', 'Z5']) {
        expect(find.textContaining(z), findsOneWidget);
      }
    });

    testWidgets('renders percentage values', (tester) async {
      final zones = {
        'Z1_pct': 7.0,
        'Z2_pct': 54.0,
        'Z3_pct': 15.0,
        'Z4_pct': 24.0,
        'Z5_pct': 0.0,
      };
      await tester.pumpWidget(_wrap(HrZonesBar(hrZones: zones)));
      expect(find.textContaining('54%'), findsOneWidget);
      expect(find.textContaining('24%'), findsOneWidget);
    });

    testWidgets('shows nothing when all zones are zero', (tester) async {
      final zones = {
        'Z1_pct': 0.0,
        'Z2_pct': 0.0,
        'Z3_pct': 0.0,
        'Z4_pct': 0.0,
        'Z5_pct': 0.0,
      };
      await tester.pumpWidget(_wrap(HrZonesBar(hrZones: zones)));
      expect(find.text('HR ZONES'), findsNothing);
    });

    testWidgets('also accepts lowercase z1/z2 keys', (tester) async {
      final zones = {
        'z1': 10.0,
        'z2': 50.0,
        'z3': 20.0,
        'z4': 15.0,
        'z5': 5.0,
      };
      await tester.pumpWidget(_wrap(HrZonesBar(hrZones: zones)));
      expect(find.text('HR ZONES'), findsOneWidget);
    });
  });
}
