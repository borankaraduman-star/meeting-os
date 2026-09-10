#!/bin/sh
# One-click updater: pull the v0.1 branch, rebuild with the pinned signing identity, relaunch.
# Launched detached by the app (which then quits). Never force-pulls over local changes.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$HOME/Library/Application Support/MeetingOS"
LOG="$DATA/update.log"; STATUS="$DATA/update-status.json"
MARKER="$DATA/signing-partition.ok"      # scripts/fix-signing-prompts.sh writes it after the one-time grant
LOCK="$DATA/update.lock.d"               # mkdir is the atomic primitive every sh has
LOCK_STALE_MINUTES=30                    # a build takes ~20 min; older than this and the holder is gone
INSTALLED="$REPO/build/installed-commit" # the commit the installed app was actually built from
LOG_MAX_BYTES=1048576
SIGNING_FIX="İmzalama anahtarı için bir kez: sh '$REPO/scripts/fix-signing-prompts.sh' (Terminal'de, Mac parolası)"
cd "$REPO" || exit 1
mkdir -p "$DATA"
# Atomic: a half-written status file is read by the app as "no update ever ran", and the app polls this
# while the updater is mid-write.
status() {
  message="$(printf '%s' "$3" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\n')"
  tmp="$STATUS.tmp.$$"
  printf '{"state":"%s","from":"%s","to":"%s","message":"%s","time":"%s"}\n' \
    "$1" "$FROM" "$2" "$message" "$(date '+%Y-%m-%d %H:%M:%S')" > "$tmp" && mv -f "$tmp" "$STATUS" || rm -f "$tmp"
}
FROM="$(git rev-parse --short HEAD 2>/dev/null)"
# The log is append-only across every update this Mac ever runs; without rotation it is the largest file in
# the data folder after a year.
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" 2>/dev/null || echo 0)" -gt "$LOG_MAX_BYTES" ]; then mv -f "$LOG" "$LOG.1"; fi
exec >> "$LOG" 2>&1
TMP="$(mktemp -d "${TMPDIR:-/tmp}/meeting-os-update.XXXXXX")" || exit 1
LOCK_HELD=''
# Whatever happens, the app comes back — and the build that was just installed is the one that opens.
# `open -a` goes through LaunchServices, which happily resolves "Meeting OS" to a stale copy in ~/Applications
# or the Trash; the bundle path is the only unambiguous answer, so it is tried first.
trap 'code=$?; [ -n "$LOCK_HELD" ] && rmdir "$LOCK" 2>/dev/null; rm -rf "$TMP" 2>/dev/null;
      open "$REPO/build/Meeting OS.app" 2>/dev/null || open -a "Meeting OS" 2>/dev/null; exit $code' EXIT
echo "== $(date '+%F %T') güncelleme başladı ($FROM)"
# Two updaters at once means two builds writing the same app bundle. The app can launch a second one (the card
# and the automatic check are separate paths) and a teammate can start one by hand while another runs.
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -d "$LOCK" ] && [ -z "$(find "$LOCK" -maxdepth 0 -mmin "-$LOCK_STALE_MINUTES" 2>/dev/null)" ]; then
    echo "eski kilit temizlendi ($LOCK)"; rm -rf "$LOCK"
  fi
  if ! mkdir "$LOCK" 2>/dev/null; then status failed "$FROM" "Güncelleme zaten sürüyor"; exit 1; fi
fi
LOCK_HELD=1
# A recording is the one thing that must never be interrupted: the build replaces the capture helper and the
# app bundle underneath a meeting that is being taped right now.
report_roots() {
  printf '%s\n' "$DATA"
  printf '%s\n' "$HOME/Library/Mobile Documents/com~apple~CloudDocs/MeetingOS-Reports"
  [ -f "$DATA/settings.json" ] && sed -n 's/.*"\(report_dir\|team_dir\)"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\2/p' "$DATA/settings.json"
  return 0
}
recording_live() {   # recording-heartbeat.json is rewritten once a minute while the recorder drains
  report_roots | while IFS= read -r root; do
    [ -n "$root" ] && [ -d "$root" ] || continue
    [ -n "$(find "$root" -maxdepth 3 -name recording-heartbeat.json -mmin -3 2>/dev/null | head -n 1)" ] && { echo live; break; }
  done
}
if pgrep -x MeetingCapture >/dev/null 2>&1 || [ -n "$(recording_live)" ]; then
  status failed "$FROM" "Kayıt sürüyor; güncelleme yapılmadı"; exit 1
fi
status running "$FROM" "Uygulamanın kapanması bekleniyor"
i=0; while pgrep -x MeetingOS >/dev/null && [ $i -lt 60 ]; do sleep 1; i=$((i+1)); done
if pgrep -x MeetingOS >/dev/null; then status failed "$FROM" "Uygulama kapanmadı; güncelleme iptal"; exit 1; fi
if [ -n "$(git status --porcelain)" ]; then status failed "$FROM" "Yerel değişiklikler var; güncelleme yapılmadı"; exit 1; fi
# GIT_TERMINAL_PROMPT/GIT_ASKPASS: a repo that lost its credentials must fail, never sit on an invisible
# username prompt. The watchdog covers the other half: a TCP connection that hangs instead of refusing.
GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/true git fetch --tags --force origin v0.1 &
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
# The HIGHEST tag reachable from the branch, not the nearest ancestor: `describe` walks backwards from the tip and
# stops at the first tag it meets, which on a branch carrying several tags can be an OLDER release than one already
# installed — that is a silent downgrade. `sort -V` orders them by version instead of by graph distance.
TARGET="origin/v0.1"
if [ -z "${MEETING_OS_UPDATE_UNTAGGED:-}" ]; then
  TARGET="$(git tag --merged origin/v0.1 'v*' 2>/dev/null | sort -V | tail -n 1)"
  if [ -z "$TARGET" ]; then status failed "$FROM" "GitHub'da yayınlanmış sürüm etiketi bulunamadı; güncelleme bekletildi"; exit 1; fi
fi
# Everything that can refuse the update is asked BEFORE the working tree moves. A Mac that fails the signing gate
# after `git merge` sits at the new commit with the old app installed, and the in-app check then reports "güncel"
# (behind=0) and hides the button — the update is invisibly stuck until someone reads update.log.
if [ ! -f "$MARKER" ]; then status failed "$FROM" "$SIGNING_FIX"; exit 1; fi
if ! git merge-base --is-ancestor HEAD "$TARGET" 2>"$TMP/ff.err"; then
  cat "$TMP/ff.err"
  status failed "$FROM" "Dal ileri sarılamadı: $(head -n 1 "$TMP/ff.err" | tr -d '\r' || true) · yerel dal ayrışmış · Boran'a update.log gönderin"; exit 1
fi
# The commit the app in build/ was actually built from. After a failure between the merge and a finished build,
# HEAD is already the new commit while the app is the old one; comparing against HEAD-at-start would then skip pip
# and the capture helper on every retry, and the retry would install a new app against old dependencies.
BASE="$(cat "$INSTALLED" 2>/dev/null | tr -d ' \n' || true)"
[ -n "$BASE" ] && git cat-file -e "$BASE^{commit}" 2>/dev/null || BASE="$FROM"
if ! git merge --ff-only "$TARGET" 2>"$TMP/merge.err"; then
  cat "$TMP/merge.err"
  status failed "$FROM" "Dal ileri sarılamadı: $(head -n 1 "$TMP/merge.err" | tr -d '\r' || true) · Boran'a update.log gönderin"; exit 1
fi
TO="$(git rev-parse --short HEAD)"
# Belt and braces: the gate above already refused, but nothing may reach codesign without the grant. The update
# runs detached, with the app quit: a codesign password dialog here has no one to answer it and the build hangs
# or fails halfway.
if [ ! -f "$MARKER" ]; then status failed "$TO" "$SIGNING_FIX"; exit 1; fi
status running "$TO" "Bağımlılıklar kontrol ediliyor"
if [ "$BASE" != "$TO" ] && ! git diff --quiet "$BASE" "$TO" -- requirements-macos-tested.txt pyproject.toml; then
  nice -n 19 .venv/bin/python -m pip install -r requirements-macos-tested.txt && nice -n 19 .venv/bin/python -m pip install -e '.[mlx,speakers,analysis]' || { status failed "$TO" "Python bağımlılıkları kurulamadı"; exit 1; }
fi
if [ "$BASE" != "$TO" ] && ! git diff --quiet "$BASE" "$TO" -- capture; then
  nice -n 19 /bin/sh scripts/build-capture.sh || { status failed "$TO" "Kayıt yardımcısı derlenemedi"; exit 1; }
fi
status running "$TO" "Uygulama derleniyor ve imzalanıyor"
# This run's build output, in its own file: the errSecAuth classification used to read the tail of update.log,
# which carries every earlier run — one old signing failure made every later compiler error look like a
# keychain problem.
if nice -n 19 /bin/sh scripts/build-desktop.sh > "$TMP/build.log" 2>&1; then
  cat "$TMP/build.log"
  mkdir -p "$(dirname "$INSTALLED")" && printf '%s\n' "$TO" > "$INSTALLED.tmp.$$" && mv -f "$INSTALLED.tmp.$$" "$INSTALLED"
  status done "$TO" "Güncellendi: $BASE → $TO"
else
  cat "$TMP/build.log"
  if grep -qE 'errSecAuth|User interaction is not allowed|errSecInternalComponent' "$TMP/build.log"; then
    status failed "$TO" "$SIGNING_FIX"
  else
    status failed "$TO" "Derleme başarısız; kurulu sürüm değişmedi (build/Meeting OS.app) · ayrıntı update.log"
  fi
fi
echo "== $(date '+%F %T') bitti ($TO)"
