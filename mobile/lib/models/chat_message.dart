class ChatMessage {
  final String role;
  final String message;
  final String? createdAt;

  const ChatMessage({
    required this.role,
    required this.message,
    this.createdAt,
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
        role: json['role'] as String,
        message: json['message'] as String? ?? '',
        createdAt: json['created_at'] as String?,
      );

  bool get isUser => role == 'user';
}
