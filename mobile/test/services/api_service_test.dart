// Debug experiment: keep all the imports the real test uses, but reduce
// to a single trivial assertion. If this segfaults, the trigger is one
// of the imports (most likely top-level dio or dart:typed_data). If it
// passes, the trigger is runtime behavior (Dio creation, MockAdapter
// implementation, etc.).

import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/services/api_service.dart';
import 'package:runcoach/services/secure_storage_service_base.dart';

void main() {
  test('trivial', () {
    expect(true, isTrue);
    // Reference imports so analyzer does not flag them.
    expect(jsonEncode(<String, int>{'a': 1}), isNotEmpty);
    expect(Uint8List(0), isEmpty);
    expect(BaseOptions, isNotNull);
    expect(ApiService, isNotNull);
    expect(SecureStorageServiceBase, isNotNull);
  });
}
