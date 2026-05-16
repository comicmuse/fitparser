import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import '../models/planned_workout.dart';
import '../providers/auth_provider.dart';
import '../widgets/power_zone_bar.dart';

/// Returns the badge label for a route source, or null if no badge should be shown.
String? routeSourceLabel(String? source) => switch (source) {
  'strava' => 'My routes',
  'previous' => 'Previously run',
  _ => null,
};

class WorkoutDetailScreen extends ConsumerStatefulWidget {
  final PlannedWorkout workout;
  const WorkoutDetailScreen({required this.workout, super.key});

  @override
  ConsumerState<WorkoutDetailScreen> createState() =>
      _WorkoutDetailScreenState();
}

class _WorkoutDetailScreenState extends ConsumerState<WorkoutDetailScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  List<Map<String, dynamic>>? _routes;
  int _routeIndex = 0;
  bool _loadingRoutes = false;
  bool _loadingOrs = false;
  String? _routeError;
  bool _routeTabVisited = false;
  Position? _prefetchedPosition;
  bool _savedRoutesDone = false;
  bool _orsOnTabVisit = false;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
    _tabs.addListener(_onTabChanged);
    _fetchSavedRoutes();
  }

  void _onTabChanged() {
    if (_tabs.index == 2 && !_tabs.indexIsChanging && !_routeTabVisited) {
      setState(() => _routeTabVisited = true);
      if (_savedRoutesDone && _prefetchedPosition != null) {
        _fetchOrsRoutes(_prefetchedPosition!);
      } else {
        _orsOnTabVisit = true;
      }
    }
  }

  // Phase 1: fetch saved/Strava routes. Called immediately on screen open so
  // results are ready by the time the user taps the Route tab.
  Future<void> _fetchSavedRoutes() async {
    setState(() {
      _loadingRoutes = true;
      _routeError = null;
    });
    try {
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        if (!mounted) return;
        setState(() {
          _loadingRoutes = false;
          _routeError = 'location_denied';
        });
        return;
      }

      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      ).timeout(const Duration(seconds: 15));

      final api = ref.read(apiServiceProvider);
      final distanceM = widget.workout.distanceM?.toInt() ?? 5000;

      final quickRoutes = await api.postRouteSuggestion(
        lat: position.latitude,
        lng: position.longitude,
        distanceM: distanceM,
        includeOrs: false,
      );

      if (!mounted) return;
      _prefetchedPosition = position;
      _savedRoutesDone = true;

      if (quickRoutes.isNotEmpty) {
        setState(() {
          _routes = quickRoutes;
          _routeIndex = 0;
          _loadingRoutes = false;
          _loadingOrs = _orsOnTabVisit;
        });
      }
      // If quickRoutes is empty, keep _loadingRoutes = true so the Route tab
      // spinner persists until ORS resolves (same behaviour as before).

      if (_orsOnTabVisit) {
        _fetchOrsRoutes(position);
      }
    } on TimeoutException {
      if (!mounted) return;
      setState(() {
        _loadingRoutes = false;
        _loadingOrs = false;
        _routeError = 'error';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loadingRoutes = false;
        _loadingOrs = false;
        _routeError = 'error';
      });
    }
  }

  // Phase 2: fetch ORS route suggestions. Called when the user first taps
  // the Route tab (or immediately after Phase 1 if the tab was already open).
  Future<void> _fetchOrsRoutes(Position position) async {
    if (!mounted) return;
    setState(() => _loadingOrs = true);

    try {
      final api = ref.read(apiServiceProvider);
      final distanceM = widget.workout.distanceM?.toInt() ?? 5000;

      final fullRoutes = await api.postRouteSuggestion(
        lat: position.latitude,
        lng: position.longitude,
        distanceM: distanceM,
      );

      if (!mounted) return;
      setState(() {
        _routes = fullRoutes.isNotEmpty ? fullRoutes : _routes;
        _routeIndex = _routeIndex.clamp(
          0,
          ((_routes?.length ?? 1) - 1).clamp(0, double.maxFinite.toInt()),
        );
        _loadingRoutes = false;
        _loadingOrs = false;
        if (_routes == null || _routes!.isEmpty) _routeError = 'error';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loadingRoutes = false;
        _loadingOrs = false;
        if (_routes == null || _routes!.isEmpty) _routeError = 'error';
      });
    }
  }

  @override
  void dispose() {
    _tabs.removeListener(_onTabChanged);
    _tabs.dispose();
    super.dispose();
  }

  String _formatDate(String isoDate) {
    try {
      final dt = DateTime.parse(isoDate);
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
      const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      return '${days[dt.weekday - 1]} ${dt.day} ${months[dt.month - 1]}';
    } catch (_) {
      return isoDate;
    }
  }

  String _buildSubtitle() {
    final parts = <String>[];
    if (widget.workout.durationS != null) {
      parts.add('${(widget.workout.durationS! / 60).round()} min');
    }
    if (widget.workout.distanceM != null) {
      parts.add('${(widget.workout.distanceM! / 1000).toStringAsFixed(1)} km');
    }
    return parts.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final subtitle = _buildSubtitle();
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        iconTheme: const IconThemeData(color: Colors.white),
        flexibleSpace: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              stops: [0.0, 0.5, 1.0],
              colors: [Color(0xFF1c1917), Color(0xFF9a3412), Color(0xFFea580c)],
            ),
          ),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _formatDate(widget.workout.date),
              style: const TextStyle(fontSize: 11, color: Color(0xFFFFD9B0)),
            ),
            Text(
              widget.workout.name,
              style: const TextStyle(
                fontWeight: FontWeight.w700,
                fontSize: 16,
                color: Colors.white,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            if (subtitle.isNotEmpty)
              Text(
                subtitle,
                style: const TextStyle(fontSize: 11, color: Color(0xFFFFD9B0)),
              ),
          ],
        ),
        bottom: TabBar(
          controller: _tabs,
          labelColor: Colors.white,
          unselectedLabelColor: const Color(0xFFFFD9B0),
          indicatorColor: Colors.white,
          tabs: const [
            Tab(text: 'Overview'),
            Tab(text: 'Structure'),
            Tab(text: 'Route'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          _OverviewTab(workout: widget.workout),
          _StructureTab(workout: widget.workout),
          _RouteTab(
            routes: _routes,
            loading: _loadingRoutes,
            loadingOrs: _loadingOrs,
            error: _routeError,
            routeIndex: _routeIndex,
            onPrev: _routeIndex > 0
                ? () => setState(() => _routeIndex--)
                : null,
            onNext: _routes != null && _routeIndex < _routes!.length - 1
                ? () => setState(() => _routeIndex++)
                : null,
            onRetry: () {
              setState(() {
                _routes = null;
                _routeError = null;
                _savedRoutesDone = false;
                _prefetchedPosition = null;
                _orsOnTabVisit = true;
              });
              _fetchSavedRoutes();
            },
          ),
        ],
      ),
    );
  }
}

class _OverviewTab extends StatelessWidget {
  final PlannedWorkout workout;
  const _OverviewTab({required this.workout});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
      children: [
        if (workout.description.isNotEmpty)
          Text(
            workout.description,
            style: const TextStyle(fontSize: 14, height: 1.6),
          ),
        const SizedBox(height: 8),
        PowerZoneBar(zones: workout.intensityZones),
      ],
    );
  }
}

class _StructureTab extends StatelessWidget {
  final PlannedWorkout workout;
  const _StructureTab({required this.workout});

  Color _blockColor(String intensityClass) => switch (intensityClass) {
    'work' || 'active' => const Color(0xFFF97316),
    'rest' => const Color(0xFF9CA3AF),
    'warmup' || 'cooldown' => const Color(0xFF2563EB),
    _ => const Color(0xFFCCCCCC),
  };

  Widget _buildSegmentCard(
    PlannedWorkoutSegment seg, {
    double horizontalMargin = 16,
  }) {
    final color = _blockColor(seg.intensityClass);
    final hasPower = seg.powerMinPct != null && seg.powerMaxPct != null;
    return Card(
      margin: EdgeInsets.symmetric(horizontal: horizontalMargin, vertical: 3),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border(left: BorderSide(color: color, width: 3)),
        ),
        padding: const EdgeInsets.all(12),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  seg.intensityClass.toUpperCase(),
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: color,
                    letterSpacing: 0.5,
                  ),
                ),
                if (hasPower) ...[
                  const SizedBox(height: 2),
                  Text(
                    '${seg.powerMinPct}–${seg.powerMaxPct}% CP',
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ],
            ),
            Text(
              seg.formattedDuration,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: Color(0xFF888888),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRepeatGroup(PlannedWorkoutBlock block, BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 14, 12, 4),
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            decoration: BoxDecoration(
              border: Border.all(color: const Color(0xFFF59E0B), width: 1.5),
              borderRadius: BorderRadius.circular(14),
              color: const Color(0xFFF59E0B).withValues(alpha: 0.06),
            ),
            padding: const EdgeInsets.fromLTRB(0, 10, 0, 6),
            child: Column(
              children: block.segments
                  .map((seg) => _buildSegmentCard(seg, horizontalMargin: 8))
                  .toList(),
            ),
          ),
          Positioned(
            top: -9,
            left: 12,
            child: Container(
              color: Theme.of(context).scaffoldBackgroundColor,
              padding: const EdgeInsets.symmetric(horizontal: 6),
              child: Text(
                '× ${block.repeat} REPEAT',
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFFF59E0B),
                  letterSpacing: 0.5,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final structure = workout.structure;
    if (structure == null || structure.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'No structure data available for this workout',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFF888888)),
          ),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(vertical: 12),
      itemCount: structure.length,
      itemBuilder: (context, i) {
        final block = structure[i];
        if (block.repeat > 1) {
          return _buildRepeatGroup(block, context);
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: block.segments
              .map((seg) => _buildSegmentCard(seg))
              .toList(),
        );
      },
    );
  }
}

class _RouteTab extends StatefulWidget {
  final List<Map<String, dynamic>>? routes;
  final bool loading;
  final bool loadingOrs;
  final String? error;
  final int routeIndex;
  final VoidCallback? onPrev;
  final VoidCallback? onNext;
  final VoidCallback onRetry;

  const _RouteTab({
    required this.routes,
    required this.loading,
    required this.loadingOrs,
    required this.error,
    required this.routeIndex,
    required this.onPrev,
    required this.onNext,
    required this.onRetry,
  });

  @override
  State<_RouteTab> createState() => _RouteTabState();
}

class _RouteTabState extends State<_RouteTab> {
  final MapController _mapController = MapController();

  List<LatLng> _pointsForIndex(int index) {
    final routes = widget.routes;
    if (routes == null || routes.isEmpty || index >= routes.length) return [];
    final rawCoords = routes[index]['coords'] as List<dynamic>;
    return rawCoords.map((c) {
      final pt = c as List<dynamic>;
      return LatLng((pt[0] as num).toDouble(), (pt[1] as num).toDouble());
    }).toList();
  }

  void _fitToCurrentRoute() {
    final points = _pointsForIndex(widget.routeIndex);
    if (points.isEmpty) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _mapController.fitCamera(
          CameraFit.coordinates(
            coordinates: points,
            padding: const EdgeInsets.all(32),
          ),
        );
      }
    });
  }

  @override
  void didUpdateWidget(_RouteTab oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.routes != oldWidget.routes ||
        widget.routeIndex != oldWidget.routeIndex) {
      _fitToCurrentRoute();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (widget.error == 'location_denied') {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'Location access needed for route suggestions',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFF888888)),
          ),
        ),
      );
    }

    if (widget.error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text(
              "Couldn't load route suggestions",
              style: TextStyle(color: Color(0xFF888888)),
            ),
            const SizedBox(height: 16),
            OutlinedButton(
              onPressed: widget.onRetry,
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    if (widget.routes == null) return const SizedBox.shrink();

    if (widget.routes!.isEmpty) {
      return const Center(
        child: Text(
          "Couldn't load route suggestions",
          style: TextStyle(color: Color(0xFF888888)),
        ),
      );
    }

    final route = widget.routes![widget.routeIndex];
    final points = _pointsForIndex(widget.routeIndex);

    return Column(
      children: [
        Expanded(
          child: Stack(
            children: [
              FlutterMap(
                mapController: _mapController,
                options: MapOptions(
                  initialCameraFit: CameraFit.coordinates(
                    coordinates: points,
                    padding: const EdgeInsets.all(32),
                  ),
                  interactionOptions: const InteractionOptions(
                    flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
                  ),
                ),
                children: [
                  TileLayer(
                    urlTemplate:
                        'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'com.runcoach.app',
                  ),
                  PolylineLayer(
                    polylines: [
                      Polyline(
                        points: points,
                        color: const Color(0xFFea580c),
                        strokeWidth: 3,
                      ),
                    ],
                  ),
                  if (points.isNotEmpty)
                    MarkerLayer(
                      markers: [
                        Marker(
                          point: points.first,
                          child: const Icon(
                            Icons.circle,
                            color: Color(0xFF4ADE80),
                            size: 12,
                          ),
                        ),
                      ],
                    ),
                ],
              ),
              if (routeSourceLabel(route['source'] as String?) != null)
                Positioned(
                  top: 12,
                  left: 12,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 5,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.black87,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      routeSourceLabel(route['source'] as String?)!,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              if ((route['name'] as String?) != null &&
                  routeSourceLabel(route['source'] as String?) != null)
                Positioned(
                  top: 44,
                  left: 12,
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      maxWidth: MediaQuery.of(context).size.width - 24,
                    ),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.black54,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        route['name'] as String,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 11,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              TextButton.icon(
                onPressed: widget.onPrev,
                icon: const Icon(Icons.chevron_left),
                label: const Text('Prev'),
              ),
              Text(
                widget.loadingOrs
                    ? 'Route ${widget.routeIndex + 1} of ${widget.routes!.length} · Finding more…'
                    : 'Route ${widget.routeIndex + 1} of ${widget.routes!.length}',
                style: const TextStyle(fontSize: 13, color: Color(0xFF888888)),
              ),
              TextButton.icon(
                onPressed: widget.onNext,
                icon: const Icon(Icons.chevron_right),
                label: const Text('Next'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
