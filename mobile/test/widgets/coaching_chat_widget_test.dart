import 'package:flutter_test/flutter_test.dart';
import '../../lib/models/chat_message.dart';
import '../../lib/providers/chat_provider.dart';
import '../../lib/widgets/coaching_chat_widget.dart';

void main() {
  group('shouldAutoScrollChat', () {
    const history = [
      ChatMessage(role: 'assistant', message: 'Welcome'),
      ChatMessage(role: 'assistant', message: 'How did it feel?'),
    ];

    test('does not auto-scroll when there is no previous state', () {
      final next = ChatState(messages: history, isLoading: false);
      expect(shouldAutoScrollChat(null, next), isFalse);
    });

    test('does not auto-scroll when initial history load completes', () {
      final previous = const ChatState(messages: [], isLoading: true);
      final next = ChatState(messages: history, isLoading: false);

      expect(shouldAutoScrollChat(previous, next), isFalse);
    });

    test('auto-scrolls when a new user message is added', () {
      final previous = ChatState(messages: history, isSending: false);
      final next = ChatState(
        messages: [
          ...history,
          const ChatMessage(role: 'user', message: 'Hi'),
        ],
        isSending: true,
      );

      expect(shouldAutoScrollChat(previous, next), isTrue);
    });

    test('auto-scrolls when assistant response is added', () {
      final previous = ChatState(
        messages: [
          ...history,
          const ChatMessage(role: 'user', message: 'Hi'),
        ],
        isSending: true,
      );
      final next = ChatState(
        messages: [
          ...history,
          const ChatMessage(role: 'user', message: 'Hi'),
          const ChatMessage(role: 'assistant', message: 'Great run.'),
        ],
        isSending: false,
      );

      expect(shouldAutoScrollChat(previous, next), isTrue);
    });
  });

  group('ChatState', () {
    test('copyWith preserves lastError when not overridden', () {
      const state = ChatState(lastError: 'some error');
      final next = state.copyWith(isSending: true);
      expect(next.lastError, 'some error');
    });

    test('copyWith clears lastError when clearError is true', () {
      const state = ChatState(lastError: 'old error');
      final next = state.copyWith(clearError: true);
      expect(next.lastError, isNull);
    });
  });

  group('ChatMessage status', () {
    test('fromJson defaults status to ok when absent', () {
      final msg = ChatMessage.fromJson({'role': 'user', 'message': 'hello'});
      expect(msg.status, 'ok');
      expect(msg.isRateLimited, isFalse);
    });

    test('fromJson reads rate_limited status', () {
      final msg = ChatMessage.fromJson({
        'role': 'user',
        'message': 'hello',
        'status': 'rate_limited',
      });
      expect(msg.status, 'rate_limited');
      expect(msg.isRateLimited, isTrue);
    });
  });

  group('rate limited message retry', () {
    test('isRateLimited is true for rate_limited status', () {
      const msg = ChatMessage(
        role: 'user',
        message: 'hi',
        status: 'rate_limited',
      );
      expect(msg.isRateLimited, isTrue);
    });

    test('isRateLimited is false for ok status', () {
      const msg = ChatMessage(role: 'user', message: 'hi');
      expect(msg.isRateLimited, isFalse);
    });
  });
}
