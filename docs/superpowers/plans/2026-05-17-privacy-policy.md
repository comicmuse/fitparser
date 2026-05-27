# Privacy Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GDPR-compliant privacy policy served at `GET /privacy`, linked from the web footer and a Flutter profile screen tile.

**Architecture:** A plain Flask route renders a static HTML template extending `base.html`. The footer in `base.html` links to it. The Flutter profile screen gains a "Legal" card with a `ListTile` that opens the URL in the external browser via `launchUrl`.

**Tech Stack:** Flask/Jinja2 (web), Flutter/url_launcher (mobile), Playwright (E2E tests), flutter_test (widget tests)

---

### Task 1: Flask `/privacy` route, template, and E2E tests

**Files:**
- Create: `runcoach/web/templates/privacy.html`
- Modify: `runcoach/web/routes.py`
- Create: `tests/e2e/test_privacy.py`

- [ ] **Step 1: Write the failing E2E test**

Create `tests/e2e/test_privacy.py`:

```python
"""Playwright E2E tests for the privacy policy page."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_privacy_page_returns_200(page, server_url):
    """GET /privacy returns 200 with expected heading."""
    page.goto(f"{server_url}/privacy")
    page.wait_for_load_state("networkidle")
    expect(page.locator("h1")).to_contain_text("Privacy Policy")


def test_privacy_page_no_login_required(page, server_url):
    """/privacy is accessible without authentication."""
    page.goto(f"{server_url}/privacy")
    # Should not be redirected to /login
    assert "/login" not in page.url
    assert page.url.endswith("/privacy")
```

- [ ] **Step 2: Run E2E tests to confirm they fail**

```bash
pytest tests/e2e/test_privacy.py -v --no-cov
```

Expected: FAIL — `GET /privacy` returns a 404 (route does not exist yet).

- [ ] **Step 3: Add the `/privacy` route to `routes.py`**

In `runcoach/web/routes.py`, add after the `offline` route (around line 499):

```python
@bp.route("/privacy")
def privacy():
    return render_template("privacy.html")
```

- [ ] **Step 4: Create `privacy.html`**

Create `runcoach/web/templates/privacy.html`:

```html
{% extends "base.html" %}
{% block title %}Privacy Policy — RunCoach{% endblock %}
{% block content %}
<div class="card" style="max-width: 720px; margin: 0 auto;">
  <h1 style="font-size:1.5rem; margin-bottom:1rem;">Privacy Policy</h1>
  <p style="color:var(--fg-muted); font-size:0.85rem; margin-bottom:1.5rem;">Last updated: May 2026</p>

  <p>This policy covers RunCoach. It applies to the central hosted service at
  <strong>runcoach.linehan.me.uk</strong> and to self-hosted instances. For
  self-hosted deployments, the person or organisation operating the server is
  the data controller and is responsible for their own privacy policy — this
  document serves as a template and reference.</p>

  <h2 style="margin-top:1.5rem; margin-bottom:0.5rem;">1. Data Controller</h2>
  <p>For the central service: <strong>Colm Linehan</strong>,
  <a href="mailto:runcoach@linehan.me.uk">runcoach@linehan.me.uk</a>.<br>
  For self-hosted instances: the operator of that instance.</p>

  <h2 style="margin-top:1.5rem; margin-bottom:0.5rem;">2. Data We Collect</h2>
  <div class="table-scroll">
  <table>
    <thead><tr><th>Data</th><th>Details</th></tr></thead>
    <tbody>
      <tr><td>Account credentials</td><td>Email address; bcrypt password hash — your password is never stored in plaintext.</td></tr>
      <tr><td>FIT activity files</td><td>Garmin FIT files downloaded from Stryd or uploaded manually; contains GPS track, power, heart rate, and pace data.</td></tr>
      <tr><td>Athlete profile</td><td>Free-text description entered by you; used as context in AI coaching prompts.</td></tr>
      <tr><td>AI chat history</td><td>Conversation messages per run, stored in the database.</td></tr>
      <tr><td>Strava OAuth tokens</td><td>Access and refresh tokens, stored only if you connect Strava (optional).</td></tr>
      <tr><td>FCM device token</td><td>Android push notification token, stored only if you enable notifications (optional).</td></tr>
    </tbody>
  </table>
  </div>

  <h2 style="margin-top:1.5rem; margin-bottom:0.5rem;">3. Third-Party Data Processors</h2>

  <p><strong>Stryd</strong><br>
  RunCoach fetches activity data from Stryd on your behalf using your Stryd credentials.
  Data held by Stryd is governed by Stryd's own privacy policy.</p>

  <p><strong>OpenAI / Anthropic</strong> (central service, if configured)<br>
  Workout data — power zone breakdown, heart rate, RSS score, duration, distance, and your
  athlete profile text — is sent to the configured LLM provider for AI coaching analysis.
  Both OpenAI and Anthropic operate data processing agreements and process data on servers
  in the United States (see International Transfers below). Self-hosters who configure
  Ollama keep all data local.</p>

  <p><strong>Strava</strong> (optional)<br>
  If you connect Strava, RunCoach stores OAuth tokens and fetches route polylines.
  Governed by Strava's privacy policy.</p>

  <p><strong>Firebase / Google FCM</strong> (central service, Android)<br>
  Android device tokens are sent to Google's Firebase Cloud Messaging service to deliver
  push notifications. Self-hosters can run without FCM by not setting
  <code>FCM_SERVICE_ACCOUNT_PATH</code>.</p>

  <p><strong>OpenRouteService</strong> (optional)<br>
  If route suggestions are used, GPS coordinates are sent to the OpenRouteService API.
  Governed by ORS's privacy policy.</p>

  <h2 style="margin-top:1.5rem; margin-bottom:0.5rem;">4. Legal Basis (GDPR)</h2>
  <div class="table-scroll">
  <table>
    <thead><tr><th>Purpose</th><th>Legal basis</th></tr></thead>
    <tbody>
      <tr><td>Account, activity storage, AI analysis</td><td>Contractual necessity (Art. 6(1)(b)) — required to provide the service.</td></tr>
      <tr><td>Strava integration</td><td>Consent (Art. 6(1)(a)) — user-initiated, can be revoked at any time.</td></tr>
      <tr><td>Push notifications</td><td>Consent (Art. 6(1)(a)) — user-initiated, can be revoked at any time.</td></tr>
    </tbody>
  </table>
  </div>

  <h2 style="margin-top:1.5rem; margin-bottom:0.5rem;">5. Data Retention</h2>
  <p>Data is stored for as long as your account exists. Users of the central service may
  request deletion by emailing
  <a href="mailto:runcoach@linehan.me.uk">runcoach@linehan.me.uk</a>. For self-hosted
  instances, contact your administrator.</p>

  <h2 style="margin-top:1.5rem; margin-bottom:0.5rem;">6. Your Rights (GDPR)</h2>
  <p>You have the right to:</p>
  <ul style="margin: 0.5rem 0 0.75rem 1.5rem;">
    <li><strong>Access</strong> — request a copy of your personal data</li>
    <li><strong>Rectification</strong> — correct inaccurate data</li>
    <li><strong>Erasure</strong> — request deletion of your data</li>
    <li><strong>Portability</strong> — receive your data in a machine-readable format</li>
    <li><strong>Object</strong> — object to processing based on legitimate interest</li>
    <li><strong>Complain</strong> — lodge a complaint with the UK Information Commissioner's Office (ICO) at <a href="https://ico.org.uk" target="_blank" rel="noopener">ico.org.uk</a></li>
  </ul>
  <p>To exercise any of these rights, contact
  <a href="mailto:runcoach@linehan.me.uk">runcoach@linehan.me.uk</a> (central service)
  or your instance administrator (self-hosted).</p>

  <h2 style="margin-top:1.5rem; margin-bottom:0.5rem;">7. International Transfers</h2>
  <p>OpenAI and Anthropic process data on servers in the United States. Where required,
  transfers rely on Standard Contractual Clauses (SCCs) under UK/EU GDPR. Self-hosters
  using Ollama keep all data on their own infrastructure.</p>
</div>
{% endblock %}
```

- [ ] **Step 5: Run E2E tests to confirm they pass**

```bash
pytest tests/e2e/test_privacy.py -v --no-cov
```

Expected: PASS — both tests green.

- [ ] **Step 6: Commit**

```bash
git add runcoach/web/routes.py runcoach/web/templates/privacy.html tests/e2e/test_privacy.py
git commit -m "feat: add GET /privacy route and GDPR privacy policy page

Closes part of #38"
```

---

### Task 2: Privacy Policy link in web footer

**Files:**
- Modify: `runcoach/web/templates/base.html`

- [ ] **Step 1: Add a failing E2E assertion for the footer link**

Append to `tests/e2e/test_privacy.py`:

```python
def test_privacy_link_in_footer(logged_in_page, server_url):
    """Privacy Policy link is present in the footer on the main index page."""
    page = logged_in_page
    page.goto(server_url)
    page.wait_for_load_state("networkidle")
    link = page.locator("footer a", has_text="Privacy Policy")
    expect(link).to_be_visible()
    expect(link).to_have_attribute("href", "/privacy")
```

- [ ] **Step 2: Run the new test to confirm it fails**

```bash
pytest tests/e2e/test_privacy.py::test_privacy_link_in_footer -v --no-cov
```

Expected: FAIL — no such link exists in the footer yet.

- [ ] **Step 3: Add the Privacy Policy link to the footer in `base.html`**

In `runcoach/web/templates/base.html`, replace the footer (lines 596–598):

```html
  <footer>
    <div class="container">RunCoach &mdash; Your AI running coach &mdash; <a href="/privacy">Privacy Policy</a></div>
  </footer>
```

- [ ] **Step 4: Run all three privacy E2E tests to confirm they pass**

```bash
pytest tests/e2e/test_privacy.py -v --no-cov
```

Expected: all three tests PASS.

- [ ] **Step 5: Commit**

```bash
git add runcoach/web/templates/base.html tests/e2e/test_privacy.py
git commit -m "feat: add Privacy Policy link to web footer (#38)"
```

---

### Task 3: Privacy Policy tile in Flutter profile screen

**Files:**
- Modify: `mobile/lib/screens/profile_screen.dart`
- Create: `mobile/test/screens/profile_screen_privacy_test.dart`

- [ ] **Step 1: Write the failing widget test**

Create `mobile/test/screens/profile_screen_privacy_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/providers/auth_provider.dart';
import 'package:runcoach/screens/profile_screen.dart';

void main() {
  group('ProfileScreen privacy', () {
    testWidgets('shows Privacy Policy tile', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            _profileDataProvider.overrideWith(
              (ref) async => {
                'athlete_profile': '',
                'strava_athlete_id': null,
              },
            ),
          ],
          child: const MaterialApp(home: ProfileScreen()),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Privacy Policy'), findsOneWidget);
    });
  });
}
```

> **Note:** `_profileDataProvider` is a private provider declared in `profile_screen.dart`. To make it accessible to the test, promote it to package-private by removing the leading underscore in `profile_screen.dart` (rename `_profileDataProvider` → `profileDataProvider` in both the declaration and the one `ref.watch` call that uses it). This is the standard pattern used throughout the codebase.

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd mobile && flutter test test/screens/profile_screen_privacy_test.dart
```

Expected: compile error — `_profileDataProvider` is private.

- [ ] **Step 3: Rename `_profileDataProvider` to `profileDataProvider` in `profile_screen.dart`**

In `mobile/lib/screens/profile_screen.dart`, change lines 6–11:

```dart
final profileDataProvider = FutureProvider.autoDispose<Map<String, dynamic>>((
  ref,
) async {
  final api = ref.read(apiServiceProvider);
  return api.getAthleteProfile();
});
```

And update the `ref.watch` call in `build` (line 18):

```dart
final profileAsync = ref.watch(profileDataProvider);
```

- [ ] **Step 4: Add the LEGAL card with Privacy Policy `ListTile` in `profile_screen.dart`**

After the Notifications card closing `),` and before the final `]` of the ListView children (around line 231), insert:

```dart
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
                      ),
                    ),
                  ],
                ),
              ),
            ),
```

- [ ] **Step 5: Update the test to use the renamed provider**

In `mobile/test/screens/profile_screen_privacy_test.dart`, replace `_profileDataProvider` with `profileDataProvider` and add the import:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/screens/profile_screen.dart';

void main() {
  group('ProfileScreen privacy', () {
    testWidgets('shows Privacy Policy tile', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            profileDataProvider.overrideWith(
              (ref) async => {
                'athlete_profile': '',
                'strava_athlete_id': null,
              },
            ),
          ],
          child: const MaterialApp(home: ProfileScreen()),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Privacy Policy'), findsOneWidget);
    });
  });
}
```

- [ ] **Step 6: Run the widget test to confirm it passes**

```bash
cd mobile && flutter test test/screens/profile_screen_privacy_test.dart
```

Expected: PASS.

- [ ] **Step 7: Run dart format**

```bash
cd mobile && dart format --output=none --set-exit-if-changed .
```

Expected: exit 0 (no formatting issues). If it exits non-zero, run `dart format .` and re-check.

- [ ] **Step 8: Run the full Flutter test suite with coverage to confirm no regressions**

```bash
cd mobile && flutter test --coverage --concurrency=1
```

Expected: all tests PASS with no segfaults.

- [ ] **Step 9: Commit**

```bash
cd /home/colm/git/fitparser
git add mobile/lib/screens/profile_screen.dart mobile/test/screens/profile_screen_privacy_test.dart
git commit -m "feat: add Privacy Policy tile to Flutter profile screen (#38)"
```

---

### Task 4: Final verification and PR

- [ ] **Step 1: Run the full Python test suite including E2E**

```bash
pytest && pytest -m e2e --no-cov -v
```

Expected: all tests PASS.

- [ ] **Step 2: Raise the PR**

```bash
git checkout -b feature/issue-38-privacy-policy
git push -u origin feature/issue-38-privacy-policy
gh pr create \
  --title "feat: add GDPR-compliant privacy policy (#38)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `GET /privacy` Flask route serving a GDPR-compliant privacy policy page (no auth required)
- Links to `/privacy` from the web footer on every page
- Adds a "Privacy Policy" tile in the Flutter profile screen opening the URL externally

## Test plan
- [ ] `pytest tests/e2e/test_privacy.py -v --no-cov` — all three E2E tests pass
- [ ] `pytest` — full Python unit suite passes
- [ ] `pytest -m e2e --no-cov -v` — full E2E suite passes
- [ ] `cd mobile && flutter test test/screens/profile_screen_privacy_test.dart` — widget test passes
- [ ] `cd mobile && flutter test --coverage --concurrency=1` — full Flutter suite passes, no segfault

Closes #38

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
