# Privacy Policy — Design Spec

**Issue:** #38  
**Date:** 2026-05-17  

## Overview

Add a GDPR-compliant privacy policy covering the web app and Android app. One document distinguishes between the central hosted service (runcoach.linehan.me.uk) and self-hosted instances. The policy is served as a web page and linked from both the web UI and the Android app.

## Flask Web Route

- New `GET /privacy` route in `runcoach/web/routes.py`, no authentication required
- Renders a new `privacy.html` template extending `base.html` for consistent navigation
- No database access; purely static content
- A "Privacy Policy" link added to the footer in `base.html` so it is reachable from every page

## Flutter

- Single `ListTile` added to `profile_screen.dart`, below the existing Stryd external link
- Label: "Privacy Policy"
- Taps open `https://runcoach.linehan.me.uk/privacy` via the existing `launchUrl()` pattern
- No new dependencies, no new screen

## Privacy Policy Content Structure

The document is written in plain English. Central-vs-self-hosted distinctions are called out inline.

### 1. Who This Policy Applies To
The central hosted service at `runcoach.linehan.me.uk` and self-hosted instances. For self-hosted deployments, the person or organisation operating the server is the data controller and is responsible for their own privacy policy — this document serves as a template and reference.

### 2. Data Controller
- **Central service:** Colm Linehan, runcoach@linehan.me.uk
- **Self-hosted:** the operator of the instance

### 3. Data We Collect

| Data | Details |
|------|---------|
| Account credentials | Email address; bcrypt password hash (password never stored in plaintext) |
| FIT activity files | Garmin FIT files downloaded from Stryd or uploaded manually; contains GPS track, power, heart rate, pace |
| Athlete profile | Free-text description entered by the user; used as context in AI coaching prompts |
| AI chat history | Conversation messages per run, stored in the database |
| Strava OAuth tokens | Access and refresh tokens, stored if the user connects Strava (optional) |
| FCM device token | Android push notification token, stored if notifications are enabled (optional) |

### 4. Third-Party Data Processors

**Stryd**  
RunCoach fetches activity data from Stryd on the user's behalf using their Stryd credentials. Data held by Stryd is governed by Stryd's own privacy policy.

**OpenAI / Anthropic** (central service, if configured)  
Workout data — power zone breakdown, heart rate, RSS score, duration, distance, and the user's athlete profile text — is sent to the configured LLM provider for AI coaching analysis. Both OpenAI and Anthropic operate data processing agreements and process data on servers in the United States (see International Transfers below). Self-hosters who configure Ollama keep all data local.

**Strava** (optional)  
If the user connects Strava, RunCoach stores OAuth tokens and fetches route polylines. Governed by Strava's privacy policy.

**Firebase / Google FCM** (central service, Android)  
Android device tokens are sent to Google's Firebase Cloud Messaging service to deliver push notifications. Self-hosters can run without FCM by not setting `FCM_SERVICE_ACCOUNT_PATH`.

**OpenRouteService** (optional)  
If route suggestions are used, GPS coordinates are sent to the OpenRouteService API. Governed by ORS's privacy policy.

### 5. Legal Basis (GDPR)

| Purpose | Legal basis |
|---------|------------|
| Account, activity storage, AI analysis | Contractual necessity (Art. 6(1)(b)) — required to provide the service |
| Strava integration | Consent (Art. 6(1)(a)) — user-initiated, can be revoked |
| Push notifications | Consent (Art. 6(1)(a)) — user-initiated, can be revoked |

### 6. Data Retention

Data is stored for as long as the account exists. Users of the central service may request deletion by emailing runcoach@linehan.me.uk. For self-hosted instances, contact your administrator.

### 7. Your Rights (GDPR)

Users have the right to:
- **Access** — request a copy of their personal data
- **Rectification** — correct inaccurate data
- **Erasure** — request deletion of their data
- **Portability** — receive their data in a machine-readable format
- **Object** — object to processing based on legitimate interest
- **Complain** — lodge a complaint with the UK Information Commissioner's Office (ICO) at ico.org.uk

To exercise any of these rights, contact runcoach@linehan.me.uk (central service) or your instance administrator (self-hosted).

### 8. International Transfers

OpenAI and Anthropic process data on servers in the United States. Where required, transfers rely on Standard Contractual Clauses (SCCs) under UK/EU GDPR. Self-hosters using Ollama keep all data on their own infrastructure.

## Tests

- E2E test: `GET /privacy` returns 200 and contains expected heading text
- E2E test: privacy link present in page footer on the main index page

## Out of Scope

- Cookie consent banner (RunCoach uses no tracking cookies)
- Separate self-hoster policy template document
- In-app WebView for the policy (external browser is sufficient)
