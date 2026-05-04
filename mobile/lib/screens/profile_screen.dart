import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import '../providers/auth_provider.dart';

final _profileDataProvider = FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  return api.getAthleteProfile();
});

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profileAsync = ref.watch(_profileDataProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Profile', style: TextStyle(fontWeight: FontWeight.w700)),
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
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
                    const Text('ATHLETE', style: TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Text(
                      profile['display_name'] as String? ?? profile['username'] as String? ?? '',
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 4),
                    Text(profile['username'] as String? ?? '',
                        style: const TextStyle(fontSize: 13, color: Color(0xFF888888))),
                    if ((profile['profile'] as String?)?.isNotEmpty == true) ...[
                      const SizedBox(height: 12),
                      const Divider(),
                      const SizedBox(height: 8),
                      Text(profile['profile'] as String,
                          style: const TextStyle(fontSize: 13, color: Color(0xFF444444))),
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
                    const Text('CONNECTED SERVICES', style: TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        if (profile['strava_athlete_id'] != null)
                          _ServiceButton(
                            label: 'STRAVA',
                            color: const Color(0xFFFC4C02),
                            onTap: () => launchUrl(Uri.parse('https://www.strava.com/athletes/${profile['strava_athlete_id']}')),
                          ),
                        const SizedBox(width: 12),
                        _ServiceButton(
                          label: 'STRYD',
                          color: const Color(0xFF00A0DF),
                          onTap: () => launchUrl(Uri.parse('https://www.stryd.com')),
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
                    const Text('APP', style: TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
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
                        icon: const Icon(Icons.logout, color: Color(0xFFEF4444)),
                        label: const Text('Logout', style: TextStyle(color: Color(0xFFEF4444))),
                        style: OutlinedButton.styleFrom(side: const BorderSide(color: Color(0xFFEF4444))),
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

            // Notifications placeholder
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('NOTIFICATIONS', style: TextStyle(fontSize: 10, color: Color(0xFF888888), letterSpacing: 1, fontWeight: FontWeight.w600)),
                    SizedBox(height: 8),
                    Text('Coming soon', style: TextStyle(fontSize: 13, color: Color(0xFFBBBBBB))),
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

class _ServiceButton extends StatelessWidget {
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _ServiceButton({required this.label, required this.color, required this.onTap});

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
      child: Text(label, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
    );
  }
}
