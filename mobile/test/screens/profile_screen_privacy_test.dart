import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/providers/auth_provider.dart';
import 'package:runcoach/screens/profile_screen.dart';

class _FakeServerUrlNotifier extends ServerUrlNotifier {
  @override
  Future<String> build() async => 'https://example.com';
}

void main() {
  group('ProfileScreen privacy', () {
    testWidgets('shows Privacy Policy tile', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            profileDataProvider.overrideWith(
              (ref) async => {
                'athlete_profile': '',
                'strava_athlete_id': null,
                'display_name': 'Test User',
                'username': 'testuser',
                'profile': '',
              },
            ),
            serverUrlProvider.overrideWith(_FakeServerUrlNotifier.new),
          ],
          child: const MaterialApp(home: ProfileScreen()),
        ),
      );
      await tester.pump();
      await tester.pumpAndSettle();
      expect(find.text('Privacy Policy', skipOffstage: false), findsOneWidget);
    });
  });
}
