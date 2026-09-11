#!/bin/sh
# Daily backup of the Meeting OS team sync state. Quiet on success.
# Installed at /opt/meetingos-sync/backup.sh, run from cron at 03:17.
set -eu

SRC=${SRC:-/var/lib/meetingos-sync}
DEST=${DEST:-/var/backups/meetingos-sync}
KEEP=${KEEP:-14}

[ -d "$SRC" ] || { echo "backup: missing $SRC" >&2; exit 1; }

mkdir -p "$DEST"
chmod 700 "$DEST"

STAMP=$(date -u +%Y%m%d)
OUT="$DEST/sync-$STAMP.tar.gz"
TMP="$OUT.part"

# _downloads holds published app bundles (≈1,3 GB each) that already exist on Boran's Mac and can be
# republished at any time; 14 daily copies of them would be the largest thing on this VPS by far.
tar -czf "$TMP" --exclude "$(basename "$SRC")/_downloads" \
    -C "$(dirname "$SRC")" "$(basename "$SRC")"
chmod 600 "$TMP"
mv -f "$TMP" "$OUT"

# keep the newest $KEEP archives, drop the rest
ls -1t "$DEST"/sync-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f "$old"
done

exit 0
