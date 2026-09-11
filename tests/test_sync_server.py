"""Tests for the Meeting OS team sync server (server/sync_server.py)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import shutil
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER_PY = os.path.join(os.path.dirname(_HERE), "server", "sync_server.py")

_spec = importlib.util.spec_from_file_location("meetingos_sync_server", _SERVER_PY)
sync_server = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(sync_server)

TOKEN = "a" * 40
SECRET = "c" * 64
OTHER_TOKEN = "b" * 40
HOST_A = "Mac-A"
HOST_B = "Mac-B"


class _Server:
    def __init__(self, max_file: int = 4 * 1024 * 1024, max_team: int = 500 * 1024 * 1024,
                 secret: str | None = SECRET, downloads: str | None = None):
        self.root = tempfile.mkdtemp(prefix="sync-test-")
        self.secret_file = os.path.join(self.root, "download.secret")
        if secret is not None:
            with open(self.secret_file, "w", encoding="utf-8") as fh:
                fh.write(secret + "\n")
        self.downloads = downloads or os.path.join(self.root, "_downloads")
        os.makedirs(self.downloads, exist_ok=True)
        self.httpd = sync_server.make_server("127.0.0.1", 0, self.root,
                                             max_file=max_file, max_team=max_team,
                                             downloads=self.downloads,
                                             download_secret_file=self.secret_file)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return "http://127.0.0.1:%d" % self.port

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        shutil.rmtree(self.root, ignore_errors=True)


def request(server: _Server, method: str, path: str, *, token: str | None = TOKEN,
            host: str | None = None, body: bytes | None = None,
            headers: dict | None = None, prefix: str = "/v1"):
    url = server.base + prefix + path
    req = urllib.request.Request(url, data=body, method=method)
    if token is not None:
        req.add_header("Authorization", "Bearer " + token)
    if host is not None:
        req.add_header("X-Meeting-OS-Host", host)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def fetch(server: _Server, path: str, *, method: str = "GET", headers: dict | None = None):
    """The download route the way a browser or `curl -C -` hits it: no Authorization header at all."""
    req = urllib.request.Request(server.base + path, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


class DownloadRouteTest(unittest.TestCase):
    """`/dl/<secret>/<name>` — the app bundle update channel (docs/BUNDLE.md). The secret IS the credential:
    there is no header to send, because a 1.3 GB zip has to be fetchable by a browser and resumable by the
    updater."""

    @classmethod
    def setUpClass(cls) -> None:
        logging.getLogger("meetingos-sync").setLevel(logging.CRITICAL)
        cls.server = _Server()
        cls.payload = bytes(range(256)) * 40      # 10240 bytes, every byte value
        with open(os.path.join(cls.server.downloads, "Meeting-OS-1.2.72.zip"), "wb") as fh:
            fh.write(cls.payload)
        cls.latest = json.dumps({"version": "1.2.72", "file": "Meeting-OS-1.2.72.zip"}).encode()
        with open(os.path.join(cls.server.downloads, "latest.json"), "wb") as fh:
            fh.write(cls.latest)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.close()

    def zip_url(self, secret: str = SECRET, prefix: str = "/dl") -> str:
        return "%s/%s/Meeting-OS-1.2.72.zip" % (prefix, secret)

    def test_the_zip_is_served_with_no_auth_header_under_both_prefixes(self):
        for prefix in ("/dl", "/meetingos/dl"):
            status, body, headers = fetch(self.server, self.zip_url(prefix=prefix))
            self.assertEqual(status, 200, prefix)
            self.assertEqual(body, self.payload)
            self.assertEqual(headers["Content-Type"], "application/zip")
            self.assertEqual(headers["Content-Length"], str(len(self.payload)))
            self.assertEqual(headers["Accept-Ranges"], "bytes")
            self.assertTrue(headers["ETag"].startswith('"'))

    def test_a_wrong_secret_is_404_not_403(self):
        for bad in ("d" * 64, SECRET[:-1] + "d", "", "short", SECRET + "d"):
            status, _, _ = fetch(self.server, "/dl/%s/Meeting-OS-1.2.72.zip" % bad)
            self.assertEqual(status, 404, bad[:8])

    def test_without_a_secret_file_the_whole_route_is_404(self):
        blind = _Server(secret=None)
        try:
            with open(os.path.join(blind.downloads, "latest.json"), "wb") as fh:
                fh.write(b"{}")
            self.assertEqual(fetch(blind, "/dl/%s/latest.json" % SECRET)[0], 404)
            self.assertEqual(fetch(blind, "/dl//latest.json")[0], 404)
            self.assertEqual(request(blind, "GET", "/ping", token=None)[0], 200)   # the rest still works
        finally:
            blind.close()

    def test_a_short_or_malformed_secret_file_is_refused(self):
        for bad_secret in ("abc", "z" * 64, ""):
            blind = _Server(secret=bad_secret)
            try:
                with open(os.path.join(blind.downloads, "latest.json"), "wb") as fh:
                    fh.write(b"{}")
                self.assertEqual(fetch(blind, "/dl/%s/latest.json" % bad_secret)[0], 404, bad_secret)
            finally:
                blind.close()

    def test_traversal_and_dotfiles_are_404(self):
        outside = os.path.join(self.server.root, "outside.txt")
        with open(outside, "wb") as fh:
            fh.write(b"nope")
        with open(os.path.join(self.server.downloads, ".hidden"), "wb") as fh:
            fh.write(b"nope")
        for name in ("../outside.txt", "%2e%2e%2foutside.txt", "..%2Foutside.txt", ".hidden",
                     "..", ".", "sub/dir.zip", "a" * 121 + ".zip", "hop%00.zip", ""):
            status, _, _ = fetch(self.server, "/dl/%s/%s" % (SECRET, name))
            self.assertEqual(status, 404, name)

    def test_a_range_resumes_the_download(self):
        status, body, headers = fetch(self.server, self.zip_url(),
                                      headers={"Range": "bytes=4096-"})
        self.assertEqual(status, 206)
        self.assertEqual(body, self.payload[4096:])
        self.assertEqual(headers["Content-Range"], "bytes 4096-10239/10240")
        self.assertEqual(headers["Content-Length"], str(len(self.payload) - 4096))

        status, body, headers = fetch(self.server, self.zip_url(),
                                      headers={"Range": "bytes=10-19"})
        self.assertEqual(status, 206)
        self.assertEqual(body, self.payload[10:20])
        self.assertEqual(headers["Content-Range"], "bytes 10-19/10240")

        # past the end is 416, a malformed header is simply ignored
        self.assertEqual(fetch(self.server, self.zip_url(), headers={"Range": "bytes=99999-"})[0], 416)
        status, body, _ = fetch(self.server, self.zip_url(), headers={"Range": "elma-armut"})
        self.assertEqual((status, body), (200, self.payload))

    def test_head_gives_the_size_without_the_body(self):
        status, body, headers = fetch(self.server, self.zip_url(), method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(headers["Content-Length"], str(len(self.payload)))
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(fetch(self.server, "/dl/%s/yok.zip" % SECRET, method="HEAD")[0], 404)

    def test_json_gets_its_own_content_type_and_the_sidecar_becomes_the_etag(self):
        status, body, headers = fetch(self.server, "/dl/%s/latest.json" % SECRET)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["version"], "1.2.72")
        self.assertEqual(headers["Content-Type"], "application/json")

        digest = hashlib.sha256(self.payload).hexdigest()
        with open(os.path.join(self.server.downloads, "Meeting-OS-1.2.72.zip.sha256"), "w") as fh:
            fh.write("%s  Meeting-OS-1.2.72.zip\n" % digest)
        _status, _body, headers = fetch(self.server, self.zip_url())
        self.assertEqual(headers["ETag"], '"%s"' % digest)
        # and an unchanged file is answered 304
        status, body, _ = fetch(self.server, self.zip_url(), headers={"If-None-Match": '"%s"' % digest})
        self.assertEqual((status, body), (304, b""))

    def test_downloads_are_not_a_team_and_never_reach_the_index(self):
        status, _, _ = request(self.server, "PUT", "/file/words/%s.jsonl" % HOST_A,
                               host=HOST_A, body=b'{"w":1}')
        self.assertEqual(status, 200)
        status, body, _ = request(self.server, "GET", "/index")
        index = json.loads(body)
        self.assertNotIn("_downloads", index["hosts"])
        self.assertFalse([p for p in index["files"] if "_downloads" in p or "Meeting-OS" in p])
        # and the download route cannot be used as a writer
        self.assertEqual(fetch(self.server, self.zip_url(), method="PUT")[0], 405)


class SyncServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        logging.getLogger("meetingos-sync").setLevel(logging.CRITICAL)
        cls.server = _Server()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.close()

    # ---- auth ----------------------------------------------------------

    def test_ping_needs_no_auth(self):
        status, body, _ = request(self.server, "GET", "/ping", token=None)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["version"], "1")
        self.assertTrue(payload["time"].endswith("Z"))

    def test_head_ping_has_no_body(self):
        status, body, _ = request(self.server, "HEAD", "/ping", token=None)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")

    def test_missing_token_is_401(self):
        status, body, _ = request(self.server, "GET", "/index", token=None)
        self.assertEqual(status, 401)
        self.assertIn("error", json.loads(body))

    def test_bad_token_is_401(self):
        for bad in ("nothex" * 8, "abc", "A" * 40, "a" * 200):
            status, _, _ = request(self.server, "GET", "/index", token=bad)
            self.assertEqual(status, 401, bad[:10])

    # ---- path whitelist -------------------------------------------------

    def test_path_outside_whitelist_is_403(self):
        for bad in ("secret.txt", "words/Mac-A.txt", "reports/Mac-A/deep/x.json",
                    "profiles/Mac-A.jsonl/x", "etc/passwd"):
            status, _, _ = request(self.server, "GET", "/file/" + bad)
            self.assertEqual(status, 403, bad)

    def test_dotdot_is_403(self):
        for bad in ("../../etc/passwd", "reports/../words/Mac-A.jsonl",
                    "%2e%2e/%2e%2e/etc/passwd", "reports/Mac-A/../../x.json",
                    "/words/Mac-A.jsonl", "words//Mac-A.jsonl"):
            status, _, _ = request(self.server, "GET", "/file/" + bad)
            self.assertEqual(status, 403, bad)

    def test_put_to_other_host_path_is_403(self):
        status, _, _ = request(self.server, "PUT", "/file/words/%s.jsonl" % HOST_B,
                               host=HOST_A, body=b"nope")
        self.assertEqual(status, 403)
        status, _, _ = request(self.server, "PUT", "/file/words/%s.jsonl" % HOST_A,
                               body=b"nope")  # no host header at all
        self.assertEqual(status, 403)

    def test_delete_other_host_is_403_own_is_ok(self):
        path = "/file/profiles/%s.jsonl" % HOST_B
        status, _, _ = request(self.server, "PUT", path, host=HOST_B, body=b'{"n":1}')
        self.assertEqual(status, 200)
        status, _, _ = request(self.server, "DELETE", path, host=HOST_A)
        self.assertEqual(status, 403)
        status, body, _ = request(self.server, "DELETE", path, host=HOST_B)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["deleted"])
        status, _, _ = request(self.server, "GET", path)
        self.assertEqual(status, 404)
        # deleting a missing file still reports true
        status, body, _ = request(self.server, "DELETE", path, host=HOST_B)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["deleted"])

    # ---- roundtrip ------------------------------------------------------

    def test_put_get_index_roundtrip(self):
        payload = b'{"word":"kadans"}\n'
        digest = hashlib.sha256(payload).hexdigest()
        status, body, _ = request(self.server, "PUT", "/file/words/%s.jsonl" % HOST_A,
                                  host=HOST_A, body=payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"sha256": digest, "size": len(payload)})

        report = b'{"ok":true}'
        status, _, _ = request(self.server, "PUT", "/file/reports/%s/heartbeat.json" % HOST_B,
                               host=HOST_B, body=report)
        self.assertEqual(status, 200)

        # any team member may read any team file
        status, body, headers = request(self.server, "GET", "/file/words/%s.jsonl" % HOST_A,
                                        host=HOST_B)
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)
        self.assertEqual(headers["ETag"], '"%s"' % digest)

        status, body, _ = request(self.server, "GET", "/index")
        self.assertEqual(status, 200)
        index = json.loads(body)
        entry = index["files"]["words/%s.jsonl" % HOST_A]
        self.assertEqual(entry["sha256"], digest)
        self.assertEqual(entry["size"], len(payload))
        self.assertTrue(entry["updated"].endswith("Z"))
        self.assertIn("reports/%s/heartbeat.json" % HOST_B, index["files"])
        self.assertEqual(index["hosts"], sorted({HOST_A, HOST_B}))

        # file mode is 0600 on disk
        team_id = hashlib.sha256(TOKEN.encode()).hexdigest()[:32]
        disk = os.path.join(self.server.root, team_id, "words", "%s.jsonl" % HOST_A)
        self.assertEqual(os.stat(disk).st_mode & 0o777, 0o600)

    def test_teams_are_isolated(self):
        request(self.server, "PUT", "/file/errors/%s.jsonl" % HOST_A, host=HOST_A, body=b"x")
        status, body, _ = request(self.server, "GET", "/index", token=OTHER_TOKEN)
        self.assertEqual(status, 200)
        self.assertNotIn("errors/%s.jsonl" % HOST_A, json.loads(body)["files"])

    def test_if_none_match_304(self):
        path = "/file/glossary/%s.jsonl" % HOST_A
        payload = b"term\n"
        request(self.server, "PUT", path, host=HOST_A, body=payload)
        status, _, headers = request(self.server, "GET", path)
        etag = headers["ETag"]
        status, body, headers = request(self.server, "GET", path,
                                        headers={"If-None-Match": etag})
        self.assertEqual(status, 304)
        self.assertEqual(body, b"")
        self.assertEqual(headers["ETag"], etag)
        # a stale etag still returns the body
        status, body, _ = request(self.server, "GET", path,
                                  headers={"If-None-Match": '"deadbeef"'})
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)

    def test_prefix_tolerance(self):
        payload = b"prefixed\n"
        status, _, _ = request(self.server, "PUT", "/file/words/%s.jsonl" % HOST_B,
                               host=HOST_B, body=payload, prefix="/meetingos/v1")
        self.assertEqual(status, 200)
        status, body, _ = request(self.server, "GET", "/file/words/%s.jsonl" % HOST_B,
                                  prefix="/meetingos/v1")
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)
        # same bytes are visible through the bare prefix
        status, body, _ = request(self.server, "GET", "/file/words/%s.jsonl" % HOST_B)
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)
        status, _, _ = request(self.server, "GET", "/ping", token=None, prefix="/meetingos/v1")
        self.assertEqual(status, 200)

    def test_unknown_endpoint_is_404(self):
        status, _, _ = request(self.server, "GET", "/nope")
        self.assertEqual(status, 404)
        status, _, _ = request(self.server, "GET", "/index", prefix="/v2")
        self.assertEqual(status, 404)

    # ---- limits ---------------------------------------------------------

    def test_max_file_413(self):
        small = _Server(max_file=64)
        try:
            status, body, _ = request(small, "PUT", "/file/words/%s.jsonl" % HOST_A,
                                      host=HOST_A, body=b"x" * 65)
            self.assertEqual(status, 413)
            self.assertIn("error", json.loads(body))
            status, _, _ = request(small, "PUT", "/file/words/%s.jsonl" % HOST_A,
                                   host=HOST_A, body=b"x" * 64)
            self.assertEqual(status, 200)
        finally:
            small.close()

    def test_max_team_413(self):
        small = _Server(max_file=1024, max_team=100)
        try:
            status, _, _ = request(small, "PUT", "/file/words/%s.jsonl" % HOST_A,
                                   host=HOST_A, body=b"x" * 80)
            self.assertEqual(status, 200)
            status, _, _ = request(small, "PUT", "/file/words/%s.jsonl" % HOST_B,
                                   host=HOST_B, body=b"y" * 80)
            self.assertEqual(status, 413)
            # overwriting my own file does not double count
            status, _, _ = request(small, "PUT", "/file/words/%s.jsonl" % HOST_A,
                                   host=HOST_A, body=b"z" * 90)
            self.assertEqual(status, 200)
        finally:
            small.close()

    def test_missing_content_length_is_411(self):
        with socket.create_connection(("127.0.0.1", self.server.port), timeout=5) as sock:
            req = (
                "PUT /v1/file/words/%s.jsonl HTTP/1.1\r\n"
                "Host: 127.0.0.1\r\n"
                "Authorization: Bearer %s\r\n"
                "X-Meeting-OS-Host: %s\r\n"
                "Connection: close\r\n\r\n" % (HOST_A, TOKEN, HOST_A)
            )
            sock.sendall(req.encode("ascii"))
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        self.assertIn(b" 411 ", data.split(b"\r\n", 1)[0] + b" ")

    # ---- concurrency ----------------------------------------------------

    def test_concurrent_puts_all_land(self):
        conc = _Server()
        try:
            bodies = {}

            def put(i: int):
                host = "Mac-%02d" % i
                payload = (("%d" % i) * 4096).encode()
                bodies[host] = payload
                return request(conc, "PUT", "/file/profiles/%s.jsonl" % host,
                               host=host, body=payload)[0]

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(put, range(8)))
            self.assertEqual(results, [200] * 8)

            status, body, _ = request(conc, "GET", "/index")
            index = json.loads(body)
            self.assertEqual(len(index["hosts"]), 8)
            for host, payload in bodies.items():
                entry = index["files"]["profiles/%s.jsonl" % host]
                self.assertEqual(entry["size"], len(payload))
                self.assertEqual(entry["sha256"], hashlib.sha256(payload).hexdigest())
                status, got, _ = request(conc, "GET", "/file/profiles/%s.jsonl" % host)
                self.assertEqual(got, payload)
            # no temp files left behind
            leftovers = [n for _d, _s, fs in os.walk(conc.root) for n in fs
                         if n.startswith(".tmp-")]
            self.assertEqual(leftovers, [])
        finally:
            conc.close()


if __name__ == "__main__":
    unittest.main()
