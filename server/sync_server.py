#!/usr/bin/env python3
"""Meeting OS team sync server.

Dumb, per-team, per-host file storage for the Meeting OS team cloud
(see docs/TEAM_CLOUD.md). Standard library only, Python 3.12.

Storage layout::

    <root>/<team_id>/<path>

where ``team_id = sha256(token).hexdigest()[:32]``. The raw token is never
written to disk and never logged.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import http.server
import json
import logging
import os
import re
import socketserver
import stat
import sys
import tempfile
import traceback
import urllib.parse

VERSION = "1"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8790
DEFAULT_ROOT = "/var/lib/meetingos-sync"
DEFAULT_MAX_FILE = 4 * 1024 * 1024
DEFAULT_MAX_TEAM = 500 * 1024 * 1024

TOKEN_RE = re.compile(r"^[0-9a-f]{32,128}$")
HOST_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# The only paths that may ever exist inside a team directory.
FLAT_RE = re.compile(r"^(?:words|glossary|profiles|errors)/([A-Za-z0-9._-]{1,64})\.jsonl$")
REPORT_RE = re.compile(r"^reports/([A-Za-z0-9._-]{1,64})/[A-Za-z0-9._-]{1,120}\.json$")

PREFIXES = ("/meetingos/v1", "/v1")

# ---- download channel (app bundle updates, docs/BUNDLE.md) --------------
# A second, much dumber service on the same port: static files under <root>/_downloads served at
# /dl/<secret>/<name>. No Authorization header (a browser and `curl` must be able to fetch the 1.3 GB app
# zip), so the secret IS the credential and the whole path is a secret — never log it. Nothing here can
# write, and the name character class has no "/" at all, so a team directory can never be reached from it.
DOWNLOAD_DIR_NAME = "_downloads"
DEFAULT_DOWNLOAD_SECRET_FILE = "/etc/meetingos-sync/download.secret"
DOWNLOAD_PREFIXES = ("/meetingos/dl", "/dl")
DOWNLOAD_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
SECRET_RE = re.compile(r"^[0-9a-fA-F]{32,128}$")
RANGE_RE = re.compile(r"^bytes=(\d{1,18})-(\d{0,18})$")
DOWNLOAD_CHUNK = 256 * 1024
CONTENT_TYPES = {".zip": "application/zip", ".json": "application/json"}

log = logging.getLogger("meetingos-sync")


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_from_ts(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def team_id_for(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def path_owner(path: str) -> str | None:
    """Return the host that owns ``path``, or None if the path is not allowed.

    The regexes alone are not enough: ``..`` matches the host character class,
    so every segment is checked explicitly for traversal, absolute and empty
    segments first.
    """
    if not path or path.startswith("/") or path.endswith("/"):
        return None
    if "\\" in path or "\x00" in path:
        return None
    segments = path.split("/")
    for seg in segments:
        if seg in ("", ".", ".."):
            return None
    m = FLAT_RE.match(path) or REPORT_RE.match(path)
    if not m:
        return None
    owner = m.group(1)
    if owner in (".", "..") or not HOST_RE.match(owner):
        return None
    return owner


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_download_secret(path: str) -> str | None:
    """The download secret, or None when the file is missing/empty/malformed.

    Read on every request instead of at startup: `deploy.sh` creates the file and restarts the unit, but a
    server that came up before it existed must start serving as soon as it does, and rotating the secret must
    not need a restart. The file is 64 bytes; the read is cheaper than the TLS handshake in front of it.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read(256).strip()
    except OSError:
        return None
    return raw if SECRET_RE.match(raw) else None


def sidecar_sha256(path: str) -> str | None:
    """`<name>.sha256` next to the file (shasum format or a bare hex digest), if it is readable."""
    try:
        with open(path + ".sha256", "r", encoding="utf-8", errors="replace") as fh:
            fields = fh.read(200).strip().split()
    except OSError:
        return None
    token = fields[0] if fields else ""
    return token.lower() if re.fullmatch(r"[0-9a-fA-F]{64}", token) else None


def parse_range(header: str, total: int) -> tuple[int, int] | None:
    """(start, end) inclusive for `bytes=s-` and `bytes=s-e`; None when the header is not one we honour.

    Only a single range is supported on purpose — resuming a download is the only reason this exists, and a
    multipart/byteranges response is a body format worth nobody's time here.
    """
    m = RANGE_RE.match((header or "").strip())
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else total - 1
    if end >= total:
        end = total - 1
    if start > end or start >= total:
        raise HttpError(416, "range not satisfiable")
    return start, end


def ensure_dir(path: str) -> None:
    """Create ``path`` and its parents with mode 0700 (umask independent)."""
    parts: list[str] = []
    cur = path
    while cur and not os.path.isdir(cur):
        parts.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    for d in reversed(parts):
        try:
            os.mkdir(d, 0o700)
        except FileExistsError:
            pass
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass


def atomic_write(dest: str, data: bytes) -> None:
    ensure_dir(os.path.dirname(dest))
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(dest))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def walk_team(team_dir: str) -> dict[str, dict]:
    """Return {relpath: {sha256, size, updated}} for whitelisted team files.

    Teams are small (a handful of Macs, a few files each), so a plain walk on
    every index request is cheap and needs no cache.
    """
    out: dict[str, dict] = {}
    if not os.path.isdir(team_dir):
        return out
    for dirpath, dirnames, filenames in os.walk(team_dir):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, team_dir).replace(os.sep, "/")
            if path_owner(rel) is None:
                continue
            try:
                st = os.stat(full)
                with open(full, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            out[rel] = {
                "sha256": sha256_bytes(data),
                "size": st.st_size,
                "updated": utc_from_ts(st.st_mtime),
            }
    return out


def team_total_bytes(team_dir: str) -> int:
    total = 0
    if not os.path.isdir(team_dir):
        return 0
    for dirpath, _dirnames, filenames in os.walk(team_dir):
        for name in filenames:
            try:
                total += os.stat(os.path.join(dirpath, name)).st_size
            except OSError:
                continue
    return total


class HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class SyncHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "meetingos-sync/" + VERSION
    sys_version = ""

    # ---- plumbing -------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401 - silence default
        return

    def log_error(self, fmt: str, *args) -> None:  # noqa: D401 - silence default
        return

    def _access_log(self, status: int, nbytes: int) -> None:
        log.info(
            "%s team=%s host=%s %s %s %s %s",
            utc_now(),
            getattr(self, "_team_short", "-") or "-",
            getattr(self, "_host", "-") or "-",
            self.command or "-",
            getattr(self, "_log_path", self.path) or "-",
            status,
            nbytes,
        )

    def _respond(self, status: int, body: bytes, headers: dict | None = None,
                 send_body: bool = True) -> None:
        headers = dict(headers or {})
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if status != 304:
            self.send_header("Content-Length", str(len(body)))
        if getattr(self, "_must_close", False):
            self.close_connection = True
            self.send_header("Connection", "close")
        self.end_headers()
        if send_body and status != 304 and body:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        self._access_log(status, len(body))

    def _respond_json(self, status: int, payload: dict, headers: dict | None = None,
                      send_body: bool = True) -> None:
        body = (json.dumps(payload, sort_keys=False, ensure_ascii=False) + "\n").encode("utf-8")
        hdrs = {"Content-Type": "application/json; charset=utf-8"}
        hdrs.update(headers or {})
        self._respond(status, body, hdrs, send_body=send_body)

    def _error(self, status: int, message: str) -> None:
        # A request whose body was never drained cannot share the connection.
        if self.command in ("PUT", "POST") and not getattr(self, "_body_read", False):
            self._must_close = True
        self._respond_json(status, {"error": message}, send_body=self.command != "HEAD")

    # ---- request parsing -------------------------------------------------

    def _split_path(self) -> tuple[str, str]:
        raw = self.path.split("?", 1)[0].split("#", 1)[0]
        for prefix in PREFIXES:
            if raw == prefix or raw.startswith(prefix + "/"):
                return prefix, raw[len(prefix):]
        raise HttpError(404, "unknown endpoint")

    def _token(self) -> str:
        auth = self.headers.get("Authorization", "") or ""
        if not auth.lower().startswith("bearer "):
            raise HttpError(401, "missing bearer token")
        token = auth[7:].strip()
        if not TOKEN_RE.match(token):
            raise HttpError(401, "invalid token")
        return token

    def _team_dir(self) -> str:
        token = self._token()
        tid = team_id_for(token)
        self._team_short = tid[:6]
        # team_id is always 32 hex characters, so it can never collide with _downloads; the guard is here so
        # that stays true if the id scheme ever changes.
        if tid == DOWNLOAD_DIR_NAME:
            raise HttpError(403, "reserved team id")
        return os.path.join(self.server.cfg["root"], tid)

    def _client_host(self) -> str | None:
        value = (self.headers.get("X-Meeting-OS-Host") or "").strip()
        if not value or not HOST_RE.match(value):
            return None
        return value

    def _file_path(self, rest: str) -> tuple[str, str]:
        """Return (relative path, owning host) for /file/<path>."""
        raw = rest[len("/file/"):]
        rel = urllib.parse.unquote(raw)
        owner = path_owner(rel)
        if owner is None:
            raise HttpError(403, "path not allowed")
        return rel, owner

    def _read_body(self) -> bytes:
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            raise HttpError(411, "Content-Length required")
        try:
            length = int(raw_len)
        except ValueError:
            raise HttpError(400, "bad Content-Length") from None
        if length < 0:
            raise HttpError(400, "bad Content-Length")
        if length > self.server.cfg["max_file"]:
            raise HttpError(413, "file too large")
        data = b""
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                break
            data += chunk
            remaining -= len(chunk)
        self._body_read = True
        if len(data) != length:
            raise HttpError(400, "short body")
        return data

    # ---- dispatch --------------------------------------------------------

    def _dispatch(self, method: str) -> None:
        self._team_short = "-"
        self._host = self._client_host() or "-"
        self._must_close = False
        self._body_read = False

        raw = self.path.split("?", 1)[0].split("#", 1)[0]
        for prefix in DOWNLOAD_PREFIXES:
            if raw == prefix or raw.startswith(prefix + "/"):
                # The secret lives in the path, so the path never reaches the journal.
                self._log_path = prefix + "/<secret>/…"
                if method not in ("GET", "HEAD"):
                    raise HttpError(405, "method not allowed")
                self._download(raw[len(prefix):], method)
                return

        _prefix, rest = self._split_path()
        self._log_path = rest

        if rest == "/ping":
            if method not in ("GET", "HEAD"):
                raise HttpError(405, "method not allowed")
            self._respond_json(200, {"ok": True, "version": VERSION, "time": utc_now()},
                               send_body=method != "HEAD")
            return

        team_dir = self._team_dir()

        if rest == "/index":
            if method not in ("GET", "HEAD"):
                raise HttpError(405, "method not allowed")
            files = walk_team(team_dir)
            hosts = sorted({path_owner(p) for p in files if path_owner(p)})
            payload = {"files": files, "hosts": hosts}
            body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            etag = '"%s"' % sha256_bytes(body)
            if self._if_none_match(etag):
                self._respond(304, b"", {"ETag": etag}, send_body=False)
                return
            self._respond(200, body,
                          {"Content-Type": "application/json; charset=utf-8", "ETag": etag},
                          send_body=method != "HEAD")
            return

        if rest.startswith("/file/"):
            rel, owner = self._file_path(rest)
            dest = os.path.join(team_dir, *rel.split("/"))
            if method in ("GET", "HEAD"):
                self._get_file(dest, method)
                return
            if method == "PUT":
                self._put_file(team_dir, dest, rel, owner)
                return
            if method == "DELETE":
                self._delete_file(dest, owner)
                return
            raise HttpError(405, "method not allowed")

        raise HttpError(404, "unknown endpoint")

    def _if_none_match(self, etag: str) -> bool:
        header = self.headers.get("If-None-Match")
        if not header:
            return False
        bare = etag.strip('"')
        for candidate in header.split(","):
            candidate = candidate.strip()
            if candidate.startswith("W/"):
                candidate = candidate[2:].strip()
            if candidate == "*" or candidate == etag or candidate.strip('"') == bare:
                return True
        return False

    def _get_file(self, dest: str, method: str) -> None:
        try:
            with open(dest, "rb") as fh:
                data = fh.read()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            raise HttpError(404, "not found") from None
        etag = '"%s"' % sha256_bytes(data)
        if self._if_none_match(etag):
            self._respond(304, b"", {"ETag": etag}, send_body=False)
            return
        self._respond(200, data,
                      {"Content-Type": "application/octet-stream", "ETag": etag},
                      send_body=method != "HEAD")

    # ---- download channel ------------------------------------------------

    def _download(self, rest: str, method: str) -> None:
        """Serve <downloads>/<name> for /dl/<secret>/<name>. Every refusal is the same 404.

        A wrong secret, a missing secret file, a bad name and a missing file all answer identically: the route
        must not tell a scanner which of the four it got wrong.
        """
        parts = [urllib.parse.unquote(p) for p in rest.split("/")]
        if len(parts) != 3 or parts[0] != "":
            raise HttpError(404, "not found")
        secret, name = parts[1], parts[2]
        expected = read_download_secret(self.server.cfg["download_secret_file"])
        if not expected or not hmac.compare_digest(secret, expected):
            raise HttpError(404, "not found")
        if not DOWNLOAD_NAME_RE.match(name) or name.startswith("."):
            raise HttpError(404, "not found")   # no dotfiles, no "..", and the class has no "/" at all
        self._send_download(os.path.join(self.server.cfg["downloads"], name), name, method)

    def _send_download(self, path: str, name: str, method: str) -> None:
        try:
            st = os.stat(path)
        except OSError:
            raise HttpError(404, "not found") from None
        if not stat.S_ISREG(st.st_mode):
            raise HttpError(404, "not found")
        total = st.st_size
        digest = sidecar_sha256(path)
        etag = '"%s"' % (digest or "%x-%x" % (int(st.st_mtime), total))
        ctype = CONTENT_TYPES.get(os.path.splitext(name)[1].lower(), "application/octet-stream")
        headers = {"Content-Type": ctype, "ETag": etag, "Accept-Ranges": "bytes"}

        if self._if_none_match(etag):
            self._respond(304, b"", headers, send_body=False)
            return

        start, end = 0, total - 1
        status = 200
        rng = parse_range(self.headers.get("Range", ""), total) if total else None
        if rng is not None:
            start, end = rng
            status = 206
            headers["Content-Range"] = "bytes %d-%d/%d" % (start, end, total)
        length = 0 if total == 0 else end - start + 1

        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if method != "HEAD" and length:
            # Streamed, never read whole: the app bundle is well over a gigabyte.
            try:
                with open(path, "rb") as fh:
                    fh.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = fh.read(min(DOWNLOAD_CHUNK, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                    if remaining:   # the file shrank under us; the promised length is now a lie
                        self.close_connection = True
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
            except OSError:
                self.close_connection = True
        self._access_log(status, length)

    def _put_file(self, team_dir: str, dest: str, rel: str, owner: str) -> None:
        host = self._client_host()
        if host is None or host != owner:
            raise HttpError(403, "host does not own this path")
        data = self._read_body()
        max_team = self.server.cfg["max_team"]
        try:
            existing = os.stat(dest).st_size
        except OSError:
            existing = 0
        if team_total_bytes(team_dir) - existing + len(data) > max_team:
            raise HttpError(413, "team quota exceeded")
        atomic_write(dest, data)
        self._respond_json(200, {"sha256": sha256_bytes(data), "size": len(data)})

    def _delete_file(self, dest: str, owner: str) -> None:
        host = self._client_host()
        if host is None or host != owner:
            raise HttpError(403, "host does not own this path")
        try:
            os.unlink(dest)
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            pass
        self._respond_json(200, {"deleted": True})

    # ---- HTTP verbs ------------------------------------------------------

    def _handle(self, method: str) -> None:
        try:
            self._dispatch(method)
        except HttpError as exc:
            self._error(exc.status, exc.message)
        except Exception:  # never let one bad request kill the server
            log.error("unhandled error for %s %s\n%s", method,
                      getattr(self, "_log_path", "-"), traceback.format_exc())
            try:
                self._error(500, "internal error")
            except Exception:
                pass

    def do_GET(self) -> None:
        self._handle("GET")

    def do_HEAD(self) -> None:
        self._handle("HEAD")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    def do_POST(self) -> None:
        self._handle("POST")


class SyncServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, cfg: dict) -> None:
        self.cfg = cfg
        super().__init__(addr, handler)

    def handle_error(self, request, client_address) -> None:
        log.error("connection error from %s\n%s", client_address[0] if client_address else "-",
                  traceback.format_exc())


def make_server(host: str, port: int, root: str, max_file: int = DEFAULT_MAX_FILE,
                max_team: int = DEFAULT_MAX_TEAM, downloads: str | None = None,
                download_secret_file: str = DEFAULT_DOWNLOAD_SECRET_FILE) -> SyncServer:
    ensure_dir(root)
    root = os.path.abspath(root)
    cfg = {"root": root, "max_file": max_file, "max_team": max_team,
           "downloads": os.path.abspath(downloads or os.path.join(root, DOWNLOAD_DIR_NAME)),
           "download_secret_file": download_secret_file}
    return SyncServer((host, port), SyncHandler, cfg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Meeting OS team sync server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--max-file", type=int, default=DEFAULT_MAX_FILE)
    parser.add_argument("--max-team", type=int, default=DEFAULT_MAX_TEAM)
    parser.add_argument("--downloads", default=None,
                        help="static download directory (default <root>/%s)" % DOWNLOAD_DIR_NAME)
    parser.add_argument("--download-secret-file", default=DEFAULT_DOWNLOAD_SECRET_FILE,
                        help="file holding the /dl/<secret>/ path secret (32-128 hex)")
    args = parser.parse_args(argv)

    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    server = make_server(args.host, args.port, args.root, args.max_file, args.max_team,
                         downloads=args.downloads, download_secret_file=args.download_secret_file)
    log.info("%s meetingos-sync listening on %s:%s root=%s max_file=%s max_team=%s downloads=%s secret=%s",
             utc_now(), args.host, args.port, server.cfg["root"], args.max_file, args.max_team,
             server.cfg["downloads"],
             "var" if read_download_secret(server.cfg["download_secret_file"]) else "yok")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
