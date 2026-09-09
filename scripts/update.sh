#!/bin/sh
# One-click updater: pull the v0.1 branch, rebuild with the pinned signing identity, relaunch.
# Launched detached by the app (which then quits). Never force-pulls over local changes.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$HOME/Library/Application Support/MeetingOS"
LOG="$DATA/update.log"; STATUS="$DATA/update-status.json"
cd "$REPO" || exit 1
mkdir -p "$DATA"
status() { printf '{"state":"%s","from":"%s","to":"%s","message":"%s","time":"%s"}\n' "$1" "$FROM" "$2" "$3" "$(date '+%Y-%m-%d %H:%M:%S')" > "$STATUS"; }
FROM="$(git rev-parse --short HEAD 2>/dev/null)"
exec >> "$LOG" 2>&1
echo "== $(date '+%F %T') güncelleme başladı ($FROM)"
status running "$FROM" "Uygulamanın kapanması bekleniyor"
i=0; while pgrep -x MeetingOS >/dev/null && [ $i -lt 60 ]; do sleep 1; i=$((i+1)); done
if pgrep -x MeetingOS >/dev/null; then status failed "$FROM" "Uygulama kapanmadı; güncelleme iptal"; exit 1; fi
if [ -n "$(git status --porcelain)" ]; then status failed "$FROM" "Yerel değişiklikler var; güncelleme yapılmadı"; exit 1; fi
if ! git fetch origin v0.1; then status failed "$FROM" "GitHub'a ulaşılamadı"; open -a "Meeting OS" 2>/dev/null || open "$REPO/build/Meeting OS.app"; exit 1; fi
if ! git merge --ff-only origin/v0.1; then status failed "$FROM" "Dal ileri sarılamadı"; open "$REPO/build/Meeting OS.app"; exit 1; fi
TO="$(git rev-parse --short HEAD)"
status running "$TO" "Bağımlılıklar kontrol ediliyor"
if [ "$FROM" != "$TO" ] && ! git diff --quiet "$FROM" "$TO" -- requirements-macos-tested.txt pyproject.toml; then
  .venv/bin/python -m pip install -r requirements-macos-tested.txt && .venv/bin/python -m pip install -e '.[mlx,speakers,analysis]' || { status failed "$TO" "Python bağımlılıkları kurulamadı"; exit 1; }
fi
if [ "$FROM" != "$TO" ] && ! git diff --quiet "$FROM" "$TO" -- capture; then
  /bin/sh scripts/build-capture.sh || { status failed "$TO" "Kayıt yardımcısı derlenemedi"; exit 1; }
fi
status running "$TO" "Uygulama derleniyor ve imzalanıyor"
if /bin/sh scripts/build-desktop.sh; then
  status done "$TO" "Güncellendi: $FROM → $TO"
else
  status failed "$TO" "Derleme başarısız; önceki sürüm build/app-backups içinde"
fi
open "$REPO/build/Meeting OS.app"
echo "== $(date '+%F %T') bitti ($TO)"
