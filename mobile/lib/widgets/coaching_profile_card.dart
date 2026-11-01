import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

/// Server-side limit for the coaching profile text (see api.py).
const int kCoachingProfileMaxLength = 5000;

/// Card showing the athlete's coaching profile — the free-text instructions
/// injected into every AI analysis — with inline editing.
///
/// [onSave] persists the text and returns the value the server stored
/// (which may be sanitised/trimmed).
class CoachingProfileCard extends StatefulWidget {
  final String initialText;
  final Future<String> Function(String text) onSave;

  const CoachingProfileCard({
    super.key,
    required this.initialText,
    required this.onSave,
  });

  @override
  State<CoachingProfileCard> createState() => _CoachingProfileCardState();
}

class _CoachingProfileCardState extends State<CoachingProfileCard> {
  late String _text;
  late final TextEditingController _controller;
  bool _editing = false;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _text = widget.initialText;
    _controller = TextEditingController(text: _text);
  }

  @override
  void didUpdateWidget(CoachingProfileCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Pick up refreshed server data, but never clobber an in-progress edit.
    if (!_editing && widget.initialText != oldWidget.initialText) {
      _text = widget.initialText;
      _controller.text = _text;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _startEditing() {
    _controller.text = _text;
    setState(() => _editing = true);
  }

  void _cancel() {
    _controller.text = _text;
    setState(() => _editing = false);
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final saved = await widget.onSave(_controller.text);
      if (!mounted) return;
      setState(() {
        _text = saved;
        _controller.text = saved;
        _editing = false;
      });
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Coaching profile saved')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not save: ${_errorMessage(e)}')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  static String _errorMessage(Object e) {
    if (e is DioException) {
      final data = e.response?.data;
      if (data is Map && data['error'] is String) return data['error'];
      return e.message ?? 'network error';
    }
    return e.toString();
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'COACHING PROFILE',
                    style: TextStyle(
                      fontSize: 10,
                      color: Color(0xFF888888),
                      letterSpacing: 1,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                if (!_editing)
                  IconButton(
                    key: const ValueKey('coaching-profile-edit'),
                    icon: const Icon(Icons.edit_outlined, size: 20),
                    tooltip: 'Edit coaching profile',
                    visualDensity: VisualDensity.compact,
                    onPressed: _startEditing,
                  ),
              ],
            ),
            const SizedBox(height: 4),
            const Text(
              'Instructions for your AI coach: race goals, training approach, '
              'body weight, injuries, anything it should know.',
              style: TextStyle(fontSize: 12, color: Color(0xFF888888)),
            ),
            const SizedBox(height: 12),
            if (_editing) ..._buildEditor() else _buildView(),
          ],
        ),
      ),
    );
  }

  Widget _buildView() {
    if (_text.isEmpty) {
      return InkWell(
        onTap: _startEditing,
        child: const Padding(
          padding: EdgeInsets.symmetric(vertical: 4),
          child: Text(
            'No coaching profile yet. Tap to add one.',
            style: TextStyle(
              fontSize: 13,
              color: Color(0xFFBBBBBB),
              fontStyle: FontStyle.italic,
            ),
          ),
        ),
      );
    }
    return Text(
      _text,
      style: const TextStyle(fontSize: 13, color: Color(0xFF444444)),
    );
  }

  List<Widget> _buildEditor() {
    return [
      TextField(
        key: const ValueKey('coaching-profile-field'),
        controller: _controller,
        enabled: !_saving,
        autofocus: true,
        minLines: 6,
        maxLines: 14,
        maxLength: kCoachingProfileMaxLength,
        keyboardType: TextInputType.multiline,
        textCapitalization: TextCapitalization.sentences,
        decoration: const InputDecoration(
          border: OutlineInputBorder(),
          hintText: "e.g. I'm training for a spring marathon…",
        ),
      ),
      const SizedBox(height: 8),
      Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          TextButton(
            key: const ValueKey('coaching-profile-cancel'),
            onPressed: _saving ? null : _cancel,
            child: const Text('Cancel'),
          ),
          const SizedBox(width: 8),
          FilledButton(
            key: const ValueKey('coaching-profile-save'),
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Save'),
          ),
        ],
      ),
    ];
  }
}
