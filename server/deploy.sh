#!/bin/sh
# Deploy the Meeting OS team sync server to the VPS. Run from a Mac:
#
#     sh server/deploy.sh                    # default target
#     TARGET=root@1.2.3.4 sh server/deploy.sh
#
# Idempotent: safe to re-run after every change to sync_server.py.
set -eu

TARGET=${TARGET:-root@100.87.35.111}
CODE_DIR=/opt/meetingos-sync
STATE_DIR=/var/lib/meetingos-sync
UNIT=meetingos-sync
PING_URL=http://127.0.0.1:8790/v1/ping

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SRC_SERVER="$HERE/sync_server.py"
SRC_UNIT="$HERE/$UNIT.service"
SRC_BACKUP="$HERE/backup.sh"

for f in "$SRC_SERVER" "$SRC_UNIT" "$SRC_BACKUP"; do
    [ -f "$f" ] || { echo "deploy: missing $f" >&2; exit 1; }
done

echo "==> target $TARGET"

# 1. user + directories -------------------------------------------------
ssh "$TARGET" 'sh -s' <<'REMOTE'
set -eu
if ! id -u meetingos >/dev/null 2>&1; then
    if [ -x /usr/sbin/nologin ]; then SHELL_BIN=/usr/sbin/nologin
    elif [ -x /sbin/nologin ]; then SHELL_BIN=/sbin/nologin
    else SHELL_BIN=/bin/false; fi
    useradd --system --no-create-home --home-dir /var/lib/meetingos-sync \
            --shell "$SHELL_BIN" meetingos
    echo "created system user meetingos"
fi
mkdir -p /opt/meetingos-sync /var/lib/meetingos-sync /var/backups/meetingos-sync
chown root:root /opt/meetingos-sync
chmod 755 /opt/meetingos-sync
chown -R meetingos:meetingos /var/lib/meetingos-sync
chmod 700 /var/lib/meetingos-sync
chmod 700 /var/backups/meetingos-sync
REMOTE

# 2. copy files ---------------------------------------------------------
echo "==> scp"
scp -q "$SRC_SERVER" "$SRC_BACKUP" "$SRC_UNIT" "$TARGET:$CODE_DIR/"

# 3. verify every remote write byte for byte ----------------------------
echo "==> verify remote sizes"
verify() {
    _local=$1
    _remote=$2
    _lsize=$(wc -c < "$_local" | tr -d ' ')
    _rsize=$(ssh "$TARGET" "wc -c < '$_remote'" | tr -d ' ')
    if [ "$_lsize" != "$_rsize" ]; then
        echo "deploy: size mismatch for $_remote (local $_lsize, remote $_rsize)" >&2
        exit 1
    fi
    echo "    $_remote $_rsize bytes ok"
}
verify "$SRC_SERVER" "$CODE_DIR/sync_server.py"
verify "$SRC_BACKUP" "$CODE_DIR/backup.sh"
verify "$SRC_UNIT" "$CODE_DIR/$UNIT.service"

# 4. install unit + backup cron, restart --------------------------------
ssh "$TARGET" 'sh -s' <<'REMOTE'
set -eu
chmod 755 /opt/meetingos-sync/sync_server.py /opt/meetingos-sync/backup.sh
chown root:root /opt/meetingos-sync/sync_server.py /opt/meetingos-sync/backup.sh
install -m 644 -o root -g root /opt/meetingos-sync/meetingos-sync.service \
        /etc/systemd/system/meetingos-sync.service

CRON_LINE='17 3 * * * /opt/meetingos-sync/backup.sh'
if crontab -l 2>/dev/null | grep -Fq '/opt/meetingos-sync/backup.sh'; then
    echo "backup cron already installed"
else
    { crontab -l 2>/dev/null; echo "$CRON_LINE"; } | crontab -
    echo "backup cron installed"
fi

systemctl daemon-reload
systemctl enable --now meetingos-sync
systemctl restart meetingos-sync
REMOTE

# 5. health check -------------------------------------------------------
echo "==> ping"
i=1
while [ "$i" -le 10 ]; do
    if OUT=$(ssh "$TARGET" "curl -fsS $PING_URL" 2>/dev/null); then
        echo "$OUT"
        echo "==> ok"
        exit 0
    fi
    i=$((i + 1))
    sleep 1
done

echo "deploy: ping failed at $PING_URL" >&2
ssh "$TARGET" "systemctl status $UNIT --no-pager -l | tail -n 20" >&2 || true
exit 1
