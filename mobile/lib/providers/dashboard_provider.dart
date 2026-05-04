import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/dashboard.dart';
import 'auth_provider.dart';

final dashboardProvider = FutureProvider.autoDispose<Dashboard>((ref) async {
  ref.watch(authProvider);
  final api = ref.read(apiServiceProvider);
  return api.getDashboard();
});
