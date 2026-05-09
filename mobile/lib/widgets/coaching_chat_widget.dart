import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../providers/chat_provider.dart';
import '../providers/auth_provider.dart';
import '../providers/run_detail_provider.dart';
import '../models/run.dart';

class CoachingChatWidget extends ConsumerStatefulWidget {
  final Run run;
  const CoachingChatWidget({required this.run, super.key});

  @override
  ConsumerState<CoachingChatWidget> createState() => _CoachingChatWidgetState();
}

class _CoachingChatWidgetState extends ConsumerState<CoachingChatWidget> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  bool _analyzing = false;
  Timer? _pollTimer;

  @override
  void dispose() {
    _pollTimer?.cancel();
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  bool _shouldAutoScroll(ChatState? previous, ChatState next) {
    return shouldAutoScrollChat(previous, next);
  }

  Future<void> _triggerAnalysis() async {
    setState(() => _analyzing = true);
    try {
      await ref.read(apiServiceProvider).analyzeRun(widget.run.id);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Failed to start analysis: $e')));
      setState(() => _analyzing = false);
      return;
    }
    // Poll every 3 seconds until the run stage flips to analyzed
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!mounted) {
        _pollTimer?.cancel();
        return;
      }
      ref.invalidate(runDetailProvider(widget.run.id));
    });
  }

  void _stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
    if (mounted) setState(() => _analyzing = false);
  }

  @override
  Widget build(BuildContext context) {
    final chatState = ref.watch(chatProvider(widget.run.id));

    // Watch the live run so we detect when analysis completes
    final runAsync = ref.watch(runDetailProvider(widget.run.id));
    final liveRun = runAsync.valueOrNull ?? widget.run;
    final isAnalyzed = liveRun.stage == RunStage.analyzed;

    // Stop polling once analysis is complete
    if (_analyzing && isAnalyzed) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _stopPolling());
    }

    ref.listen(chatProvider(widget.run.id), (previous, next) {
      if (_shouldAutoScroll(previous, next)) {
        _scrollToBottom();
      }
    });

    return Column(
      children: [
        Expanded(
          child: ListView(
            controller: _scrollController,
            padding: const EdgeInsets.all(16),
            children: [
              if (isAnalyzed && liveRun.commentary != null)
                _AiCommentaryBubble(
                  commentary: liveRun.commentary!,
                  timestamp: liveRun.analyzedAt,
                ),
              if (!isAnalyzed)
                Padding(
                  padding: const EdgeInsets.symmetric(
                    vertical: 48,
                    horizontal: 16,
                  ),
                  child: Column(
                    children: [
                      if (_analyzing)
                        const CircularProgressIndicator()
                      else
                        const Icon(
                          Icons.analytics_outlined,
                          size: 48,
                          color: Color(0xFFCCCCCC),
                        ),
                      const SizedBox(height: 16),
                      Text(
                        _analyzing
                            ? 'Analysing your run…'
                            : 'No coaching analysis yet',
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF666666),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        _analyzing
                            ? 'This usually takes about a minute'
                            : 'Get AI coaching feedback on this run',
                        style: const TextStyle(
                          fontSize: 13,
                          color: Color(0xFF888888),
                        ),
                      ),
                      if (!_analyzing) ...[
                        const SizedBox(height: 24),
                        FilledButton.icon(
                          icon: const Icon(Icons.auto_awesome, size: 18),
                          label: const Text('Analyze Now'),
                          onPressed: _triggerAnalysis,
                        ),
                      ],
                    ],
                  ),
                ),
              if (chatState.isLoading)
                const Center(child: CircularProgressIndicator()),
              ...chatState.messages.map(
                (msg) => msg.isUser
                    ? _UserBubble(message: msg.message)
                    : _AiBubble(message: msg.message),
              ),
              if (chatState.isSending)
                const Padding(
                  padding: EdgeInsets.only(top: 8),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                      SizedBox(width: 8),
                      Text(
                        'Thinking…',
                        style: TextStyle(
                          color: Color(0xFF888888),
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        if (isAnalyzed)
          _ChatInput(
            controller: _controller,
            onSend: () {
              final text = _controller.text.trim();
              if (text.isEmpty) return;
              ref.read(chatProvider(liveRun.id).notifier).send(text);
              _controller.clear();
            },
          ),
      ],
    );
  }
}

@visibleForTesting
bool shouldAutoScrollChat(ChatState? previous, ChatState next) {
  if (previous == null) return false;

  final hasNewMessage = next.messages.length > previous.messages.length;
  if (!hasNewMessage) return false;

  final isInitialHistoryLoad =
      previous.isLoading &&
      !next.isLoading &&
      !previous.isSending &&
      !next.isSending;

  return !isInitialHistoryLoad;
}

class _AiCommentaryBubble extends StatelessWidget {
  final String commentary;
  final String? timestamp;

  const _AiCommentaryBubble({required this.commentary, this.timestamp});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 4),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const CircleAvatar(
                radius: 14,
                backgroundColor: Color(0xFF6750A4),
                child: Text(
                  'AI',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              const Text(
                'RunCoach',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF6750A4),
                ),
              ),
              const Spacer(),
              if (timestamp != null)
                Text(
                  _formatTimestamp(timestamp!),
                  style: const TextStyle(
                    fontSize: 10,
                    color: Color(0xFFAAAAAA),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 10),
          MarkdownBody(
            data: commentary,
            styleSheet: MarkdownStyleSheet(
              p: const TextStyle(
                fontSize: 13,
                color: Color(0xFF222222),
                height: 1.5,
              ),
              strong: const TextStyle(
                fontWeight: FontWeight.w700,
                fontSize: 13,
                color: Color(0xFF111111),
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _formatTimestamp(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      const months = [
        'Jan',
        'Feb',
        'Mar',
        'Apr',
        'May',
        'Jun',
        'Jul',
        'Aug',
        'Sep',
        'Oct',
        'Nov',
        'Dec',
      ];
      return '${dt.day} ${months[dt.month - 1]}, ${dt.hour}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }
}

class _UserBubble extends StatelessWidget {
  final String message;
  const _UserBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8, left: 48),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: const BoxDecoration(
          color: Color(0xFF6750A4),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(14),
            topRight: Radius.circular(14),
            bottomLeft: Radius.circular(14),
            bottomRight: Radius.circular(3),
          ),
        ),
        child: Text(
          message,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            height: 1.4,
          ),
        ),
      ),
    );
  }
}

class _AiBubble extends StatelessWidget {
  final String message;
  const _AiBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8, right: 48),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(14),
            topRight: Radius.circular(14),
            bottomLeft: Radius.circular(3),
            bottomRight: Radius.circular(14),
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.06),
              blurRadius: 4,
            ),
          ],
        ),
        child: Text(
          message,
          style: const TextStyle(
            fontSize: 13,
            color: Color(0xFF222222),
            height: 1.4,
          ),
        ),
      ),
    );
  }
}

class _ChatInput extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSend;

  const _ChatInput({required this.controller, required this.onSend});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      color: Colors.white,
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              decoration: const InputDecoration(
                hintText: 'Ask a follow-up question…',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.all(Radius.circular(24)),
                ),
                contentPadding: EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 10,
                ),
                isDense: true,
              ),
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => onSend(),
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            onPressed: onSend,
            style: FilledButton.styleFrom(
              shape: const CircleBorder(),
              padding: const EdgeInsets.all(12),
            ),
            child: const Icon(Icons.arrow_upward, size: 18),
          ),
        ],
      ),
    );
  }
}
