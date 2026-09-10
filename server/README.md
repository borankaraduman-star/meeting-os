# meetingos-sync

Dumb per-team, per-host file store behind the Meeting OS team cloud (`docs/TEAM_CLOUD.md`).
Python 3.12 stdlib only, listens on `127.0.0.1:8790`, stores `<root>/<team_id>/<path>` with
`team_id = sha256(token)[:32]`. The raw token is never written to disk and never logged.

Auth: `Authorization: Bearer <32–128 hex>`; owner host: `X-Meeting-OS-Host`. `PUT`/`DELETE` only on
paths whose `<host>` segment equals that header; `GET` on any file of the same team. Allowed paths:
`(words|glossary|profiles|errors)/<host>.jsonl` and `reports/<host>/<name>.json` — anything else 403.
Both `/v1/…` and `/meetingos/v1/…` are accepted. Limits: 4 MB per file, 500 MB per team (413),
`Content-Length` required on PUT (411). Errors are JSON `{"error": "…"}`.

| Endpoint | Response |
|---|---|
| `GET /v1/ping` | `{"ok":true,"version":"1","time":"<utc>"}` — no auth |
| `GET /v1/index` | `{"files":{"<path>":{"sha256","size","updated"}},"hosts":[…]}` |
| `GET /v1/file/<path>` | raw bytes, `ETag: "<sha256>"`; `If-None-Match` match → 304 |
| `PUT /v1/file/<path>` | `{"sha256":"…","size":n}`; atomic write (tmp + rename), mode 0600 |
| `DELETE /v1/file/<path>` | `{"deleted":true}` (true even if it was missing) |

## Deploy

    TARGET=root@100.87.35.111 sh server/deploy.sh

Creates the `meetingos` system user, copies `sync_server.py`, `backup.sh` and the unit to
`/opt/meetingos-sync`, verifies each remote file size, installs the daily backup cron
(`17 3 * * *`), restarts the unit and prints the `/v1/ping` JSON (non-zero exit if it fails).

Public TLS via Tailscale Funnel:

    tailscale funnel --bg --set-path /meetingos http://127.0.0.1:8790

## Logs

    journalctl -u meetingos-sync -n 50           # one line per request, no tokens
    journalctl -u meetingos-sync -f              # follow

## Restore a backup

    systemctl stop meetingos-sync
    tar -xzf /var/backups/meetingos-sync/sync-YYYYmmdd.tar.gz -C /var/lib --overwrite
    chown -R meetingos:meetingos /var/lib/meetingos-sync && chmod 700 /var/lib/meetingos-sync
    systemctl start meetingos-sync
