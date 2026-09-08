#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
swift build --package-path desktop -c release
app="$PWD/build/Meeting OS.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp desktop/.build/release/MeetingOS "$app/Contents/MacOS/MeetingOS"
.venv/bin/python - "$app/Contents/Resources/runtime.json" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({'python':str(Path(sys.executable).absolute()),'repo':str(Path.cwd().resolve())}))
PY
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.boran.meeting-os</string>
<key>CFBundleName</key><string>Meeting OS</string>
<key>CFBundleExecutable</key><string>MeetingOS</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0.2</string>
<key>LSMinimumSystemVersion</key><string>15.0</string>
<key>NSMicrophoneUsageDescription</key><string>Meeting OS toplantı mikrofonunu yalnızca bu Mac üzerinde kaydeder ve yazıya dönüştürür.</string>
<key>NSScreenCaptureUsageDescription</key><string>Meeting OS toplantı sistem sesini yerel olarak kaydeder. Ekran görüntüsü saklanmaz.</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
xattr -cr "$app"
codesign --force --deep --sign - "$app"
printf '%s\n' "$app"
