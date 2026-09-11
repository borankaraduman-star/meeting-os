#!/bin/sh
# Publish a bundle zip as a GitHub Release asset (the download channel teammates and the in-app updater use).
#
#     sh scripts/publish-github.sh build/Meeting-OS-1.2.74.zip
#
# Why GitHub and not the VPS: 11 Sep 2026, the Tailscale Funnel route moved 4.5 MB/s on the tailnet and far less
# through the DERP relays a teammate without Tailscale goes through; GitHub's CDN moved the same zip at 21 MB/s.
# The zip must carry NO secret (no invite.json, no download.secret): the repo is public. The team and the key
# reach a teammate through their personal `meetingos://join?…&key=…` link instead.
#
# Uploads, in order: <zip>, <zip>.sha256, latest.json (last, so `releases/latest/download/latest.json` never
# names a file that is not there yet). Needs `gh auth status` to be green and the tag v<version> to exist.
set -eu
ZIP=${1:?kullanım: publish-github.sh build/Meeting-OS-<sürüm>.zip}
[ -f "$ZIP" ] || { echo "yok: $ZIP" >&2; exit 1; }
REPO=$(cd "$(dirname "$0")/.." && pwd)
NAME=$(basename "$ZIP")
VERSION=$(printf '%s' "$NAME" | sed -n 's/^Meeting-OS-\([0-9][0-9.]*\)\.zip$/\1/p')
[ -n "$VERSION" ] || { echo "zip adı Meeting-OS-<sürüm>.zip olmalı: $NAME" >&2; exit 1; }
for f in "$REPO/build/bundle/Meeting OS.app/Contents/Resources/invite.json" "$REPO/build/bundle/Meeting OS.app/Contents/Resources/download.secret"; do
  if unzip -l "$ZIP" 2>/dev/null | grep -q "Resources/$(basename "$f")\$"; then echo "zip gizli dosya taşıyor ($(basename "$f")); GitHub'a çıkmaz" >&2; exit 1; fi
done
SHA=$(shasum -a 256 "$ZIP" | awk '{print $1}')
printf '%s\n' "$SHA" > "$ZIP.sha256"
NOTES="$REPO/docs/releases/v$VERSION.md"
TITLE=$(sed -n '1s/^# *//p' "$NOTES" 2>/dev/null)
LATEST="$REPO/build/latest.json"
"$REPO/.venv/bin/python" - "$LATEST" "$NAME" "$SHA" "$ZIP" "$VERSION" "${TITLE:-Meeting OS $VERSION}" <<'PY'
import json, sys, datetime, os
out, name, sha, zip_path, version, title = sys.argv[1:7]
json.dump({'version': version, 'file': name, 'sha256': sha, 'size': os.path.getsize(zip_path),
           'published': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'notes': title},
          open(out, 'w'), ensure_ascii=False)
PY
if gh release view "v$VERSION" >/dev/null 2>&1; then
  gh release upload "v$VERSION" "$ZIP" "$ZIP.sha256" "$LATEST" --clobber
else
  if [ -f "$NOTES" ]; then gh release create "v$VERSION" "$ZIP" "$ZIP.sha256" "$LATEST" --title "Meeting OS $VERSION" --notes-file "$NOTES"
  else gh release create "v$VERSION" "$ZIP" "$ZIP.sha256" "$LATEST" --title "Meeting OS $VERSION" --notes "Meeting OS $VERSION"; fi
fi
echo "==> yayında: https://github.com/borankaraduman-star/meeting-os/releases/download/v$VERSION/$NAME"
echo "    güncelleyici: https://github.com/borankaraduman-star/meeting-os/releases/latest/download/latest.json"
