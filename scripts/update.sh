#!/bin/sh
# One-click updater: pull the v0.1 branch, rebuild with the pinned signing identity, relaunch.
# Launched detached by the app (which then quits). Never force-pulls over local changes.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$HOME/Library/Application Support/MeetingOS"
LOG="$DATA/update.log"; STATUS="$DATA/update-status.json"
MARKER="$DATA/signing-partition.ok"      # scripts/fix-signing-prompts.sh writes it after the one-time grant
SIGNING_FIX="İmzalama anahtarı için bir kez: sh scripts/fix-signing-prompts.sh (Terminal'de, Mac parolası)"
cd "$REPO" || exit 1
mkdir -p "$DATA"
status() { printf '{"state":"%s","from":"%s","to":"%s","message":"%s","time":"%s"}\n' "$1" "$FROM" "$2" "$3" "$(date '+%Y-%m-%d %H:%M:%S')" > "$STATUS"; }
FROM="$(git rev-parse --short HEAD 2>/dev/null)"
exec >> "$LOG" 2>&1
trap 'open -a "Meeting OS" 2>/dev/null || open "$REPO/build/Meeting OS.app"' EXIT   # whatever happens, the app comes back
echo "== $(date '+%F %T') güncelleme başladı ($FROM)"
status running "$FROM" "Uygulamanın kapanması bekleniyor"
i=0; while pgrep -x MeetingOS >/dev/null && [ $i -lt 60 ]; do sleep 1; i=$((i+1)); done
if pgrep -x MeetingOS >/dev/null; then status failed "$FROM" "Uygulama kapanmadı; güncelleme iptal"; exit 1; fi
if [ -n "$(git status --porcelain)" ]; then status failed "$FROM" "Yerel değişiklikler var; güncelleme yapılmadı"; exit 1; fi
# GIT_TERMINAL_PROMPT/GIT_ASKPASS: a repo that lost its credentials must fail, never sit on an invisible
# username prompt. The watchdog covers the other half: a TCP connection that hangs instead of refusing.
GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/true git fetch --tags origin v0.1 &
fetch_pid=$!
i=0; while kill -0 "$fetch_pid" 2>/dev/null && [ $i -lt 120 ]; do sleep 1; i=$((i+1)); done
if kill -0 "$fetch_pid" 2>/dev/null; then
  kill "$fetch_pid" 2>/dev/null; sleep 2; kill -9 "$fetch_pid" 2>/dev/null
  wait "$fetch_pid" 2>/dev/null || true
  rm -f .git/FETCH_HEAD.lock                                   # a killed fetch can leave the lock behind
  status failed "$FROM" "GitHub'a ulaşılamadı (zaman aşımı)"; exit 1
fi
if ! wait "$fetch_pid"; then status failed "$FROM" "GitHub'a ulaşılamadı"; exit 1; fi
# Only released states are installed: the tip of origin/v0.1 must carry a release tag (vX.Y.Z). A half-finished
# push or a stray commit never lands on a teammate's Mac. Set MEETING_OS_UPDATE_UNTAGGED=1 to override on a dev Mac.
TARGET="origin/v0.1"
if [ -z "${MEETING_OS_UPDATE_UNTAGGED:-}" ]; then
  TARGET="$(git describe --tags --abbrev=0 --match 'v*' origin/v0.1 2>/dev/null || true)"
  if [ -z "$TARGET" ]; then status failed "$FROM" "GitHub'da yayınlanmış sürüm etiketi bulunamadı; güncelleme bekletildi"; exit 1; fi
fi
if ! git merge --ff-only "$TARGET"; then status failed "$FROM" "Dal ileri sarılamadı"; exit 1; fi
TO="$(git rev-parse --short HEAD)"
# The update runs detached, with the app quit: a codesign password dialog here has no one to answer it and the
# build hangs or fails halfway. Without the partition list every signing asks, so the grant is a precondition,
# checked before the first build rather than after twenty minutes of pip and Swift.
if [ ! -f "$MARKER" ]; then status failed "$TO" "$SIGNING_FIX"; exit 1; fi
status running "$TO" "Bağımlılıklar kontrol ediliyor"
if [ "$FROM" != "$TO" ] && ! git diff --quiet "$FROM" "$TO" -- requirements-macos-tested.txt pyproject.toml; then
  nice -n 19 .venv/bin/python -m pip install -r requirements-macos-tested.txt && nice -n 19 .venv/bin/python -m pip install -e '.[mlx,speakers,analysis]' || { status failed "$TO" "Python bağımlılıkları kurulamadı"; exit 1; }
fi
if [ "$FROM" != "$TO" ] && ! git diff --quiet "$FROM" "$TO" -- capture; then
  nice -n 19 /bin/sh scripts/build-capture.sh || { status failed "$TO" "Kayıt yardımcısı derlenemedi"; exit 1; }
fi
status running "$TO" "Uygulama derleniyor ve imzalanıyor"
if nice -n 19 /bin/sh scripts/build-desktop.sh; then
  status done "$TO" "Güncellendi: $FROM → $TO"
elif tail -n 200 "$LOG" | grep -qE 'errSecAuth|User interaction is not allowed|errSecInternalComponent'; then
  status failed "$TO" "$SIGNING_FIX"
else
  status failed "$TO" "Derleme başarısız; önceki sürüm build/app-backups içinde"
fi
echo "== $(date '+%F %T') bitti ($TO)"
