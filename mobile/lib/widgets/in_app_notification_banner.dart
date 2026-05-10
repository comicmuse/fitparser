import 'package:flutter/material.dart';

/// Burnt-orange banner that slides down from the top of the screen when a
/// new analysis notification arrives while the app is in the foreground.
class InAppNotificationBanner extends StatefulWidget {
  final String runName;
  final VoidCallback onTap;
  final VoidCallback onDismiss;

  const InAppNotificationBanner({
    super.key,
    required this.runName,
    required this.onTap,
    required this.onDismiss,
  });

  @override
  State<InAppNotificationBanner> createState() =>
      _InAppNotificationBannerState();
}

class _InAppNotificationBannerState extends State<InAppNotificationBanner>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<Offset> _slide;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
    _slide = Tween<Offset>(
      begin: const Offset(0, -1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOut));

    _controller.forward();
    Future.delayed(const Duration(seconds: 4), () {
      if (mounted) _dismiss();
    });
  }

  void _dismiss() {
    _controller.reverse().then((_) => widget.onDismiss());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SlideTransition(
      position: _slide,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
          child: Material(
            color: Colors.transparent,
            child: GestureDetector(
              onTap: () {
                _dismiss();
                widget.onTap();
              },
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFFC45C1A),
                  borderRadius: BorderRadius.circular(10),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.3),
                      blurRadius: 12,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 12,
                ),
                child: Row(
                  children: [
                    Container(
                      width: 34,
                      height: 34,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.2),
                        shape: BoxShape.circle,
                      ),
                      child: const Center(
                        child: Text('🏃', style: TextStyle(fontSize: 16)),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Text(
                            'New Analysis Ready',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                            ),
                          ),
                          Text(
                            '${widget.runName} · Tap to view',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                    GestureDetector(
                      onTap: _dismiss,
                      child: const Icon(
                        Icons.close,
                        color: Colors.white54,
                        size: 20,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Inserts an [InAppNotificationBanner] into [overlay] and manages its lifecycle.
/// The returned [OverlayEntry] is removed automatically on dismiss or tap.
OverlayEntry showInAppNotificationBanner({
  required OverlayState overlay,
  required String runName,
  required VoidCallback onTap,
}) {
  late OverlayEntry entry;
  entry = OverlayEntry(
    builder: (_) => Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: InAppNotificationBanner(
        runName: runName,
        onTap: () {
          entry.remove();
          onTap();
        },
        onDismiss: entry.remove,
      ),
    ),
  );
  overlay.insert(entry);
  return entry;
}
