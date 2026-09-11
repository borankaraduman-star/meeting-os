"""The bundle update channel (docs/BUNDLE.md): latest.json → zip → sha256 → ditto → swap-update.sh.

Nothing here touches the network, /Applications or the real data folder: the release server is a local
http.server on port 0, HOME is a temp directory and the app bundles are empty directories. The failure modes
that matter are the silent ones — a wrong sha256 accepted, a resumed download concatenated into garbage, a
swap that loses the installed app — so those are what the tests are about.
"""
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from meeting_os import updater

SECRET = 'a' * 64
REPO = Path(__file__).resolve().parents[1]


class Release:
    """A tiny stand-in for the VPS download route: /<secret>/latest.json and /<secret>/<file>, with Range."""

    def __init__(self, version='1.2.72', payload=None, sha=None, name='Meeting-OS-1.2.72.zip', notes='Yeni sürüm'):
        self.dir = Path(tempfile.mkdtemp(prefix='release-'))
        self.payload = payload if payload is not None else bytes(range(256)) * 64
        self.name = name
        self.ranges = []
        (self.dir/name).write_bytes(self.payload)
        (self.dir/'latest.json').write_text(json.dumps({
            'version': version, 'file': name,
            'sha256': sha or hashlib.sha256(self.payload).hexdigest(),
            'size': len(self.payload), 'published': '2026-09-11T00:00:00Z', 'notes': notes,
        }), encoding='utf-8')
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a): pass

            def do_GET(self):
                parts = self.path.strip('/').split('/')
                if len(parts) != 2 or parts[0] != SECRET:
                    self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
                target = outer.dir/parts[1]
                if not target.is_file():
                    self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
                data = target.read_bytes()
                rng = self.headers.get('Range')
                status = 200
                if rng:
                    outer.ranges.append(rng)
                    start = int(rng.split('=')[1].split('-')[0])
                    data, status = data[start:], 206
                    self.send_response(206)
                    self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, start + len(data) - 1, target.stat().st_size))
                else:
                    self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()

    @property
    def base(self):
        return 'http://127.0.0.1:%d/%s' % (self.httpd.server_address[1], SECRET)

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close(); self.thread.join(timeout=2)
        shutil.rmtree(self.dir, ignore_errors=True)


def runtime_json(tmp, version='1.2.71', **extra):
    """`Meeting OS.app/Contents/Resources/{runtime.json,repo}` — the layout check()/start() read the channel
    from."""
    res = Path(tmp)/'Meeting OS.app'/'Contents'/'Resources'
    (res/'repo').mkdir(parents=True, exist_ok=True)
    data = {'python': 'runtime/bin/python3', 'repo': 'repo', 'bundled': True, 'version': version}
    data.update(extra)
    (res/'runtime.json').write_text(json.dumps(data), encoding='utf-8')
    return res


class RuntimeDetectionTests(unittest.TestCase):
    def test_a_git_checkout_is_not_a_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(updater.bundled(tmp))
            self.assertIsNone(updater.bundle_runtime(tmp))

    def test_the_repo_inside_a_bundle_is_a_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = runtime_json(tmp)
            self.assertTrue(updater.bundled(res/'repo'))
            self.assertEqual(updater.bundle_runtime(res/'repo')['version'], '1.2.71')
            self.assertEqual(updater.app_bundle_path(updater.bundle_runtime(res/'repo')).name, 'Meeting OS.app')

    def test_a_runtime_json_without_the_bundled_flag_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = runtime_json(tmp)
            (res/'runtime.json').write_text(json.dumps({'python': 'p', 'repo': 'repo'}), encoding='utf-8')
            self.assertFalse(updater.bundled(res/'repo'))
            (res/'runtime.json').write_text('bozuk', encoding='utf-8')
            self.assertFalse(updater.bundled(res/'repo'))

    def test_the_secret_file_beats_the_runtime_json_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = runtime_json(tmp, download_secret='b' * 64)
            rt = updater.bundle_runtime(res/'repo')
            self.assertEqual(updater.bundle_secret(rt), 'b' * 64)
            self.assertEqual(updater.bundle_base(rt), updater.BUNDLE_HOST + '/' + 'b' * 64)
            (res/'download.secret').write_text(SECRET + '\n', encoding='utf-8')
            self.assertEqual(updater.bundle_secret(updater.bundle_runtime(res/'repo')), SECRET)

    def test_a_bundle_with_no_secret_at_all_says_so_instead_of_calling_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = runtime_json(tmp)
            r = updater.check(res/'repo')
            self.assertFalse(r['available'])
            self.assertEqual(r['error'], updater.NO_SECRET_ERROR)
            self.assertEqual((r['behind'], r['target']), (0, '1.2.71'))

    def test_a_malformed_secret_is_no_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = runtime_json(tmp, download_secret='kısa')
            self.assertEqual(updater.bundle_base(updater.bundle_runtime(res/'repo')), '')


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.release = Release(); self.addCleanup(self.release.close)

    def bundle(self, version):
        return runtime_json(self.tmp.name, version=version, download_base=self.release.base)/'repo'

    def test_an_older_bundle_is_offered_the_release_with_its_note(self):
        r = updater.check(self.bundle('1.2.71'))
        self.assertTrue(r['available'])
        self.assertEqual((r['behind'], r['target'], r['remote']), (1, '1.2.72', '1.2.72'))
        self.assertEqual(r['subjects'], ['Yeni sürüm'])
        self.assertEqual((r['file'], r['size']), ('Meeting-OS-1.2.72.zip', len(self.release.payload)))
        self.assertTrue(r['bundled'])
        self.assertNotIn('error', r)

    def test_the_same_or_a_newer_bundle_is_up_to_date(self):
        for version in ('1.2.72', '1.2.73', '1.3.0'):
            r = updater.check(self.bundle(version))
            self.assertFalse(r['available'], version)
            self.assertEqual(r['behind'], 0, version)
            self.assertEqual(r['subjects'], [])

    def test_versions_compare_as_numbers_not_as_text(self):
        self.assertGreater(updater.vkey('1.2.10'), updater.vkey('1.2.9'))   # "1.2.10" < "1.2.9" as strings
        self.assertTrue(updater.check(self.bundle('1.2.9'))['available'])
        self.assertIsNone(updater.vkey('el-yapımı'))
        # an unreadable local version must never mean "forever up to date"
        self.assertTrue(updater.check(self.bundle('el-yapımı'))['available'])

    def test_an_unreachable_server_is_an_error_not_an_exception(self):
        root = runtime_json(self.tmp.name, download_base='http://127.0.0.1:1/x')/'repo'
        r = updater.check(root)
        self.assertFalse(r['available'])
        self.assertEqual(r['error'], updater.UNREACHABLE_ERROR)
        self.assertEqual(r['target'], '1.2.71')

    def test_a_release_without_a_file_or_a_sha_is_not_offered(self):
        (self.release.dir/'latest.json').write_text(json.dumps({'version': '1.2.72'}), encoding='utf-8')
        r = updater.check(self.bundle('1.2.71'))
        self.assertFalse(r['available'])
        self.assertIn('eksik', r['error'])

    def test_the_check_never_waits_longer_than_five_seconds(self):
        self.assertEqual(updater.CHECK_TIMEOUT, 5)
        seen = {}
        real = updater.urllib.request.urlopen

        def fake(req, timeout=None):
            seen['timeout'] = timeout
            return real(req, timeout=timeout)
        with patch.object(updater.urllib.request, 'urlopen', fake):
            updater.check(self.bundle('1.2.71'))
        self.assertEqual(seen['timeout'], 5)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data = self.tmp/'data'; self.data.mkdir()
        self.cache = self.tmp/'cache'; self.cache.mkdir()

    def test_a_partial_file_is_resumed_with_a_range_header(self):
        release = Release(); self.addCleanup(release.close)
        dest = self.cache/release.name
        dest.write_bytes(release.payload[:5000])
        updater.download_resumable('%s/%s' % (release.base, release.name), dest, total_hint=len(release.payload))
        self.assertEqual(release.ranges, ['bytes=5000-'])
        self.assertEqual(dest.read_bytes(), release.payload)

    def test_a_server_that_ignores_the_range_restarts_the_file_instead_of_appending(self):
        release = Release(); self.addCleanup(release.close)
        dest = self.cache/release.name
        dest.write_bytes(b'eski' * 100)

        class Resp:
            status = 200
            headers = {'Content-Length': str(len(release.payload))}
            def __init__(self): self._data = [release.payload]
            def read(self, _n): return self._data.pop() if self._data else b''
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with patch.object(updater, '_get', lambda *a, **k: Resp()):
            updater.download_resumable('http://x/y', dest)
        self.assertEqual(dest.read_bytes(), release.payload)   # not 400 bytes of "eski" followed by the zip

    def test_a_complete_file_the_server_calls_out_of_range_is_left_alone(self):
        """A finished zip asks for `bytes=<size>-` and gets 416. That is not a failure: the sha256 check
        immediately after is what decides whether those bytes are the right ones."""
        release = Release(); self.addCleanup(release.close)
        dest = self.cache/release.name
        dest.write_bytes(release.payload)

        def boom(*_a, **_k):
            raise updater.urllib.error.HTTPError('http://x', 416, 'range', {}, None)
        with patch.object(updater, '_get', boom):
            self.assertEqual(updater.download_resumable('http://x/y', dest), len(release.payload))
        self.assertEqual(dest.read_bytes(), release.payload)

    def test_progress_is_reported_as_a_percentage(self):
        release = Release(); self.addCleanup(release.close)
        seen = []
        updater.download_resumable('%s/%s' % (release.base, release.name), self.cache/release.name,
                                   total_hint=len(release.payload),
                                   on_progress=lambda d, t: seen.append(int(d * 100 / t)))
        self.assertEqual(seen[0], 0)
        self.assertEqual(seen[-1], 100)


class WorkerTests(unittest.TestCase):
    """`run_download` end to end, with a real `ditto` on a real zip and a fake swap script."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data = self.tmp/'data'; self.data.mkdir()
        self.cache = self.tmp/'cache'; self.cache.mkdir()
        self.swap_calls = self.tmp/'swap-args.txt'
        self.swap = self.tmp/'fake-swap.sh'
        self.swap.write_text('#!/bin/sh\nprintf "%%s\\n" "$@" > "%s"\n' % self.swap_calls, encoding='utf-8')
        # A real signed-looking app bundle, zipped the way scripts/build-bundle.sh does it.
        stage = self.tmp/'stage'; (stage/'Meeting OS.app'/'Contents'/'MacOS').mkdir(parents=True)
        (stage/'Meeting OS.app'/'Contents'/'MacOS'/'MeetingOS').write_text('#!/bin/sh\n', encoding='utf-8')
        self.zip = self.tmp/'Meeting-OS-1.2.72.zip'
        subprocess.run(['/usr/bin/ditto', '-c', '-k', '--keepParent', str(stage/'Meeting OS.app'), str(self.zip)],
                       check=True, capture_output=True)
        self.payload = self.zip.read_bytes()

    def release(self, **kw):
        r = Release(payload=self.payload, **kw); self.addCleanup(r.close); return r

    def status(self):
        return json.loads((self.data/'update-status.json').read_text(encoding='utf-8'))

    def run_worker(self, release):
        states = []
        real = updater.write_status

        def spy(data_dir, state, *a, **kw):
            states.append(state); return real(data_dir, state, *a, **kw)
        with patch.object(updater, 'write_status', spy):
            rc = updater.run_download(release.base, self.data, str(self.tmp/'Meeting OS.app'), 0,
                                      str(self.swap), from_version='1.2.71', cache=self.cache)
        return rc, states

    def test_the_happy_path_walks_downloading_verifying_extracting_swapping(self):
        rc, states = self.run_worker(self.release())
        self.assertEqual(rc, 0)
        self.assertEqual([s for i, s in enumerate(states) if i == 0 or s != states[i - 1]],
                         ['downloading', 'verifying', 'extracting', 'swapping'])
        final = self.status()
        self.assertEqual(final['state'], 'swapping')
        self.assertEqual((final['from'], final['to']), ('1.2.71', '1.2.72'))
        self.assertIn('time', final)
        # the swap script was handed <new.app> <target.app> <pid>; it is detached, so give it a moment
        for _ in range(100):
            if self.swap_calls.exists(): break
            time.sleep(0.05)
        args = self.swap_calls.read_text(encoding='utf-8').splitlines()
        self.assertTrue(args[0].endswith('Meeting OS.app'))
        self.assertEqual(args[1], str(self.tmp/'Meeting OS.app'))
        self.assertEqual(args[2], '0')

    def test_the_percentage_reaches_the_status_file(self):
        seen = []
        real = updater.write_status

        def spy(data_dir, state, *a, **kw):
            if 'percent' in kw: seen.append((state, kw['percent']))
            return real(data_dir, state, *a, **kw)
        with patch.object(updater, 'write_status', spy):
            updater.run_download(self.release().base, self.data, str(self.tmp/'Meeting OS.app'), 0,
                                 str(self.swap), from_version='1.2.71', cache=self.cache)
        downloading = [p for s, p in seen if s == 'downloading']
        self.assertEqual(downloading[0], 0)
        self.assertEqual(downloading[-1], 100)
        self.assertTrue(all(0 <= p <= 100 for _s, p in seen))

    def test_a_wrong_sha256_fails_and_throws_the_zip_away(self):
        rc, states = self.run_worker(self.release(sha='0' * 64))
        self.assertEqual(rc, 1)
        self.assertIn('verifying', states)
        self.assertNotIn('swapping', states)
        final = self.status()
        self.assertEqual(final['state'], 'failed')
        self.assertEqual(final['error'], updater.SHA_ERROR)
        self.assertEqual(final['message'], updater.SHA_ERROR)
        self.assertFalse((self.cache/'Meeting-OS-1.2.72.zip').exists())   # a poisoned zip must not be resumed
        self.assertFalse(self.swap_calls.exists())

    def test_an_interrupted_download_keeps_the_partial_zip_for_the_next_run(self):
        release = self.release()
        partial = self.cache/'Meeting-OS-1.2.72.zip'
        partial.write_bytes(self.payload[:200])
        release.close()   # the server is gone: the download fails mid-flight
        rc, _states = updater.run_download(release.base, self.data, str(self.tmp/'Meeting OS.app'), 0,
                                           str(self.swap), from_version='1.2.71', cache=self.cache), None
        self.assertEqual(rc, 1)
        self.assertEqual(self.status()['state'], 'failed')
        self.assertTrue(partial.exists())

    def test_a_finished_zip_from_an_earlier_run_is_not_downloaded_again(self):
        release = self.release()
        (self.cache/'Meeting-OS-1.2.72.zip').write_bytes(self.payload)
        rc, _ = self.run_worker(release)
        self.assertEqual(rc, 0)
        self.assertEqual(release.ranges, [])

    def test_a_lying_latest_json_is_refused_before_anything_is_downloaded(self):
        release = self.release()
        (release.dir/'latest.json').write_text(json.dumps(
            {'version': '1.2.72', 'file': '../../etc/passwd', 'sha256': '0' * 64, 'size': 1}), encoding='utf-8')
        rc, _ = self.run_worker(release)
        self.assertEqual(rc, 1)
        self.assertEqual(self.status()['state'], 'failed')
        self.assertEqual(list(self.cache.iterdir()), [])


class StartTests(unittest.TestCase):
    def test_start_spawns_a_detached_worker_with_the_app_path_and_pid_swift_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = runtime_json(tmp, download_base='http://127.0.0.1:1/x')
            (res/'swap-update.sh').write_text('#!/bin/sh\n', encoding='utf-8')
            data = Path(tmp)/'data'; data.mkdir()
            calls = []
            with patch.object(updater.subprocess, 'Popen', lambda cmd, **kw: calls.append((cmd, kw))):
                out = updater.start(res/'repo', data, {'app_path': '/Applications/Meeting OS.app', 'pid': 4242})
            self.assertEqual(out, {'started': True, 'bundled': True,
                                   'app': '/Applications/Meeting OS.app', 'pid': 4242})
            cmd, kw = calls[0]
            self.assertIn('--bundle-download', cmd)
            self.assertEqual(cmd[cmd.index('--app') + 1], '/Applications/Meeting OS.app')
            self.assertEqual(cmd[cmd.index('--pid') + 1], '4242')
            self.assertEqual(Path(cmd[cmd.index('--swap') + 1]), (res/'swap-update.sh').resolve())
            self.assertTrue(kw['start_new_session'])
            self.assertNotIn('OPENROUTER_API_KEY', kw['env'])
            # the card must not sit on "kontrol ediliyor" until the worker's first write
            self.assertEqual(json.loads((data/'update-status.json').read_text())['state'], 'downloading')

    def test_without_swift_the_worker_still_gets_the_running_bundle_and_the_apps_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = runtime_json(tmp, download_base='http://127.0.0.1:1/x')
            (res/'swap-update.sh').write_text('#!/bin/sh\n', encoding='utf-8')
            data = Path(tmp)/'data'; data.mkdir()
            calls = []
            with patch.object(updater.subprocess, 'Popen', lambda cmd, **kw: calls.append((cmd, kw))):
                out = updater.start(res/'repo', data)
            self.assertEqual(Path(out['app']), (Path(tmp)/'Meeting OS.app').resolve())
            self.assertEqual(out['pid'], os.getppid())   # the bridge's parent IS the app

    def test_the_repo_swap_script_is_used_when_the_bundle_has_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = runtime_json(tmp, download_base='http://127.0.0.1:1/x')
            rt = updater.bundle_runtime(res/'repo')
            self.assertEqual(updater.swap_script(rt, REPO), REPO/'scripts'/'swap-update.sh')
            self.assertTrue(updater.swap_script(rt, REPO).is_file())


class SwapScriptTests(unittest.TestCase):
    """scripts/swap-update.sh with a fake `open` on PATH — a dry run of the one step that can lose the app."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp/'home'; (self.home/'Library'/'Application Support'/'MeetingOS').mkdir(parents=True)
        self.bin = self.tmp/'bin'; self.bin.mkdir()
        self.opened = self.tmp/'opened.txt'
        (self.bin/'open').write_text('#!/bin/sh\nprintf "%%s\\n" "$@" >> "%s"\n' % self.opened, encoding='utf-8')
        (self.bin/'open').chmod(0o755)
        self.target = self.tmp/'Applications'/'Meeting OS.app'
        (self.target/'Contents').mkdir(parents=True)
        (self.target/'Contents'/'eski').write_text('eski', encoding='utf-8')
        self.new = self.tmp/'staging'/'Meeting OS.app'
        (self.new/'Contents').mkdir(parents=True)
        (self.new/'Contents'/'yeni').write_text('yeni', encoding='utf-8')

    def swap(self, pid='0', target=None):
        env = {**os.environ, 'HOME': str(self.home), 'PATH': '%s:%s' % (self.bin, os.environ['PATH'])}
        return subprocess.run(['/bin/sh', str(REPO/'scripts'/'swap-update.sh'), str(self.new),
                               str(target or self.target), pid], env=env, capture_output=True, text=True, timeout=90)

    def status(self):
        return json.loads((self.home/'Library/Application Support/MeetingOS/update-status.json').read_text())

    def test_the_new_app_takes_the_old_ones_place_and_is_reopened(self):
        r = self.swap()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.target/'Contents'/'yeni').is_file())
        self.assertFalse((self.target/'Contents'/'eski').is_file())
        self.assertTrue((Path(str(self.target) + '.previous')/'Contents'/'eski').is_file())
        self.assertFalse(self.new.exists())
        self.assertEqual(self.opened.read_text(encoding='utf-8').strip(), str(self.target))
        self.assertEqual(self.status()['state'], 'done')

    def test_an_older_previous_is_replaced_not_stacked(self):
        older = Path(str(self.target) + '.previous'); (older/'Contents').mkdir(parents=True)
        (older/'Contents'/'çok-eski').write_text('x', encoding='utf-8')
        self.assertEqual(self.swap().returncode, 0)
        self.assertFalse((older/'Contents'/'çok-eski').exists())
        self.assertTrue((older/'Contents'/'eski').is_file())

    def test_a_read_only_folder_is_refused_and_the_installed_app_is_untouched(self):
        parent = self.target.parent
        parent.chmod(0o555); self.addCleanup(parent.chmod, 0o755)
        r = self.swap()
        self.assertEqual(r.returncode, 1)
        self.assertTrue((self.target/'Contents'/'eski').is_file())
        self.assertEqual(self.status()['state'], 'failed')
        self.assertIn('yazılabilir değil', self.status()['message'])

    def test_a_missing_new_app_fails_before_the_installed_one_is_moved(self):
        shutil.rmtree(self.new)
        r = self.swap()
        self.assertEqual(r.returncode, 1)
        self.assertTrue((self.target/'Contents'/'eski').is_file())
        self.assertEqual(self.status()['state'], 'failed')

    def test_an_app_that_never_quits_is_never_swapped_underneath(self):
        proc = subprocess.Popen(['/bin/sh', '-c', 'sleep 120'])
        self.addCleanup(proc.wait); self.addCleanup(proc.kill)
        with patch.dict(os.environ, {}):
            env = {**os.environ, 'HOME': str(self.home), 'PATH': '%s:%s' % (self.bin, os.environ['PATH'])}
            r = subprocess.run(['/bin/sh', '-c',
                                'sed "s/-lt 60/-lt 2/" "%s" > "%s"; sh "%s" "%s" "%s" %d'
                                % (REPO/'scripts'/'swap-update.sh', self.tmp/'quick.sh', self.tmp/'quick.sh',
                                   self.new, self.target, proc.pid)],
                               env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertTrue((self.target/'Contents'/'eski').is_file())
        self.assertEqual(self.status()['state'], 'failed')
        self.assertIn('kapanmadı', self.status()['message'])


if __name__ == '__main__':
    unittest.main()
