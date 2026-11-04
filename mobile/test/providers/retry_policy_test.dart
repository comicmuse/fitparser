import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/providers/retry_policy.dart';

void main() {
  test('a failed provider is not retried under the app policy', () async {
    var calls = 0;
    final failing = FutureProvider<int>((ref) async {
      calls++;
      throw Exception('boom');
    });
    final container = ProviderContainer(retry: noProviderRetry);
    addTearDown(container.dispose);

    container.listen(failing, (_, _) {});
    await expectLater(container.read(failing.future), throwsException);
    // Riverpod's default policy would schedule retries within this window.
    await Future<void>.delayed(const Duration(seconds: 1));

    expect(calls, 1);
    expect(container.read(failing).hasError, isTrue);
  });

  test('Riverpod default policy does retry (guards the test above)', () async {
    var calls = 0;
    final failing = FutureProvider<int>((ref) async {
      calls++;
      throw Exception('boom');
    });
    final container = ProviderContainer();
    addTearDown(container.dispose);

    // Don't await `.future` here: under the default policy it stays pending
    // while retries are scheduled.
    container.listen(failing, (_, _) {});
    await Future<void>.delayed(const Duration(seconds: 1));

    expect(calls, greaterThan(1));
  });
}
