import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'auth_provider.dart';

final bestRunTimeProvider = FutureProvider.autoDispose<Map<String, dynamic>?>((
  ref,
) async {
  ref.watch(authProvider);
  final api = ref.read(apiServiceProvider);

  LocationPermission permission = await Geolocator.checkPermission();
  if (permission == LocationPermission.denied) {
    permission = await Geolocator.requestPermission();
  }
  if (permission == LocationPermission.denied ||
      permission == LocationPermission.deniedForever) {
    return null;
  }

  final pos = await Geolocator.getCurrentPosition(
    locationSettings: const LocationSettings(accuracy: LocationAccuracy.low),
  );
  return api.getBestRunTime(lat: pos.latitude, lng: pos.longitude);
});
