// Debug experiment 4: drop top-level `dio` import (api_service.dart still
// pulls it in transitively). If this passes, top-level dio specifically
// is the trigger. If it segfaults, the trigger is api_service.dart itself
// — which contradicts auth_provider_test passing with the same import.

import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/secure_storage_service_base.dart';

void main() {
  test('trivial', () {
    expect(true, isTrue);
    expect(ApiService, isNotNull);
    expect(SecureStorageServiceBase, isNotNull);
  });
}
