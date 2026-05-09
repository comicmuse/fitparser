# Repeat Group Visualisation — Structure Tab Design

## Goal

Make repeat blocks visually distinct on the Structure tab of the planned workout detail screen in the Flutter mobile app. Currently, repeat groups show only a small grey "× N" text label above their segments, with no border or grouping around the cards. The change wraps repeat groups in an amber-bordered panel so the structure is immediately legible at a glance.

## Context

- `PlannedWorkoutBlock` already has a `repeat: int` field populated from the API.
- `_StructureTab` in `workout_detail_screen.dart` renders blocks as a `ListView.builder`. Blocks with `repeat > 1` already emit a `"× N"` `Text` widget above their segments — this is the only current indication of a repeat.
- Blocks with `repeat == 1` (warmup, cooldown, standalone intervals) are unaffected.
- No backend, API, or data model changes are needed.

## Design

### Visual treatment

Blocks with `repeat > 1` are wrapped in a `Container` with:
- **Border**: `1.5dp` solid `Color(0xFFF59E0B)` (amber), `BorderRadius.circular(14)`
- **Background**: `Color(0xFFF59E0B)` at 6% opacity
- **Label**: `"× N REPEAT"` chip sitting above the top-left of the border, implemented as a `Stack` with a `Positioned` label that has a small background matching the scaffold to create the "cut out of the border" effect

The segment cards inside the group keep their existing `margin: EdgeInsets.symmetric(horizontal: 8, vertical: 3)` (tighter than the outer `16` used for standalone cards, so they sit comfortably inside the band).

Standalone blocks (`repeat == 1`) render exactly as before, using `margin: EdgeInsets.symmetric(horizontal: 16, vertical: 3)`.

### Widget structure (pseudocode)

```dart
// In _StructureTab.build → ListView.builder itemBuilder:

final block = structure[i];

if (block.repeat > 1) {
  return Padding(
    padding: EdgeInsets.fromLTRB(12, 10, 12, 4),
    child: Stack(
      clipBehavior: Clip.none,
      children: [
        Container(
          decoration: BoxDecoration(
            border: Border.all(color: Color(0xFFF59E0B), width: 1.5),
            borderRadius: BorderRadius.circular(14),
            color: Color(0xFFF59E0B).withOpacity(0.06),
          ),
          padding: EdgeInsets.fromLTRB(0, 10, 0, 6),
          child: Column(
            children: block.segments.map(_buildSegmentCard).toList(),
          ),
        ),
        Positioned(
          top: -9,
          left: 12,
          child: Container(
            color: scaffoldBackground,  // Color(0xFF161b22) or Theme.of(context).scaffoldBackgroundColor
            padding: EdgeInsets.symmetric(horizontal: 6),
            child: Text(
              '× ${block.repeat} REPEAT',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700,
                               color: Color(0xFFF59E0B), letterSpacing: 0.5),
            ),
          ),
        ),
      ],
    ),
  );
} else {
  return Column(
    children: block.segments.map(_buildSegmentCard).toList(),
  );
}
```

`_buildSegmentCard` extracts the existing inline segment card widget (currently inlined in the `...block.segments.map(...)` call) into a private method, accepting a margin parameter so inner cards use `8` and outer cards use `16`.

### Refactor: extract `_buildSegmentCard`

The existing segment card markup is duplicated inside the `map`. Extract to `Widget _buildSegmentCard(PlannedWorkoutSegment seg, {double horizontalMargin = 16})` to avoid repeating it for the two render paths (inside band vs standalone).

## Files Changed

- **Modify**: `mobile/lib/screens/workout_detail_screen.dart`
  - Extract `_buildSegmentCard` helper
  - Conditional wrap in amber `Stack`/`Container` for `repeat > 1`
- **Add**: `mobile/test/screens/workout_detail_screen_test.dart`
  - Widget test: repeat group renders amber border container
  - Widget test: `repeat == 1` block renders without amber container
  - Widget test: `"× 5 REPEAT"` label visible for 5-repeat block

## What Does Not Change

- `PlannedWorkoutBlock` / `PlannedWorkoutSegment` models — untouched
- API / backend — untouched
- `_OverviewTab`, `_RouteTab` — untouched
- Blocks with `repeat == 1` — render identically to today
