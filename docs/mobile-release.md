# Mobile release APK (CI)

The **Flutter Release APK** job in `.github/workflows/ci.yml` builds an
installable, release-signed Android APK on pushes to `main` **that change the
mobile app** (anything under `mobile/`, or the CI workflow itself), and on every
manual run (Actions → CI/CD → Run workflow). Server-only changes don't rebuild
the APK — the app talks to the server over the API, so it doesn't need to.

Each build is published in two places:

- **GitHub Release `mobile-latest`** — always the newest build, never expires.
  Permanent download link (handy to bookmark on your phone):
  `https://github.com/comicmuse/fitparser/releases/download/mobile-latest/runcoach.apk`
  The release is replaced on every build and isn't marked as the repo's
  "Latest" release.
- **Workflow artifact `runcoach-release-apk`** on the run, as
  `runcoach-<version>-<run>.apk` (kept for 90 days).

Details:

- Points at the production server (`ApiService.defaultBaseUrl`).
- **Versioning:** `version:` in `mobile/pubspec.yaml` is the master for the
  human-readable **versionName** — bump it by hand when a release is worth
  naming (e.g. `1.1.0` → `1.2.0`). The **versionCode** Android uses to decide
  whether an install is an update is set automatically by CI to the run
  number, so it always increases; the `+N` in the pubspec is ignored by CI
  builds.
- Pull requests don't run this job; they build the debug APK as a compile
  check, and only when they change the mobile app.
- To rebuild without a mobile change (e.g. to refresh the release), use
  *Run workflow*.

If the signing secrets aren't set, the job is skipped with a warning and
produces no artifact.

## Repository secrets

Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | The release keystore, base64-encoded (see below) |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password |
| `ANDROID_KEY_ALIAS` | Key alias inside the keystore |
| `ANDROID_KEY_PASSWORD` | Key password |
| `GOOGLE_SERVICES_JSON` | Contents of `mobile/android/app/google-services.json` from the Firebase console. Optional: without it the APK builds with a placeholder and push notifications won't work. |

## Which signing key?

Android only installs an update if it's signed with the **same key** as the
app already on the phone.

**Option A — new release key (recommended).** Generate one, keep a backup
somewhere safe (losing it means you can't ship updates to existing installs):

```bash
keytool -genkeypair -v -keystore runcoach-release.jks -alias runcoach \
  -keyalg RSA -keysize 2048 -validity 10000
base64 -w0 runcoach-release.jks   # paste output into ANDROID_KEYSTORE_BASE64
```

Uninstall the existing app once before installing the first CI build (you'll
need to log in again); later CI builds update in place.

**Option B — keep your current key.** If the app on your phone was built
locally with `flutter build apk --release` (before this change), it was signed
with your machine's debug key at `~/.android/debug.keystore`
(store password `android`, alias `androiddebugkey`, key password `android`).
Uploading that keystore lets CI builds install over the existing app without
uninstalling, but debug keys aren't meant for distribution.

**Coming from the old Expo (React Native) app.** Expo/EAS builds held their
own signing key (managed by EAS unless you uploaded one), and Expo can't build
this Flutter app. If the Expo app used a different Android package name than
`com.runcoach.mobile`, the Flutter app installs alongside it as a separate app —
no key matching needed; just uninstall the Expo app when you're done with it.
If it used the same package name, use Option A and uninstall the Expo app first
(or download its keystore with `eas credentials` and use that as the release key).

## Building a release APK locally

Create `mobile/android/key.properties` (git-ignored):

```properties
storeFile=/absolute/path/to/runcoach-release.jks
storePassword=...
keyAlias=runcoach
keyPassword=...
```

then run `flutter build apk --release` in `mobile/`. Without `key.properties`,
release builds fall back to the debug key.
