Deploy everything in parallel:

1. **CI watch → Docker deploy**: Get the latest CI run ID on `main` with `gh run list --branch main --limit 1 --json databaseId,status -q '.[0]'`. If it's already completed successfully, skip straight to docker deploy. Otherwise watch it with `gh run watch <id> --exit-status`. On success: `cd /srv/runcoach && docker compose pull && docker compose up -d`.

2. **Flutter build → phone install** (run in parallel with step 1):
   - Discover ADB port via mDNS: `DEVICE=$(adb mdns services 2>/dev/null | grep '_adb-tls-connect' | grep '192.168.1.138' | awk '{print $3}')`. If empty, fall back to `adb mdns services` output and report what was found so the user can intervene.
   - Connect ADB: `adb connect "$DEVICE"`
   - Build: `cd /home/colm/git/fitparser/mobile && flutter build apk --release`
   - Install: `adb -s "$DEVICE" install -r build/app/outputs/flutter-apk/app-release.apk`

Run both as background tasks. Report back when each finishes. If CI fails, do not deploy Docker and report the failure.
