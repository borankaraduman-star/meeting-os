#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
.venv/bin/python scripts/signing.py --resolve >/dev/null
swift build --package-path desktop -c release --jobs 1
stage=$(mktemp -d "$PWD/build/desktop-stage.XXXXXX")
app="$stage/Meeting OS.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp desktop/.build/release/MeetingOS "$app/Contents/MacOS/MeetingOS"
cp desktop/Icon/AppIcon.icns "$app/Contents/Resources/AppIcon.icns"
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
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.2.31</string>
<key>LSMinimumSystemVersion</key><string>15.0</string>
<key>NSMicrophoneUsageDescription</key><string>Meeting OS toplantı mikrofonunu yalnızca bu Mac üzerinde kaydeder ve yazıya dönüştürür.</string>
<key>NSScreenCaptureUsageDescription</key><string>Meeting OS toplantı sistem sesini yerel olarak kaydeder. Ekran görüntüsü saklanmaz.</string>
<key>NSCalendarsFullAccessUsageDescription</key><string>Meeting OS kayıt başlarken o andaki takvim etkinliğinin adını ve katılımcılarını okur; takvime hiçbir şey yazmaz.</string>
<key>NSCalendarsUsageDescription</key><string>Meeting OS kayıt başlarken o andaki takvim etkinliğinin adını ve katılımcılarını okur; takvime hiçbir şey yazmaz.</string>
<key>NSRemindersFullAccessUsageDescription</key><string>Meeting OS seçtiğiniz görevi Apple Hatırlatıcılar’a ekler; başka hiçbir şey okumaz veya değiştirmez.</string>
<key>NSRemindersUsageDescription</key><string>Meeting OS seçtiğiniz görevi Apple Hatırlatıcılar’a ekler; başka hiçbir şey okumaz veya değiştirmez.</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
xattr -cr "$app"
.venv/bin/python scripts/signing.py --sign "$app"
.venv/bin/python scripts/signing.py --publish "$app" --target "$PWD/build/Meeting OS.app"
rmdir "$stage"
printf '%s\n' "$PWD/build/Meeting OS.app"
