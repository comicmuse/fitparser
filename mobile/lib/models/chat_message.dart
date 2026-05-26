class ChatMessage {
  final String role;
  final String message;
  final String? createdAt;
  final String status;

  const ChatMessage({
    required this.role,
    required this.message,
    this.createdAt,
    this.status = 'ok',
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
    role: json['role'] as String,
    message: json['message'] as String? ?? '',
    createdAt: json['created_at'] as String?,
    status: json['status'] as String? ?? 'ok',
  );

  bool get isUser => role == 'user';
  bool get isRateLimited => status == 'rate_limited';
}
