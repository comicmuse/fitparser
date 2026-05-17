// Debug experiment: same as previous trivial, but with dart:convert and
// dart:typed_data removed. The only top-level imports left are dio,
// flutter_test, api_service, and secure_storage_service_base — which
// matches auth_provider_test's transitive graph (api_service.dart pulls
// dio in either case). If this passes, dart:convert OR dart:typed_data
// is the trigger.

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/secure_storage_service_base.dart';

void main() {
  test('trivial', () {
    expect(true, isTrue);
    expect(BaseOptions, isNotNull);
    expect(ApiService, isNotNull);
    expect(SecureStorageServiceBase, isNotNull);
  });
}
