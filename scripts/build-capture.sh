#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
.venv/bin/python scripts/signing.py --resolve >/dev/null
swift build --package-path capture -c release --jobs 1
stage=$(mktemp -d "$PWD/build/capture-stage.XXXXXX")
# A failed signing (a cancelled keychain dialog, a revoked identity) used to leave the staged bundle behind;
# build/ then filled up with capture-stage.* copies. The trap keeps the script's own exit status.
cleanup() { rc=$?; rm -rf "$stage"; exit "$rc"; }
trap cleanup EXIT
app="$stage/MeetingCapture.app"
mkdir -p "$app/Contents/MacOS"
cp capture/.build/release/MeetingCapture "$app/Contents/MacOS/MeetingCapture"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.boran.meeting-os.capture</string>
<key>CFBundleName</key><string>MeetingCapture</string>
<key>CFBundleExecutable</key><string>MeetingCapture</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSMinimumSystemVersion</key><string>15.0</string>
<key>LSUIElement</key><true/>
<key>NSMicrophoneUsageDescription</key><string>Meeting OS records your microphone locally for meeting transcription.</string>
<key>NSScreenCaptureUsageDescription</key><string>Meeting OS captures meeting system audio locally. No screen frames are saved.</string>
</dict></plist>
PLIST
xattr -cr "$app"
.venv/bin/python scripts/signing.py --sign "$app"
.venv/bin/python scripts/signing.py --publish "$app" --target "$PWD/build/MeetingCapture.app"
rmdir "$stage"
printf '%s\n' "$PWD/build/MeetingCapture.app/Contents/MacOS/MeetingCapture"
