import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

class RouteMapWidget extends StatelessWidget {
  final String encodedPolyline;
  const RouteMapWidget({required this.encodedPolyline, super.key});

  List<LatLng> _decode(String encoded) {
    final List<LatLng> points = [];
    int index = 0, lat = 0, lng = 0;
    while (index < encoded.length) {
      int shift = 0, result = 0, b;
      do {
        b = encoded.codeUnitAt(index++) - 63;
        result |= (b & 0x1F) << shift;
        shift += 5;
      } while (b >= 0x20);
      lat += (result & 1) != 0 ? ~(result >> 1) : (result >> 1);
      shift = 0;
      result = 0;
      do {
        b = encoded.codeUnitAt(index++) - 63;
        result |= (b & 0x1F) << shift;
        shift += 5;
      } while (b >= 0x20);
      lng += (result & 1) != 0 ? ~(result >> 1) : (result >> 1);
      points.add(LatLng(lat / 1E5, lng / 1E5));
    }
    return points;
  }

  @override
  Widget build(BuildContext context) {
    final points = _decode(encodedPolyline);
    if (points.isEmpty) return const SizedBox.shrink();

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      clipBehavior: Clip.hardEdge,
      child: SizedBox(
        height: 160,
        child: FlutterMap(
          options: MapOptions(
            initialCameraFit: CameraFit.coordinates(
              coordinates: points,
              padding: const EdgeInsets.all(16),
            ),
            interactionOptions: const InteractionOptions(
              flags: InteractiveFlag.none,
            ),
          ),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'com.runcoach.app',
            ),
            PolylineLayer(
              polylines: [
                Polyline(
                  points: points,
                  color: const Color(0xFF6750A4),
                  strokeWidth: 3,
                ),
              ],
            ),
            MarkerLayer(
              markers: [
                Marker(
                  point: points.first,
                  child: const Icon(
                    Icons.circle,
                    color: Color(0xFF4ADE80),
                    size: 12,
                  ),
                ),
                Marker(
                  point: points.last,
                  child: const Icon(
                    Icons.circle,
                    color: Color(0xFFEF4444),
                    size: 12,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
