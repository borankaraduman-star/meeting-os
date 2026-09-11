#!/bin/sh
# Publish one built app bundle to the download channel (docs/BUNDLE.md).
#
#     sh scripts/publish-bundle.sh build/Meeting-OS-1.2.72.zip
#     TARGET=root@1.2.3.4 sh scripts/publish-bundle.sh build/Meeting-OS-1.2.72.zip
#
# Uploads the zip and its sha256 sidecar to <state>/_downloads on the VPS, verifies both byte counts over
# ssh, then writes latest.json — in that order, so latest.json never points at a file that is not there yet.
# Prints the two links to hand to the team. Idempotent: re-publishing the same version overwrites it.
#
# The zip itself is made on Boran's Mac (scripts/build-bundle.sh → signing.py → ditto -c -k); this script
# never builds, signs or deletes anything.
set -eu

ZIP=${1:-}
TARGET=${TARGET:-root@100.87.35.111}
REMOTE_DIR=${REMOTE_DIR:-/var/lib/meetingos-sync/_downloads}
SECRET_FILE=${SECRET_FILE:-/etc/meetingos-sync/download.secret}
BASE_URL=${BASE_URL:-https://hermes-vps.tail2d8c7e.ts.net/meetingos/dl}

[ -n "$ZIP" ] || { echo "kullanım: sh scripts/publish-bundle.sh build/Meeting-OS-<sürüm>.zip" >&2; exit 2; }
[ -f "$ZIP" ] || { echo "publish: $ZIP yok" >&2; exit 1; }

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/.." && pwd)
NAME=$(basename "$ZIP")

# Version comes from the file name, and the name is the contract: the updater downloads exactly what
# latest.json names.
VERSION=$(printf '%s' "$NAME" | sed -n 's/^Meeting-OS-\([0-9][0-9.]*\)\.zip$/\1/p')
[ -n "$VERSION" ] || { echo "publish: dosya adı Meeting-OS-<sürüm>.zip olmalı (verilen: $NAME)" >&2; exit 1; }

# sha256 sidecar: required next to the zip, computed here when it is missing so a hand-made zip still works.
SHA_FILE="$ZIP.sha256"
if [ -f "$SHA_FILE" ]; then
    SHA=$(awk '{print $1; exit}' "$SHA_FILE")
else
    echo "==> $SHA_FILE yok; hesaplanıyor"
    SHA=$(shasum -a 256 "$ZIP" | awk '{print $1}')
    printf '%s  %s\n' "$SHA" "$NAME" > "$SHA_FILE"
fi
printf '%s' "$SHA" | grep -Eq '^[0-9a-f]{64}$' || {
    echo "publish: $SHA_FILE içinde 64 haneli sha256 yok" >&2; exit 1; }

# The sidecar must describe THIS zip: a stale .sha256 next to a rebuilt zip is the one failure the app
# reports as "doğrulama başarısız" after a 1,3 GB download.
ACTUAL=$(shasum -a 256 "$ZIP" | awk '{print $1}')
[ "$ACTUAL" = "$SHA" ] || { echo "publish: $SHA_FILE zip ile uyuşmuyor ($SHA != $ACTUAL)" >&2; exit 1; }

SIZE=$(wc -c < "$ZIP" | tr -d ' ')

# notes = the release note's headline, without the leading "# ". Empty when the file is not written yet;
# the app shows the version alone in that case.
NOTES_FILE="$REPO/docs/releases/v$VERSION.md"
NOTES=""
if [ -f "$NOTES_FILE" ]; then
    NOTES=$(head -n 1 "$NOTES_FILE" | sed 's/^#* *//' | tr -d '\000-\037')
else
    echo "publish: uyarı · $NOTES_FILE yok, notes boş kalacak" >&2
fi
# JSON string escaping, by hand, because this machine may not have python on PATH.
ESCAPED=$(printf '%s' "$NOTES" | sed 's/\\/\\\\/g; s/"/\\"/g')
PUBLISHED=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

TMPDIR_PUB=$(mktemp -d "${TMPDIR:-/tmp}/meeting-os-publish.XXXXXX") || exit 1
trap 'rm -rf "$TMPDIR_PUB"' EXIT INT TERM
LATEST="$TMPDIR_PUB/latest.json"
cat > "$LATEST" <<JSON
{"version":"$VERSION","file":"$NAME","sha256":"$SHA","size":$SIZE,"published":"$PUBLISHED","notes":"$ESCAPED"}
JSON

echo "==> $NAME · $VERSION · $SIZE bayt · $TARGET:$REMOTE_DIR"
ssh "$TARGET" "mkdir -p '$REMOTE_DIR'"

echo "==> scp zip (büyük dosya; birkaç dakika)"
scp -q "$ZIP" "$SHA_FILE" "$TARGET:$REMOTE_DIR/"

verify() {
    _local=$1
    _remote=$2
    _lsize=$(wc -c < "$_local" | tr -d ' ')
    _rsize=$(ssh "$TARGET" "wc -c < '$_remote'" | tr -d ' ')
    if [ "$_lsize" != "$_rsize" ]; then
        echo "publish: boyut uyuşmuyor $_remote (yerel $_lsize, uzak $_rsize)" >&2
        exit 1
    fi
    echo "    $_remote $_rsize bayt ok"
}
echo "==> uzak boyut doğrulaması"
verify "$ZIP" "$REMOTE_DIR/$NAME"
verify "$SHA_FILE" "$REMOTE_DIR/$NAME.sha256"

# latest.json goes up LAST: until it lands, the old release is still the published one.
echo "==> latest.json"
scp -q "$LATEST" "$TARGET:$REMOTE_DIR/latest.json"
verify "$LATEST" "$REMOTE_DIR/latest.json"

ssh "$TARGET" "chown meetingos:meetingos '$REMOTE_DIR/$NAME' '$REMOTE_DIR/$NAME.sha256' '$REMOTE_DIR/latest.json' && chmod 644 '$REMOTE_DIR/$NAME' '$REMOTE_DIR/$NAME.sha256' '$REMOTE_DIR/latest.json'"

SECRET=$(ssh "$TARGET" "cat '$SECRET_FILE'" | tr -d ' \n\r')
if [ -z "$SECRET" ]; then
    echo "publish: $SECRET_FILE okunamadı; önce sh server/deploy.sh çalıştırın" >&2
    exit 1
fi

echo
echo "==> yayında: $VERSION"
[ -n "$NOTES" ] && echo "    $NOTES"
echo "    zip:    $BASE_URL/$SECRET/$NAME"
echo "    latest: $BASE_URL/$SECRET/latest.json"
echo
echo "    (bağlantı gizlidir; paylaşan herkes indirebilir)"
