import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/widgets/route_map_widget.dart';

// Google's documented example polyline: (38.5,-120.2) -> (40.7,-120.95)
// -> (43.252,-126.453).
const _encoded = '_p~iF~ps|U_ulLnnqC_mqNvxq`@';

void main() {
  testWidgets('renders map, route polyline and start/end markers', (
    tester,
  ) async {
    // Tile requests get HTTP 400 in widget tests; that must not crash.
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: RouteMapWidget(encodedPolyline: _encoded)),
      ),
    );
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(FlutterMap), findsOneWidget);
    final polyline = tester
        .widget<PolylineLayer>(find.byType(PolylineLayer))
        .polylines
        .single;
    expect(polyline.points, hasLength(3));
    expect(polyline.points.first.latitude, closeTo(38.5, 1e-5));
    expect(polyline.points.last.longitude, closeTo(-126.453, 1e-5));
    expect(find.byIcon(Icons.circle), findsNWidgets(2));
  });

  testWidgets('empty polyline renders nothing', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: RouteMapWidget(encodedPolyline: '')),
      ),
    );
    expect(find.byType(FlutterMap), findsNothing);
  });
}
