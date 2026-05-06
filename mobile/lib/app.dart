import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'providers/auth_provider.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'screens/activities_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/run_detail_screen.dart';
import 'screens/workout_detail_screen.dart';
import 'models/planned_workout.dart';

final _rootNavKey = GlobalKey<NavigatorState>();
final _shellNavKey = GlobalKey<NavigatorState>();

class _RouterNotifier extends ChangeNotifier {
  AuthStatus _authStatus = AuthStatus.unknown;
  AuthStatus get authStatus => _authStatus;
  void update(AuthStatus status) {
    _authStatus = status;
    notifyListeners();
  }
}

final _routerNotifierProvider = Provider<_RouterNotifier>((ref) {
  final notifier = _RouterNotifier();
  ref.listen<AuthStatus>(authProvider, (_, next) => notifier.update(next));
  ref.onDispose(notifier.dispose);
  return notifier;
});

final routerProvider = Provider<GoRouter>((ref) {
  final notifier = ref.watch(_routerNotifierProvider);

  return GoRouter(
    navigatorKey: _rootNavKey,
    refreshListenable: notifier,
    redirect: (context, state) {
      final isLoginRoute = state.matchedLocation == '/login';
      final authStatus = notifier.authStatus;
      if (authStatus == AuthStatus.unauthenticated && !isLoginRoute)
        return '/login';
      if (authStatus == AuthStatus.authenticated && isLoginRoute)
        return '/home';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(
        path: '/workout-detail',
        parentNavigatorKey: _rootNavKey,
        builder: (context, state) => WorkoutDetailScreen(
          workout: state.extra as PlannedWorkout,
        ),
      ),
      ShellRoute(
        navigatorKey: _shellNavKey,
        builder: (context, state, child) => ScaffoldWithNavBar(child: child),
        routes: [
          GoRoute(
            path: '/home',
            builder: (_, __) => const HomeScreen(),
            routes: [
              GoRoute(
                path: 'run/:id',
                parentNavigatorKey: _rootNavKey,
                builder: (_, state) => RunDetailScreen(
                  runId: int.parse(state.pathParameters['id']!),
                ),
              ),
            ],
          ),
          GoRoute(
            path: '/activities',
            builder: (_, __) => const ActivitiesScreen(),
            routes: [
              GoRoute(
                path: 'run/:id',
                parentNavigatorKey: _rootNavKey,
                builder: (_, state) => RunDetailScreen(
                  runId: int.parse(state.pathParameters['id']!),
                ),
              ),
            ],
          ),
          GoRoute(path: '/profile', builder: (_, __) => const ProfileScreen()),
        ],
      ),
    ],
    initialLocation: '/home',
  );
});

class ScaffoldWithNavBar extends ConsumerWidget {
  final Widget child;
  const ScaffoldWithNavBar({required this.child, super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;
    final index = switch (location) {
      String l when l.startsWith('/home') => 0,
      String l when l.startsWith('/activities') => 1,
      String l when l.startsWith('/profile') => 2,
      _ => 0,
    };

    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) {
          switch (i) {
            case 0:
              context.go('/home');
            case 1:
              context.go('/activities');
            case 2:
              context.go('/profile');
          }
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.list_outlined),
            selectedIcon: Icon(Icons.list),
            label: 'Activities',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Profile',
          ),
        ],
      ),
    );
  }
}

class RunCoachApp extends ConsumerWidget {
  const RunCoachApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'RunCoach',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6750A4),
          brightness: Brightness.light,
        ).copyWith(surface: Colors.white, onSurface: const Color(0xFF1A1A1A)),
        scaffoldBackgroundColor: const Color(0xFFF5F5F5),
        cardTheme: const CardThemeData(
          color: Colors.white,
          elevation: 1,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(12)),
          ),
        ),
        useMaterial3: true,
      ),
      routerConfig: router,
    );
  }
}
