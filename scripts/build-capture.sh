#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
swift build --package-path capture -c release
app="$PWD/build/MeetingCapture.app"
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
codesign --force --deep --sign - "$app"
printf '%s\n' "$app/Contents/MacOS/MeetingCapture"
