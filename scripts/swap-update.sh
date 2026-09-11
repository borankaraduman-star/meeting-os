#!/bin/sh
# Put a freshly downloaded Meeting OS.app in place of the running one and reopen it.
#
#     sh swap-update.sh <yeni.app> <hedef.app> <pid>
#
# Launched detached by meeting_os/updater.py after the zip is verified and unpacked; the app quits while this
# waits. Everything here is a `mv` inside one folder — no sudo, ever: if the target's folder is not writable
# the swap is refused and the old app stays exactly where it is. The target is the path the app is RUNNING
# from (Swift sends it), so an app opened from ~/Downloads updates in ~/Downloads, not in /Applications.
set -u

NEW=${1:-}
TARGET=${2:-}
PID=${3:-0}
DATA="$HOME/Library/Application Support/MeetingOS"
LOG="$DATA/update.log"
STATUS="$DATA/update-status.json"
PREV="$TARGET.previous"
LOG_MAX_BYTES=1048576
VERSION=""

mkdir -p "$DATA"
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" 2>/dev/null || echo 0)" -gt "$LOG_MAX_BYTES" ]; then mv -f "$LOG" "$LOG.1"; fi
exec >> "$LOG" 2>&1

# Same file, same keys as scripts/update.sh: the app reads one contract whichever channel updated it.
status() {
  message="$(printf '%s' "$2" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\000-\037')"
  tmp="$STATUS.tmp.$$"
  printf '{"state":"%s","from":"","to":"%s","message":"%s","time":"%s"}\n' \
    "$1" "$VERSION" "$message" "$(date '+%Y-%m-%d %H:%M:%S')" > "$tmp" && mv -f "$tmp" "$STATUS" || rm -f "$tmp"
}

echo "== $(date '+%F %T') takas başladı ($NEW → $TARGET, pid $PID)"
if [ -z "$NEW" ] || [ -z "$TARGET" ]; then
  echo "swap: eksik argüman"; status failed "Güncelleme takası yapılamadı (eksik argüman)"; exit 2
fi
if [ ! -d "$NEW" ]; then
  echo "swap: $NEW yok"; status failed "İndirilen paket bulunamadı"; exit 1
fi
VERSION="$(/usr/bin/defaults read "$NEW/Contents/Info" CFBundleShortVersionString 2>/dev/null || true)"

PARENT="$(dirname "$TARGET")"
if [ ! -w "$PARENT" ]; then
  echo "swap: $PARENT yazılabilir değil"
  status failed "Uygulama klasörü yazılabilir değil ($PARENT) · uygulamayı Uygulamalar'a taşıyın"
  rm -rf "$NEW"; exit 1
fi

# The app is quitting while we wait. 60 s is the same budget scripts/update.sh uses; past it the swap is
# abandoned rather than done underneath a running app.
i=0
while [ "$PID" -gt 0 ] && kill -0 "$PID" 2>/dev/null && [ "$i" -lt 60 ]; do sleep 1; i=$((i + 1)); done
if [ "$PID" -gt 0 ] && kill -0 "$PID" 2>/dev/null; then
  echo "swap: pid $PID hâlâ açık; takas yapılmadı"
  status failed "Uygulama kapanmadı; güncelleme kurulmadı · uygulamayı kapatıp tekrar deneyin"
  exit 1
fi
sleep 1   # the process is gone; give the filesystem a breath before moving the bundle it ran from

# One .previous at a time: the last known-good copy, replaced by this run's.
rm -rf "$PREV" 2>/dev/null
if [ -e "$TARGET" ] && ! mv "$TARGET" "$PREV"; then
  echo "swap: eski sürüm yana alınamadı"; status failed "Eski sürüm yana alınamadı; güncelleme kurulmadı"; exit 1
fi
if ! mv "$NEW" "$TARGET"; then
  echo "swap: yeni sürüm yerine konamadı; eski sürüm geri alınıyor"
  [ -e "$PREV" ] && mv "$PREV" "$TARGET"
  status failed "Yeni sürüm yerine konamadı; eski sürüm geri alındı"
  open "$TARGET" 2>/dev/null || true
  exit 1
fi
# The bundle was never in a browser's hands (the app downloaded it itself), but a quarantine flag inherited
# from anywhere would make the reopened app ask again.
/usr/bin/xattr -d -r com.apple.quarantine "$TARGET" 2>/dev/null || true
rmdir "$(dirname "$NEW")" 2>/dev/null || true   # the staging folder in ~/Library/Caches is empty now

if [ -n "$VERSION" ]; then status done "Güncellendi: $VERSION"; else status done "Güncellendi"; fi
echo "== $(date '+%F %T') takas tamam ($TARGET${VERSION:+ · $VERSION})"
open "$TARGET" || open -a "Meeting OS" 2>/dev/null || true
# The previous version stays on disk until the next update needs the space: it is the only way back if the
# new one does not start at all.
exit 0
