import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/widgets/coaching_profile_card.dart';

Widget _wrap(CoachingProfileCard card) => MaterialApp(
  home: Scaffold(body: SingleChildScrollView(child: card)),
);

const _edit = ValueKey('coaching-profile-edit');
const _field = ValueKey('coaching-profile-field');
const _save = ValueKey('coaching-profile-save');
const _cancel = ValueKey('coaching-profile-cancel');

void main() {
  testWidgets('shows existing profile text read-only', (tester) async {
    await tester.pumpWidget(
      _wrap(
        CoachingProfileCard(
          initialText: 'Sub-3 marathon goal',
          onSave: (t) async => t,
        ),
      ),
    );
    expect(find.text('Sub-3 marathon goal'), findsOneWidget);
    expect(find.byKey(_field), findsNothing);
  });

  testWidgets('shows placeholder when profile is empty', (tester) async {
    await tester.pumpWidget(
      _wrap(CoachingProfileCard(initialText: '', onSave: (t) async => t)),
    );
    expect(find.textContaining('No coaching profile yet'), findsOneWidget);

    await tester.tap(find.textContaining('No coaching profile yet'));
    await tester.pump();
    expect(find.byKey(_field), findsOneWidget);
  });

  testWidgets('edit then save calls onSave and shows saved text', (
    tester,
  ) async {
    String? sentText;
    await tester.pumpWidget(
      _wrap(
        CoachingProfileCard(
          initialText: 'Old text',
          onSave: (t) async {
            sentText = t;
            return t.trim(); // server trims
          },
        ),
      ),
    );

    await tester.tap(find.byKey(_edit));
    await tester.pump();
    await tester.enterText(find.byKey(_field), '  New instructions  ');
    await tester.tap(find.byKey(_save));
    await tester.pumpAndSettle();

    expect(sentText, '  New instructions  ');
    expect(find.byKey(_field), findsNothing);
    expect(find.text('New instructions'), findsOneWidget);
    expect(find.text('Coaching profile saved'), findsOneWidget);
  });

  testWidgets('cancel discards edits', (tester) async {
    var saveCalls = 0;
    await tester.pumpWidget(
      _wrap(
        CoachingProfileCard(
          initialText: 'Keep me',
          onSave: (t) async {
            saveCalls++;
            return t;
          },
        ),
      ),
    );

    await tester.tap(find.byKey(_edit));
    await tester.pump();
    await tester.enterText(find.byKey(_field), 'Throw me away');
    await tester.tap(find.byKey(_cancel));
    await tester.pump();

    expect(saveCalls, 0);
    expect(find.text('Keep me'), findsOneWidget);
    expect(find.text('Throw me away'), findsNothing);
  });

  testWidgets('save failure keeps editor open with the typed text', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        CoachingProfileCard(
          initialText: 'Old',
          onSave: (_) async => throw Exception('boom'),
        ),
      ),
    );

    await tester.tap(find.byKey(_edit));
    await tester.pump();
    await tester.enterText(find.byKey(_field), 'Unsaved work');
    await tester.tap(find.byKey(_save));
    await tester.pumpAndSettle();

    expect(find.byKey(_field), findsOneWidget);
    expect(find.text('Unsaved work'), findsOneWidget);
    expect(find.textContaining('Could not save'), findsOneWidget);
  });

  testWidgets('buttons are disabled while saving', (tester) async {
    final completer = Completer<String>();
    await tester.pumpWidget(
      _wrap(
        CoachingProfileCard(
          initialText: 'Old',
          onSave: (_) => completer.future,
        ),
      ),
    );

    await tester.tap(find.byKey(_edit));
    await tester.pump();
    await tester.tap(find.byKey(_save));
    await tester.pump();

    expect(tester.widget<FilledButton>(find.byKey(_save)).onPressed, isNull);
    expect(tester.widget<TextButton>(find.byKey(_cancel)).onPressed, isNull);

    completer.complete('Old');
    await tester.pumpAndSettle();
  });

  testWidgets('enforces the server max length', (tester) async {
    await tester.pumpWidget(
      _wrap(CoachingProfileCard(initialText: '', onSave: (t) async => t)),
    );
    await tester.tap(find.byKey(_edit));
    await tester.pump();
    await tester.enterText(find.byKey(_field), 'x' * 6000);
    await tester.pump();
    final field = tester.widget<TextField>(find.byKey(_field));
    expect(field.controller!.text.length, kCoachingProfileMaxLength);
  });
}
