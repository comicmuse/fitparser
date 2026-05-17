import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import '../providers/auth_provider.dart';

final profileDataProvider = FutureProvider.autoDispose<Map<String, dynamic>>((
  ref,
) async {
  final api = ref.read(apiServiceProvider);
  return api.getAthleteProfile();
});

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profileAsync = ref.watch(profileDataProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Profile',
          style: TextStyle(fontWeight: FontWeight.w700, color: Colors.white),
        ),
        backgroundColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        iconTheme: const IconThemeData(color: Colors.white),
        flexibleSpace: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              stops: [0.0, 0.38, 0.68, 1.0],
              colors: [
                Color(0xFF1c1917),
                Color(0xFF7c2d00),
                Color(0xFFea580c),
                Color(0xFFfed7aa),
              ],
            ),
          ),
        ),
      ),
      body: profileAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (profile) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Athlete info
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'ATHLETE',
                      style: TextStyle(
                        fontSize: 10,
                        color: Color(0xFF888888),
                        letterSpacing: 1,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      profile['display_name'] as String? ??
                          profile['username'] as String? ??
                          '',
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      profile['username'] as String? ?? '',
                      style: const TextStyle(
                        fontSize: 13,
                        color: Color(0xFF888888),
                      ),
                    ),
                    if ((profile['profile'] as String?)?.isNotEmpty ==
                        true) ...[
                      const SizedBox(height: 12),
                      const Divider(),
                      const SizedBox(height: 8),
                      Text(
                        profile['profile'] as String,
                        style: const TextStyle(
                          fontSize: 13,
                          color: Color(0xFF444444),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),

            // Connected services
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'CONNECTED SERVICES',
                      style: TextStyle(
                        fontSize: 10,
                        color: Color(0xFF888888),
                        letterSpacing: 1,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        if (profile['strava_athlete_id'] != null)
                          _ServiceButton(
                            label: 'STRAVA',
                            color: const Color(0xFFFC4C02),
                            onTap: () => launchUrl(
                              Uri.parse(
                                'https://www.strava.com/athletes/${profile['strava_athlete_id']}',
                              ),
                            ),
                          ),
                        const SizedBox(width: 12),
                        _ServiceButton(
                          label: 'STRYD',
                          color: const Color(0xFF00A0DF),
                          onTap: () =>
                              launchUrl(Uri.parse('https://www.stryd.com')),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),

            // App actions
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'APP',
                      style: TextStyle(
                        fontSize: 10,
                        color: Color(0xFF888888),
                        letterSpacing: 1,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.sync),
                        label: const Text('Sync Now'),
                        onPressed: () async {
                          await ref.read(apiServiceProvider).triggerSync();
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Sync started')),
                            );
                          }
                        },
                      ),
                    ),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: const Icon(
                          Icons.logout,
                          color: Color(0xFFEF4444),
                        ),
                        label: const Text(
                          'Logout',
                          style: TextStyle(color: Color(0xFFEF4444)),
                        ),
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: Color(0xFFEF4444)),
                        ),
                        onPressed: () async {
                          await ref.read(authProvider.notifier).logout();
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),

            // Server configuration
            _ServerUrlCard(),
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'NOTIFICATIONS',
                      style: TextStyle(
                        fontSize: 10,
                        color: Color(0xFF888888),
                        letterSpacing: 1,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(height: 8),
                    Text(
                      'Coming soon',
                      style: TextStyle(fontSize: 13, color: Color(0xFFBBBBBB)),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'LEGAL',
                      style: TextStyle(
                        fontSize: 10,
                        color: Color(0xFF888888),
                        letterSpacing: 1,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Privacy Policy'),
                      trailing: const Icon(Icons.open_in_new, size: 18),
                      onTap: () => launchUrl(
                        Uri.parse('https://runcoach.linehan.me.uk/privacy'),
                        mode: LaunchMode.externalApplication,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ServerUrlCard extends ConsumerStatefulWidget {
  @override
  ConsumerState<_ServerUrlCard> createState() => _ServerUrlCardState();
}

class _ServerUrlCardState extends ConsumerState<_ServerUrlCard> {
  late final TextEditingController _controller;
  bool _editing = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController();
    ref.read(serverUrlProvider.future).then((url) {
      if (mounted) _controller.text = url;
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final urlAsync = ref.watch(serverUrlProvider);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'SERVER',
              style: TextStyle(
                fontSize: 10,
                color: Color(0xFF888888),
                letterSpacing: 1,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 12),
            if (_editing)
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      decoration: const InputDecoration(
                        labelText: 'Server URL',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                      keyboardType: TextInputType.url,
                      autocorrect: false,
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: () async {
                      await ref
                          .read(serverUrlProvider.notifier)
                          .setUrl(_controller.text.trim());
                      if (mounted) setState(() => _editing = false);
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              'Server URL saved. Restart app to reconnect.',
                            ),
                          ),
                        );
                      }
                    },
                    child: const Text('Save'),
                  ),
                ],
              )
            else
              Row(
                children: [
                  Expanded(
                    child: Text(
                      urlAsync.valueOrNull ?? '…',
                      style: const TextStyle(
                        fontSize: 13,
                        color: Color(0xFF444444),
                        fontFamily: 'monospace',
                      ),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.edit_outlined, size: 20),
                    onPressed: () => setState(() => _editing = true),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _ServiceButton extends StatelessWidget {
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _ServiceButton({
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: onTap,
      style: ElevatedButton.styleFrom(
        backgroundColor: color,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      ),
      child: Text(
        label,
        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
      ),
    );
  }
}
