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
trap 'rm -rf "$TMP"' EXIT
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
count=0
find "$APP/Contents/Resources" -type f \( -name "*.so" -o -name "*.dylib" -o -perm -u+x \) ! -path "*/MeetingCapture.app/*" -print0 |
while IFS= read -r -d '' f; do
  case "$(/usr/bin/file -b "$f" 2>/dev/null)" in
    Mach-O*) sign --entitlements "$TMP/app.entitlements" "$f" 2>/dev/null || sign "$f";;
  esac
done
# 2. The capture helper is a nested app: its own executable, then the bundle.
HELPER="$APP/Contents/Resources/repo/build/MeetingCapture.app"
if [ -d "$HELPER" ]; then
  echo "==> kayıt yardımcısı"
  sign --entitlements "$TMP/helper.entitlements" "$HELPER"
fi
# 3. The app itself, last.
echo "==> uygulama"
sign --entitlements "$TMP/app.entitlements" "$APP"
/usr/bin/codesign --verify --deep --strict --verbose=1 "$APP" 2>&1 | tail -2
# 4. Notarize a zip of the app, then staple the ticket onto the app and re-zip for distribution.
VERSION=$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP/Contents/Info.plist")
OUT="$(dirname "$APP")/../Meeting-OS-$VERSION.zip"; OUT=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")
echo "==> notarize gönderimi ($PROFILE)"
/usr/bin/ditto -c -k --keepParent "$APP" "$TMP/submit.zip"
xcrun notarytool submit "$TMP/submit.zip" --keychain-profile "$PROFILE" --wait 2>&1 | tail -4
echo "==> damga yapıştırılıyor"
xcrun stapler staple "$APP" 2>&1 | tail -1
/usr/sbin/spctl --assess --type execute --verbose=1 "$APP" 2>&1 | tail -1
rm -f "$OUT"
/usr/bin/ditto -c -k --keepParent "$APP" "$OUT"
shasum -a 256 "$OUT" | awk '{print $1}' > "$OUT.sha256"
echo "==> hazır: $OUT ($(du -h "$OUT" | cut -f1)); sonra: sh scripts/publish-github.sh $OUT"
