import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/chat_message.dart';
import 'auth_provider.dart';

class ChatState {
  final List<ChatMessage> messages;
  final bool isLoading;
  final bool isSending;

  const ChatState({
    this.messages = const [],
    this.isLoading = false,
    this.isSending = false,
  });

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? isLoading,
    bool? isSending,
  }) =>
      ChatState(
        messages: messages ?? this.messages,
        isLoading: isLoading ?? this.isLoading,
        isSending: isSending ?? this.isSending,
      );
}

class ChatNotifier extends StateNotifier<ChatState> {
  final Ref _ref;
  final int _runId;

  ChatNotifier(this._ref, this._runId) : super(const ChatState()) {
    _load();
  }

  Future<void> _load() async {
    state = state.copyWith(isLoading: true);
    try {
      final api = _ref.read(apiServiceProvider);
      final history = await api.getChatHistory(_runId);
      state = state.copyWith(messages: history, isLoading: false);
    } catch (_) {
      state = state.copyWith(isLoading: false);
    }
  }

  Future<void> send(String message) async {
    if (message.trim().isEmpty || state.isSending) return;
    final userMsg = ChatMessage(role: 'user', message: message);
    state = state.copyWith(
      messages: [...state.messages, userMsg],
      isSending: true,
    );
    try {
      final api = _ref.read(apiServiceProvider);
      final response = await api.sendChatMessage(_runId, message);
      state = state.copyWith(
        messages: [...state.messages, response],
        isSending: false,
      );
    } catch (_) {
      state = state.copyWith(isSending: false);
    }
  }
}

final chatProvider =
    StateNotifierProvider.autoDispose.family<ChatNotifier, ChatState, int>((ref, runId) {
  return ChatNotifier(ref, runId);
});
