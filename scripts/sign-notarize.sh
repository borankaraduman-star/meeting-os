#!/bin/sh
# Developer ID signing + Apple notarization for the self-contained bundle (docs/BUNDLE.md).
#
#     sh scripts/sign-notarize.sh [build/bundle/Meeting OS.app]
#
# Needs, once, on this Mac: a "Developer ID Application: …" certificate in the login keychain and a notarytool
# keychain profile (default name `meetingos`, made with `xcrun notarytool store-credentials meetingos …`).
# Override with MEETING_OS_DEVID="Developer ID Application: Name (TEAMID)" and MEETING_OS_NOTARY_PROFILE=name.
#
# Why every file: notarization rejects a bundle with any unsigned Mach-O inside, and the Python runtime carries
# hundreds (torch, numpy, ffmpeg). Order matters — innermost first, the app last — and the hardened runtime needs
# entitlements that Python's JIT-ing libraries (llvmlite/numba) and dlopen of our own .so files require.
set -eu
APP=${1:-"$(cd "$(dirname "$0")/.." && pwd)/build/bundle/Meeting OS.app"}
[ -d "$APP" ] || { echo "paket yok: $APP (önce sh scripts/build-bundle.sh)" >&2; exit 1; }
PROFILE=${MEETING_OS_NOTARY_PROFILE:-meetingos}
ID=${MEETING_OS_DEVID:-}
if [ -z "$ID" ]; then
  ID=$(/usr/bin/security find-identity -v -p codesigning 2>/dev/null | sed -n 's/.*"\(Developer ID Application: [^"]*\)".*/\1/p' | head -1)
fi
[ -n "$ID" ] || { echo "Developer ID Application sertifikası yok. developer.apple.com → Certificates → Developer ID Application; .cer dosyasını çift tıklayın." >&2; exit 2; }
echo "==> imza: $ID"
TMP=$(mktemp -d -t meetingos-sign)
DIST_STAGE=
trap 'rm -rf "$TMP"; [ -z "$DIST_STAGE" ] || rm -rf "$DIST_STAGE"' EXIT
# Entitlements: the app and the embedded Python interpreter load our own dylibs/.so files (library validation
# off), numba/llvmlite JIT (allow-jit + unsigned executable memory), microphone and calendar/reminders access.
cat > "$TMP/app.entitlements" <<'PL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>com.apple.security.cs.disable-library-validation</key><true/>
<key>com.apple.security.cs.allow-jit</key><true/>
<key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>
<key>com.apple.security.cs.allow-dyld-environment-variables</key><true/>
<key>com.apple.security.device.audio-input</key><true/>
<key>com.apple.security.personal-information.calendars</key><true/>
<key>com.apple.security.automation.apple-events</key><true/>
</dict></plist>
PL
cat > "$TMP/helper.entitlements" <<'PL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>com.apple.security.device.audio-input</key><true/>
</dict></plist>
PL
sign() { /usr/bin/codesign --force --timestamp --options runtime --sign "$ID" "$@"; }
# 1. Every Mach-O inside Resources (dylibs, .so, the interpreter, ffmpeg), innermost first. Non-Mach-O executables
#    (shell scripts in bin/) are left alone: codesign has nothing to sign there.
echo "==> Mach-O dosyaları imzalanıyor"
find "$APP/Contents/Resources" -type f \( -name "*.so" -o -name "*.dylib" -o -perm -u+x \) ! -path "*/MeetingCapture.app/*" -print0 > "$TMP/mach-o-files"
while IFS= read -r -d '' f; do
  FILE_TYPE=$(/usr/bin/file -b "$f")
  case "$FILE_TYPE" in
    Mach-O*) sign --entitlements "$TMP/app.entitlements" "$f";;
  esac
done < "$TMP/mach-o-files"
# 2. The capture helper is a nested app: its own executable, then the bundle.
HELPER="$APP/Contents/Resources/repo/build/MeetingCapture.app"
if [ -d "$HELPER" ]; then
  echo "==> kayıt yardımcısı"
  sign --entitlements "$TMP/helper.entitlements" "$HELPER"
fi
# 3. The app itself, last.
echo "==> uygulama"
sign --entitlements "$TMP/app.entitlements" "$APP"
/usr/bin/codesign --verify --deep --strict --verbose=1 "$APP"
# 4. Notarize a zip of the app, then staple the ticket onto the app and re-zip for distribution.
VERSION=$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP/Contents/Info.plist")
OUT="$(dirname "$APP")/../Meeting-OS-$VERSION.zip"; OUT=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")
echo "==> notarize gönderimi ($PROFILE)"
/usr/bin/ditto -c -k --keepParent "$APP" "$TMP/submit.zip"
if ! xcrun notarytool submit "$TMP/submit.zip" --keychain-profile "$PROFILE" --wait --output-format json > "$TMP/notary-result.json"; then
  cat "$TMP/notary-result.json" >&2
  echo "Noterleme gönderimi başarısız; dağıtım paketi değiştirilmedi." >&2
  exit 1
fi
STATUS=$(/usr/bin/plutil -extract status raw -o - "$TMP/notary-result.json")
if [ "$STATUS" != Accepted ]; then
  echo "Noterleme kabul edilmedi: $STATUS; dağıtım paketi değiştirilmedi." >&2
  exit 1
fi
echo "==> damga yapıştırılıyor"
xcrun stapler staple "$APP"
/usr/sbin/spctl --assess --type execute --verbose=1 "$APP"
# Build beside the destination so publication is a rename, and a failed archive
# or checksum cannot truncate an existing release.
DIST_STAGE=$(mktemp -d "$(dirname "$OUT")/.meetingos-release.XXXXXX")
/usr/bin/ditto -c -k --keepParent "$APP" "$DIST_STAGE/release.zip"
SHA256=$(shasum -a 256 "$DIST_STAGE/release.zip")
printf '%s\n' "${SHA256%% *}" > "$DIST_STAGE/release.zip.sha256"
mv -f "$DIST_STAGE/release.zip" "$OUT"
mv -f "$DIST_STAGE/release.zip.sha256" "$OUT.sha256"
echo "==> hazır: $OUT ($(du -h "$OUT" | cut -f1)); sonra: sh scripts/publish-github.sh $OUT"
