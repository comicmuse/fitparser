import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/run.dart';
import 'auth_provider.dart';

final runDetailProvider = FutureProvider.autoDispose.family<Run, int>((
  ref,
  runId,
) async {
  final api = ref.read(apiServiceProvider);
  return api.getRun(runId);
});
