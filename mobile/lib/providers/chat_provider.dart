import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/chat_message.dart';
import 'auth_provider.dart';

class ChatState {
  final List<ChatMessage> messages;
  final bool isLoading;
  final bool isSending;
  final String? lastError;

  const ChatState({
    this.messages = const [],
    this.isLoading = false,
    this.isSending = false,
    this.lastError,
  });

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? isLoading,
    bool? isSending,
    String? lastError,
    bool clearError = false,
  }) => ChatState(
    messages: messages ?? this.messages,
    isLoading: isLoading ?? this.isLoading,
    isSending: isSending ?? this.isSending,
    lastError: clearError ? null : (lastError ?? this.lastError),
  );
}

class ChatNotifier extends StateNotifier<ChatState> {
  final Ref _ref;
  final int _runId;

  ChatNotifier(this._ref, this._runId) : super(const ChatState()) {
    _load();
  }

  Future<void> _load() async {
    if (!mounted) return;
    state = state.copyWith(isLoading: true);
    try {
      final api = _ref.read(apiServiceProvider);
      final history = await api.getChatHistory(_runId);
      if (!mounted) return;
      state = state.copyWith(messages: history, isLoading: false);
    } catch (_) {
      if (!mounted) return;
      state = state.copyWith(isLoading: false);
    }
  }

  Future<void> send(String message) async {
    if (message.trim().isEmpty || state.isSending) return;
    final userMsg = ChatMessage(role: 'user', message: message);
    if (!mounted) return;
    state = state.copyWith(
      messages: [...state.messages, userMsg],
      isSending: true,
      clearError: true,
    );
    try {
      final api = _ref.read(apiServiceProvider);
      final response = await api.sendChatMessage(_runId, message);
      if (!mounted) return;
      state = state.copyWith(
        messages: [...state.messages, response],
        isSending: false,
      );
    } on DioException catch (e) {
      if (!mounted) return;
      final errorMsg =
          (e.response?.data as Map<String, dynamic>?)?['error'] as String? ??
          'Failed to send message. Please try again.';
      state = state.copyWith(isSending: false, lastError: errorMsg);
    } catch (_) {
      if (!mounted) return;
      state = state.copyWith(
        isSending: false,
        lastError: 'Failed to send message. Please try again.',
      );
    }
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }
}

final chatProvider = StateNotifierProvider.autoDispose
    .family<ChatNotifier, ChatState, int>((ref, runId) {
      return ChatNotifier(ref, runId);
    });
