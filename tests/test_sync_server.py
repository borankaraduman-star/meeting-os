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
OTHER_TOKEN = "b" * 40
HOST_A = "Mac-A"
HOST_B = "Mac-B"


class _Server:
    def __init__(self, max_file: int = 4 * 1024 * 1024, max_team: int = 500 * 1024 * 1024):
        self.root = tempfile.mkdtemp(prefix="sync-test-")
        self.httpd = sync_server.make_server("127.0.0.1", 0, self.root,
                                             max_file=max_file, max_team=max_team)
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
