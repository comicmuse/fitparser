# RunCoach Android App — Design Spec

**Date:** 2026-05-03  
**Status:** Approved for implementation planning

---

## Overview

A Flutter Android app for RunCoach that surfaces workout analysis, training load, and AI coaching on mobile. The app authenticates via JWT, communicates exclusively with the existing `/api/v1` REST API, and lives in a `mobile/` subdirectory of the `fitparser` monorepo.

Priority: the most recent activity and next planned workout are front-and-centre. Historical activities are accessible but secondary.

---

## Technology Choices

| Concern | Choice | Reason |
|---|---|---|
| Framework | Flutter (Dart) | Superior visual polish, excellent charting (fl_chart), pixel-consistent across Android versions |
| State management | Riverpod | Clean provider/consumer separation, good async handling for JWT refresh |
| Navigation | go_router | Shell routes for bottom nav, push routes for detail screens |
| JWT storage | flutter_secure_storage | Android Keystore — never SharedPreferences |
| Charts | fl_chart | LineChart for RSB sparkline, BarChart for HR zones |
| Maps | flutter_map + OpenStreetMap tiles | Renders Strava polyline, no Google Maps API key required |
| Markdown | flutter_markdown | Renders LLM coaching commentary |
| HTTP | dio | Interceptor-based JWT refresh, consistent error handling |

---

## Repository Structure

```
fitparser/
  mobile/
    lib/
      main.dart
      app.dart                  # MaterialApp, go_router setup, theme
      models/                   # Dart data classes (Run, TrainingSummary, Block, etc.)
      providers/                # Riverpod providers (auth, runs, dashboard, chat)
      services/
        api_service.dart        # dio client, JWT inject/refresh
        secure_storage.dart     # token read/write
      screens/
        login_screen.dart
        home_screen.dart
        activities_screen.dart
        profile_screen.dart
        run_detail_screen.dart  # hosts tab controller
      widgets/
        rsb_card.dart
        run_card.dart
        next_workout_card.dart
        hr_zones_bar.dart
        block_card.dart
        route_map.dart
        coaching_chat.dart
    pubspec.yaml
    android/
```

---

## Navigation Structure

```
Root
├── /login                     (no auth required)
└── Shell (BottomNavigationBar)
    ├── /home                  (Home tab)
    │   └── /run/:id           (RunDetail — push)
    ├── /activities            (Activities tab)
    │   └── /run/:id           (RunDetail — push)
    └── /profile               (Profile tab)
```

The bottom nav has **3 tabs**: Home · Activities · Profile.

RunDetail is a push route navigated to from both Home and Activities. The back button returns to the originating tab.

---

## Authentication

- Login screen shown when no valid access token exists in secure storage
- `POST /api/v1/auth/login` → stores `access_token` + `refresh_token`
- dio interceptor: on 401, attempts `POST /api/v1/auth/refresh` automatically, retries original request
- On refresh failure: clear tokens, redirect to login
- Logout: `POST /api/v1/auth/logout`, clear stored tokens, navigate to login

---

## Screens

### Login

- Email + password fields
- Submit button → JWT login
- Error message on invalid credentials
- No registration (web-only flow)

---

### Home

Data source: `GET /api/v1/dashboard` (new endpoint — see API Changes)

**RSB Card**
- Large RSB value with colour coding: green (> +5, "Fresh"), neutral grey (−10 to +5, "Balanced"), red (< −10, "Fatigued")
- CTL and ATL values below
- 30-day RSB sparkline (fl_chart LineChart, green line + purple CTL dashed line)

**Latest Run Card**
- Run name, date
- 4-metric row: distance (km) · duration · avg power (W) · avg HR
- Tappable → RunDetail, opens on Overview tab

**Next Workout Card** (shown only if available from Stryd plan)
- Amber left-border card
- Date, workout name, target power range
- Sourced from `next_workout` in dashboard response

**Pull-to-refresh** re-fetches dashboard.

---

### Activities

Data source: `GET /api/v1/runs?page=N&per_page=20`

**App bar**
- Title: "Activities"
- "Sync Now" icon button → `POST /api/v1/sync`, shows snackbar on completion

**Year/month filter chips**
- Horizontal scrollable row of chips: current year selected by default, then month chips for that year
- Selecting a chip passes `year` and `month` query params to `GET /api/v1/runs` — requires a small backend addition to filter by date (client-side filtering won't work correctly with pagination)

**Run list**
- Grouped by month with section headers
- Infinite scroll with pagination (20 per page)
- Each row: name, date, distance, duration, avg power, avg HR, stage badge (analysed/parsed/synced/error)
- Tappable → RunDetail

---

### Profile

**Athlete info section**
- Display name, email (read-only)
- Athlete profile text (read-only — edit via web)

**Connected services section**
- STRAVA button (orange): opens `https://www.strava.com/athletes/{strava_athlete_id}` in browser. Shown only if `strava_athlete_id` is set on the user (stored in `users` table, populated during OAuth connect).
- STRYD button (blue): opens `https://www.stryd.com` in browser.

**App section**
- "Sync Now" button → `POST /api/v1/sync`
- Logout button

**Notifications section** (placeholder, not wired in v1)
- Reserved space for "Enable Notifications" toggle — renders nothing in v1 but the section header is present so the layout is established. This ensures adding `firebase_messaging` later doesn't require a layout redesign.

---

### RunDetail

Header (persistent across tabs):
- Back button (←)
- Run name + date
- STRAVA text button (orange) → opens Strava activity URL. Hidden if no `strava_activity_id`.
- STRYD text button (blue) → opens Stryd activity URL. Hidden if no `stryd_activity_id`.

**Three swipeable tabs: Overview · Blocks · Coaching**

#### Overview Tab

1. **4-metric row** (white card): distance · duration · avg power · avg HR
2. **Badges row**: RSS pill (purple), stage pill (green=analysed, amber=parsed, grey=synced, red=error)
3. **HR Zones bar** (white card): horizontal segmented bar, 5 zones (Z1 blue → Z5 red), percentage labels below each segment
4. **Stryd Prescribed Workout card** (blue left-border, shown only if `prescribed_workout` present in YAML): workout name + description text
5. **Route map** (flutter_map): renders decoded Strava polyline on OSM tiles. Green start dot, red end dot. Hidden if no polyline data.

#### Blocks Tab

Scrollable list of workout blocks from `yaml_data.blocks`:

Each block card:
- **Colour-coded left border**: warmup/cooldown = blue (`#2563eb`), work = orange (`#f97316`), rest = grey (`#9ca3af`)
- Block type label (uppercase) + duration
- Metrics row: avg power, avg HR, pace
- **Work blocks only**: target power range + compliance bar (3-segment: below/in-zone/above, coloured blue/green/orange) + percentage labels

#### Coaching Tab

- **AI commentary** rendered as the first "message" in the thread: purple AI avatar chip, "RunCoach" label, timestamp, full markdown commentary below (flutter_markdown)
- **Chat thread**: user messages right-aligned (purple bubble), AI responses left-aligned (white card)
- **Fixed input bar** at bottom: text field ("Ask a follow-up question…") + send button (purple circle, arrow icon)
- **Loading state**: if `stage != 'analysed'`, show "Analysis not yet available" placeholder instead of commentary
- Sends `POST /api/v1/runs/:id/chat`, appends response to thread

---

## API Changes Required

### 1. New endpoint: `GET /api/v1/dashboard`

Returns data needed for the Home screen in a single request.

```json
{
  "latest_run": { ...run object... },
  "next_workout": {
    "date": "2026-05-01",
    "name": "Easy Recovery Run",
    "description": "45–60 min @ 220–240W"
  },
  "training_summary": {
    "current_rsb": { "rsb": 8.2, "ctl": 52.4, "atl": 44.1, "interpretation": "fresh" },
    "rsb_history": [
      { "date": "2026-04-03", "rsb": 4.1, "ctl": 48.2, "atl": 44.1 },
      ...30 days...
    ]
  }
}
```

Implementation: call `build_training_summary()` from `context.py`, fetch latest run, fetch next planned workout from `planned_workouts` table.

### 2. Add Strava/Stryd IDs to run response

In `format_run_for_api()` in `api.py`, add:

```python
"strava_activity_id": run["strava_activity_id"],
"stryd_activity_id": run["stryd_activity_id"],
```

### 3. Year/month filtering on runs list

Add optional `year` and `month` query params to `GET /api/v1/runs`:

```
GET /api/v1/runs?year=2026&month=4&page=1&per_page=20
```

Filters runs by date in the DB query. Both params optional; `month` requires `year`.

### 4. Expose `strava_athlete_id` from athlete profile endpoint

`GET /api/v1/athlete/profile` should include `strava_athlete_id` from the `users` table so the Profile screen can construct the Strava profile URL.

---

## Theme

| Token | Value |
|---|---|
| Background | `#f5f5f5` |
| Surface (cards) | `#ffffff` |
| Primary accent | `#6750a4` (purple) |
| RSB positive | `#2e7d32` (green) |
| RSB negative | `#ef4444` (red) |
| Next workout | `#f59e0b` (amber) |
| Stryd blue | `#00a0df` |
| Strava orange | `#fc4c02` |
| Border radius | 12dp (cards), 20dp (pills/chips) |
| Font | Roboto (system default) |

Dark mode: not in v1.

---

## Out of Scope (v1)

- Manual FIT file upload
- Push notifications — **architecture must not block future implementation**. Profile screen reserves a "Notifications" section. No custom notification handling that would conflict with `firebase_messaging`.
- Admin user management
- Athlete profile editing (web-only)
- iOS build (Flutter supports it — not tested or distributed in v1)
- Coach tab on main nav (deferred until clear purpose defined)
