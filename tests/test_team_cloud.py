"""The team knowledge base over a server, with nothing for a teammate to set up.

Two "Macs" here are two temp data folders with the same `openrouter.key` — which is what makes them one team —
talking to a fake sync server on a random port in this process. The server is the whole protocol from
docs/TEAM_CLOUD.md and nothing else: bearer auth, per-host ownership, an index, ETag/304. It is deliberately
dumb, because the real one is: every merge decision this app makes lives on the client.

Nothing in this file touches iCloud, the real data folder or the network beyond 127.0.0.1.
"""
import hashlib
import http.server
import json
import re
import tempfile
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from meeting_os import correction_memory as cm
from meeting_os import errors as E
from meeting_os import glossary, reports, team_cloud as TC, team_knowledge as tk
from meeting_os.store import Store
from meeting_os.types import Segment

ALLOWED = re.compile(r'^(?:(?:words|glossary|profiles|errors)/[A-Za-z0-9._-]{1,64}\.jsonl'
                     r'|reports/[A-Za-z0-9._-]{1,64}/[A-Za-z0-9._-]{1,120}\.json)$')
TOKEN = re.compile(r'^[0-9a-fA-F]{32,128}$')


def _owner(rel):
    parts = rel.split('/')
    return parts[1][:-6] if len(parts) == 2 else parts[1]


class _Handler(http.server.BaseHTTPRequestHandler):
    """`server/sync_server.py` as the client sees it. Files per team, per host; merging is the client's job."""

    def log_message(self, *args): pass

    def _route(self):
        path = self.path.split('?')[0]
        for prefix in ('/meetingos/v1/', '/v1/'):
            if path.startswith(prefix): return path[len(prefix):]
        return None

    def _team(self):
        header = self.headers.get('Authorization') or ''
        token = header[len('Bearer '):].strip() if header.startswith('Bearer ') else ''
        return hashlib.sha256(token.encode('utf-8')).hexdigest()[:32] if TOKEN.match(token) else None

    def _reply(self, code, body=b'', kind='application/json', etag=None):
        self.server.seen.append((self.command, self.path, code))
        self.send_response(code)
        self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(body)))
        if etag: self.send_header('ETag', f'"{etag}"')
        self.end_headers()
        if body: self.wfile.write(body)

    def _json(self, code, payload): self._reply(code, json.dumps(payload).encode('utf-8'))

    def _target(self, route):
        """(path on disk, relative path) for /v1/file/<path>, or None when the path is not allowlisted."""
        rel = route[len('file/'):]
        if not ALLOWED.match(rel): return None
        return self.server.root / self._team() / rel, rel

    def do_GET(self):
        route = self._route()
        if route is None: return self._json(404, {'error': 'yol'})
        if route == 'ping': return self._json(200, {'ok': True, 'version': '1', 'time': datetime.now(timezone.utc).isoformat()})
        team = self._team()
        if not team: return self._json(401, {'error': 'kimlik'})
        base = self.server.root / team
        if route == 'index':
            files = {}; hosts = set()
            for path in sorted(base.rglob('*')) if base.is_dir() else []:
                if not path.is_file(): continue
                rel = path.relative_to(base).as_posix(); blob = path.read_bytes()
                files[rel] = {'sha256': hashlib.sha256(blob).hexdigest(), 'size': len(blob),
                              'updated': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
                hosts.add(_owner(rel))
            return self._json(200, {'files': files, 'hosts': sorted(hosts)})
        if not route.startswith('file/'): return self._json(404, {'error': 'yol'})
        found = self._target(route)
        if not found: return self._json(403, {'error': 'yol'})
        path, _ = found
        if not path.is_file(): return self._json(404, {'error': 'yok'})
        blob = path.read_bytes(); etag = hashlib.sha256(blob).hexdigest()
        if (self.headers.get('If-None-Match') or '').strip('"') == etag: return self._reply(304, b'', etag=etag)
        return self._reply(200, blob, kind='application/octet-stream', etag=etag)

    def _owned(self, route):
        if not self._team(): self._json(401, {'error': 'kimlik'}); return None
        found = self._target(route or '')
        if not found: self._json(403, {'error': 'yol'}); return None
        path, rel = found
        if _owner(rel) != (self.headers.get('X-Meeting-OS-Host') or ''): self._json(403, {'error': 'sahiplik'}); return None
        return path

    def do_PUT(self):
        route = self._route()
        if route is None or not route.startswith('file/'): return self._json(404, {'error': 'yol'})
        length = self.headers.get('Content-Length')
        if length is None: return self._json(411, {'error': 'uzunluk'})
        body = self.rfile.read(int(length))
        path = self._owned(route)
        if path is None: return
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body)
        return self._json(200, {'sha256': hashlib.sha256(body).hexdigest(), 'size': len(body)})

    def do_DELETE(self):
        route = self._route()
        if route is None or not route.startswith('file/'): return self._json(404, {'error': 'yol'})
        path = self._owned(route)
        if path is None: return
        path.unlink(missing_ok=True)
        return self._json(200, {'deleted': True})


class CloudFixture(unittest.TestCase):
    KEY = 'sk-or-v1-ekip'

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.tmp = Path(self._tmp.name)
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        self.server.root = self.tmp / 'sunucu'; self.server.root.mkdir(); self.server.seen = []
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.stores = []
        # The hooks fire `sync_async`; the tests drive `sync` themselves so a background pass cannot race them.
        self.async_calls = []
        self._async = patch.object(TC, 'sync_async', side_effect=lambda data_dir: self.async_calls.append(str(data_dir)))
        self._async.start()

    def tearDown(self):
        self._async.stop()
        for store in self.stores: store.close()
        self.server.shutdown(); self.server.server_close()
        self._tmp.cleanup()

    def mac(self, name, key=None, url=None, **settings):
        """One Mac: its own data folder, its own database, the same team token as its colleagues."""
        data = self.tmp / name; data.mkdir()
        (data / 'openrouter.key').write_text((key or self.KEY) + '\n', encoding='utf-8')
        (data / 'vocabulary.txt').write_text('Jira\n', encoding='utf-8')
        reports.save_settings(data, {'team_url': self.url if url is None else url, **settings})
        store = Store(data / 'meeting-os.sqlite'); self.stores.append(store)
        mac = type('Mac', (), {})()
        mac.name = name; mac.data = data; mac.store = store
        mac.settings = lambda: reports.load_settings(data)
        mac.mirror = TC.mirror_dir(data)
        mac.host = lambda: self.hosted(name)
        mac.sync = lambda **kw: TC.sync(data, reports.load_settings(data), **kw)
        return mac

    @contextmanager
    def hosted(self, name):
        with patch.object(reports, 'host_name', return_value=name), patch.object(tk, 'host_name', return_value=name):
            yield

    def segment(self, store, mid, text):
        return store.add_segment(mid, Segment(0.0, 4.0, text, 'system', 'system:S1'))

    def report(self, mac, name, payload):
        """A diagnostic report where the app writes one: `report_root` already points into the mirror."""
        folder = reports.host_dir(mac.settings()); folder.mkdir(parents=True, exist_ok=True)
        return reports.publish(folder / name, json.dumps(payload, ensure_ascii=False))


class MirrorTests(CloudFixture):
    def test_the_mirror_is_the_team_folder_and_never_a_stored_setting(self):
        mac = self.mac('a')
        settings = mac.settings()
        self.assertEqual(settings['team_dir'], '')                                  # Ayarlar still shows "seçilmedi"
        self.assertEqual(settings['_mirror'], str(mac.data / 'team'))
        self.assertEqual(reports.team_dir(settings), mac.data / 'team')
        self.assertEqual(reports.report_root(settings), mac.data / 'team' / 'reports')
        with mac.host():
            self.assertEqual(reports.host_dir(settings), mac.data / 'team' / 'reports' / 'a')
            self.assertEqual(tk.shared_root(settings, mac.data), mac.data / 'team')
            self.assertEqual(tk.words_path(settings, mac.data), mac.data / 'team' / 'team-words.jsonl')
        self.assertEqual(glossary.team_path(mac.data), mac.data / 'team' / 'glossary.jsonl')
        # …and it is derived every time, never written: settings.json is what a teammate's Mac would read.
        saved = reports.save_settings(mac.data, {'share_text': True})
        self.assertNotIn('_mirror', saved)
        self.assertNotIn('_mirror', json.loads((mac.data / 'settings.json').read_text(encoding='utf-8')))
        self.assertEqual(reports.load_settings(mac.data)['_mirror'], str(mac.data / 'team'))

    def test_a_picked_team_folder_still_wins(self):
        folder = self.tmp / 'nas'; folder.mkdir()
        mac = self.mac('a', team_dir=str(folder))
        settings = mac.settings()
        self.assertNotIn('_mirror', settings)
        self.assertEqual(reports.team_dir(settings), folder)
        self.assertFalse(TC.configured(settings, mac.data))
        self.assertEqual(mac.sync()['error'], 'unconfigured')
        self.assertFalse((mac.data / 'team').exists())

    def test_a_data_folder_with_no_key_has_no_cloud_at_all(self):
        data = self.tmp / 'anahtarsız'; data.mkdir()
        settings = reports.load_settings(data)
        self.assertNotIn('_mirror', settings)
        self.assertIsNone(TC.token(data))
        self.assertFalse(TC.configured(settings, data))
        self.assertIsNone(reports.team_dir(settings))
        self.assertEqual(TC.sync(data)['error'], 'unconfigured')


class TokenTests(CloudFixture):
    def test_the_key_is_the_team_and_team_token_wins(self):
        a = self.mac('a'); b = self.mac('b'); other = self.mac('c', key='sk-or-v1-baska')
        self.assertEqual(TC.token(a.data), TC.token(b.data))                         # same key → same team, nobody chose
        self.assertEqual(TC.token(a.data), hashlib.sha256(b'meetingos-team-v1:' + self.KEY.encode()).hexdigest())
        self.assertNotEqual(TC.token(a.data), TC.token(other.data))
        self.assertEqual(TC.team_id_short(TC.token(a.data)), hashlib.sha256(TC.token(a.data).encode()).hexdigest()[:6])
        joined = TC.join(other.data, TC.token(a.data).upper())
        self.assertEqual(TC.token(other.data), TC.token(a.data))                     # the file beats the derived one
        self.assertEqual((other.data / 'team.token').stat().st_mode & 0o777, 0o600)
        self.assertEqual(joined['team_id_short'], TC.team_id_short(TC.token(a.data)))
        for junk in ('', 'değil', 'ab', 'f' * 200):
            with self.assertRaises(ValueError): TC.join(other.data, junk)
        line = TC.invite_line(a.data)
        self.assertIn(f"MEETING_OS_TEAM={TC.token(a.data)}", line['line'])
        self.assertIn('install.sh', line['line'])
        self.assertEqual(TC.invite_line(self.tmp)['token'], '')                      # no key here: nothing to invite with

    def test_a_junk_token_file_falls_back_to_the_key(self):
        mac = self.mac('a'); (mac.data / 'team.token').write_text('elle yazılmış\n', encoding='utf-8')
        self.assertEqual(TC.token(mac.data), hashlib.sha256(b'meetingos-team-v1:' + self.KEY.encode()).hexdigest())


class RoundTripTests(CloudFixture):
    VECTOR = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.4, 0.2]

    def test_a_word_a_voice_and_a_report_reach_the_other_mac(self):
        a = self.mac('a'); b = self.mac('b')
        with a.host():
            mid = a.store.create_meeting('a'); self.segment(a.store, mid, 'Trendyoll ile görüştük.')
            cm.teach(a.store, mid, 'Trendyoll', 'Trendyol', a.data)
            a.store.enroll('Ayşe', self.VECTOR, 'emb-1', 12.0, 'toplanti-1:5')
            tk.publish_profiles(a.store, a.settings(), a.data)
            (a.data / 'glossary.jsonl').write_text(json.dumps({'term': 'Splendo', 'category': 'ürün'}) + '\n', encoding='utf-8')
            self.report(a, '2026-09-10_x.json', {'meeting': 'x', 'host': 'a', 'ok': True})
            pushed = a.sync()
        self.assertEqual(pushed['error'] if 'error' in pushed else None, None)
        self.assertEqual(sorted(p.relative_to(self.server.root).as_posix().split('/', 1)[1]
                                for p in self.server.root.rglob('*') if p.is_file()),
                         ['glossary/a.jsonl', 'profiles/a.jsonl', 'reports/a/2026-09-10_x.json', 'words/a.jsonl'])
        self.assertEqual(self.async_calls, [str(a.data)])   # the teach hook asked for a background pass, not a wait
        with b.host():
            got = b.sync()
            self.assertEqual((got['pushed'], got['hosts']), (0, ['a']))
            self.assertGreaterEqual(got['pulled'], 4)
            tk.pull_words(b.store, b.settings(), b.data)
            tk.pull_profiles(b.store, b.settings(), b.data)
            rule = cm.word_rules(b.store)[0]
            self.assertEqual((rule['source'], rule['host'], rule['replacement']), ('team', 'a', 'Trendyol'))
            other = b.create_meeting = b.store.create_meeting('b'); self.segment(b.store, other, 'Trendyoll güzel.')
            self.assertEqual(cm.apply_rules(b.store, other, data_dir=b.data)['fixes'], 1)
            self.assertEqual([(p['name'], p['samples']) for p in b.store.profiles()], [('Ayşe', 1)])
            self.assertIn('Splendo', [e['term'] for e in glossary.load(b.data)])
            self.assertEqual(json.loads((b.mirror / 'reports' / 'a' / '2026-09-10_x.json').read_text(encoding='utf-8'))['meeting'], 'x')
            self.assertEqual(reports.summarize(reports.report_root(b.settings()))['hosts']['a']['reports'], 1)
            # Nothing changed since: a second pass uploads nothing and downloads nothing.
            self.assertEqual({k: v for k, v in b.sync().items() if k in ('pushed', 'pulled')}, {'pushed': 0, 'pulled': 0})
        with a.host():
            self.assertEqual({k: v for k, v in a.sync().items() if k in ('pushed', 'pulled')}, {'pushed': 0, 'pulled': 0})
            self.assertEqual((a.mirror / 'profiles' / 'b.jsonl').exists(), False)   # b published nothing of its own

    def test_a_word_a_teammate_forgets_disappears_here_too(self):
        a = self.mac('a'); b = self.mac('b')
        with a.host():
            mid = a.store.create_meeting('a'); self.segment(a.store, mid, 'Trendyoll ve Splendoo.')
            cm.teach(a.store, mid, 'Trendyoll', 'Trendyol', a.data)
            cm.teach(a.store, mid, 'Splendoo', 'Splendo', a.data)
            a.sync()
        with b.host():
            b.sync(); tk.pull_words(b.store, b.settings(), b.data)
            self.assertEqual(len(tk.team_rules(b.store)), 2)
        with a.host():
            cm.forget(a.store, 'Trendyoll', a.data); a.sync()
        with b.host():
            b.sync(); tk.pull_words(b.store, b.settings(), b.data)
            self.assertEqual([r['original'] for r in tk.team_rules(b.store)], ['Splendoo'])
            self.assertEqual([e['original'] for e in tk.read_words(b.mirror / tk.WORDS_FILE)], ['Splendoo'])

    def test_a_deleted_meetings_report_leaves_the_team(self):
        a = self.mac('a'); b = self.mac('b')
        with a.host():
            path = self.report(a, '2026-09-10_m1.json', {'meeting': 'm1'})
            self.report(a, '2026-09-10_m2.json', {'meeting': 'm2'})
            a.sync()
        with b.host():
            b.sync()
            self.assertEqual(sorted(p.name for p in (b.mirror / 'reports' / 'a').glob('*.json')),
                             ['2026-09-10_m1.json', '2026-09-10_m2.json'])
        with a.host():
            path.unlink()   # the meeting was deleted; `remove_meeting_report` does exactly this
            self.assertEqual(a.sync()['deleted'], 1)
        self.assertFalse((self.server.root / hashlib.sha256(TC.token(a.data).encode()).hexdigest()[:32]
                          / 'reports/a/2026-09-10_m1.json').exists())
        with b.host():
            self.assertEqual(b.sync()['removed'], 1)
            self.assertEqual([p.name for p in (b.mirror / 'reports' / 'a').glob('*.json')], ['2026-09-10_m2.json'])

    def test_a_term_a_teammate_removed_is_dropped_from_the_mirror(self):
        a = self.mac('a'); b = self.mac('b')
        terms = [{'term': 'Splendo', 'category': 'ürün'}, {'term': 'Qatya', 'category': 'proje'}]
        with a.host():
            (a.data / 'glossary.jsonl').write_text('\n'.join(json.dumps(t) for t in terms) + '\n', encoding='utf-8')
            a.sync()
        with b.host():
            b.sync()
            self.assertEqual([e['term'] for e in glossary.load(b.data) if e['term'] in ('Splendo', 'Qatya')], ['Splendo', 'Qatya'])
        with a.host():
            (a.data / 'glossary.jsonl').write_text(json.dumps(terms[0]) + '\n', encoding='utf-8'); a.sync()
        with b.host():
            b.sync()
            self.assertEqual([e['term'] for e in glossary.load(b.data) if e['term'] in ('Splendo', 'Qatya')], ['Splendo'])


class ResilienceTests(CloudFixture):
    def test_a_server_that_is_down_is_silent_and_costs_nothing(self):
        mac = self.mac('a', url='http://127.0.0.1:9')   # discard port: refused at once, no DNS, no waiting
        with mac.host():
            mid = mac.store.create_meeting('a'); self.segment(mac.store, mid, 'Trendyoll.')
            cm.teach(mac.store, mid, 'Trendyoll', 'Trendyol', mac.data)
            words = (mac.mirror / tk.WORDS_FILE).read_text(encoding='utf-8')
            result = mac.sync()
            self.assertEqual((result['pushed'], result['pulled']), (0, 0))
            self.assertTrue(result['error'])
            self.assertLessEqual(len(result['error']), 120)
            self.assertEqual((mac.mirror / tk.WORDS_FILE).read_text(encoding='utf-8'), words)   # local learning untouched
            self.assertEqual(cm.word_rules(mac.store)[0]['replacement'], 'Trendyol')
            state = TC.status(mac.data)
            self.assertEqual((state['last_ok'], bool(state['last_error'])), (None, True))
            self.assertEqual(state['team_id_short'], TC.team_id_short(TC.token(mac.data)))
            for _ in range(3): mac.sync()
        journal = [e for e in E.entries(mac.data) if e['kind'] == 'cloud']
        self.assertEqual(len(journal), 1)                                  # one line an hour, not one line a pass
        self.assertEqual(journal[0]['context'], {'where': 'team_cloud'})
        stamp = json.loads((mac.data / TC.STATE_FILE).read_text(encoding='utf-8'))['error_recorded']
        self.assertTrue(stamp)
        self.assertEqual((mac.data / TC.STATE_FILE).stat().st_mode & 0o777, 0o600)

    def test_the_budget_stops_the_pass_without_losing_what_was_written(self):
        mac = self.mac('a')
        with mac.host():
            mid = mac.store.create_meeting('a'); self.segment(mac.store, mid, 'Trendyoll.')
            cm.teach(mac.store, mid, 'Trendyoll', 'Trendyol', mac.data)
            self.report(mac, '2026-09-10_x.json', {'meeting': 'x'})
            stopped = mac.sync(budget=0)
            self.assertEqual((stopped['error'], stopped['pushed']), ('budget', 0))
            self.assertEqual(TC.status(mac.data)['last_ok'], None)
            done = mac.sync()
            self.assertNotIn('error', done)
            self.assertEqual(done['pushed'], 2)
            self.assertTrue(TC.status(mac.data)['last_ok'])
            # A pass with nothing left to do does not report a budget error even with no time at all.
            self.assertNotIn('error', mac.sync(budget=0))

    def test_the_error_journal_travels_only_when_reports_are_shared(self):
        a = self.mac('a'); quiet = self.mac('q', share_reports=False); b = self.mac('b')
        E.record('cloud', 'bir şey oldu', data_dir=a.data); E.record('job', 'başka şey', data_dir=quiet.data)
        with a.host():
            self.report(a, '2026-09-10_x.json', {'meeting': 'x'}); a.sync()
        with self.hosted('q'):
            self.report(quiet, '2026-09-10_q.json', {'meeting': 'q'}); quiet.sync()
        remote = sorted(p.relative_to(self.server.root).as_posix().split('/', 1)[1]
                        for p in self.server.root.rglob('*') if p.is_file())
        self.assertIn('errors/a.jsonl', remote)
        self.assertIn('reports/a/2026-09-10_x.json', remote)
        self.assertNotIn('errors/q.jsonl', remote)          # share_reports off: no report and no journal
        self.assertNotIn('reports/q/2026-09-10_q.json', remote)
        with b.host():
            b.sync()
            self.assertFalse(list(b.mirror.rglob('errors*')))   # a teammate's error journal is never downloaded
            self.assertTrue((b.mirror / 'reports' / 'a' / '2026-09-10_x.json').is_file())

    def test_hooks_never_wait_for_the_network(self):
        """Naming a voice and teaching a word run on the fast bridge, behind a ten-second watchdog."""
        from meeting_os import desktop
        mac = self.mac('a')
        with mac.host():
            mid = mac.store.create_meeting('a'); self.segment(mac.store, mid, 'Trendyoll.')
            with patch.object(TC, 'sync', side_effect=AssertionError('the fast bridge must not sync inline')):
                cm.teach(mac.store, mid, 'Trendyoll', 'Trendyol', mac.data)
                desktop.share_profiles(mac.store, mac.data / 'meeting-os.sqlite')
        self.assertEqual(self.async_calls, [str(mac.data), str(mac.data)])


class ProtocolTests(CloudFixture):
    def test_an_unchanged_file_answers_304_and_is_not_written_again(self):
        """The index already tells the client what changed; `If-None-Match` is the second net under it, so a
        server that reports a stale index still cannot make this Mac rewrite a file it already has."""
        mac = self.mac('a')
        token = TC.token(mac.data)
        http = TC._Http(self.url, token, 'a', __import__('time').monotonic() + 10)
        http.put('words/a.jsonl', b'{"original":"x","replacement":"y","host":"a"}\n')
        digest = __import__('hashlib').sha256(b'{"original":"x","replacement":"y","host":"a"}\n').hexdigest()
        self.assertIsNone(http.get('words/a.jsonl', etag=digest))          # 304: nothing to write
        self.assertTrue(http.get('words/a.jsonl', etag='0' * 64))          # a real change still arrives
        self.assertIsNone(http.get('words/yok.jsonl'))                     # 404 is not an error either
        self.assertIn(('GET', '/v1/file/words/a.jsonl', 304), self.server.seen)
        self.assertEqual(TC._Http(self.url, 'f' * 32, 'a', __import__('time').monotonic() + 10).index(), ({}, []))   # another team, not an error: an empty index
        with self.assertRaises(Exception): TC._Http(self.url, 'yok', 'a', __import__('time').monotonic() + 10).index()   # no usable token: 401, and `sync` turns it into a state line
        bad = TC._Http(self.url, token, 'a', __import__('time').monotonic() + 10)
        with self.assertRaises(Exception): bad.put('words/b.jsonl', b'x')  # a teammate's file: 403, never silently written
        self.assertFalse((self.server.root / __import__('hashlib').sha256(token.encode()).hexdigest()[:32] / 'words/b.jsonl').exists())


class SeedTests(CloudFixture):
    def test_the_first_pass_carries_over_what_the_folder_era_left_on_this_mac(self):
        """A Mac that has been using iCloud since 1.2.63 must not start the cloud with an empty knowledge base.
        Only its OWN files, only on the first pass, only read — and only for the real data folder, which is why
        every path here is a temp directory standing in for iCloud."""
        mac = self.mac('a')
        icloud = self.tmp / 'icloud'; shared = icloud / 'MeetingOS-Shared'; folder = icloud / 'MeetingOS-Reports'
        (shared / 'profiles').mkdir(parents=True); (folder / 'a').mkdir(parents=True)
        (shared / 'profiles' / 'a.jsonl').write_text(json.dumps(
            {'name': 'Ayşe', 'model': 'emb-1', 'vector': [0.1] * 12, 'duration': 12.0, 'host': 'a'}) + '\n', encoding='utf-8')
        (shared / 'team-words.jsonl').write_text('\n'.join(json.dumps(e) for e in [
            {'original': 'Trendyoll', 'replacement': 'Trendyol', 'host': 'a'},
            {'original': 'Splendoo', 'replacement': 'Splendo', 'host': 'b'}]) + '\n', encoding='utf-8')
        (folder / 'a' / 'heartbeat.json').write_text(json.dumps({'host': 'a', 'meetings': 3}), encoding='utf-8')
        with mac.host(), patch.object(TC, 'ICLOUD', icloud), patch.object(TC, 'SHARED_DIR', shared), \
             patch.object(TC, 'ICLOUD_REPORTS', folder), patch.object(TC, '_is_real', return_value=True):
            result = mac.sync()
        self.assertEqual([e['original'] for e in tk.read_words(mac.mirror / tk.WORDS_FILE)], ['Trendyoll'])   # own lines only
        self.assertEqual(len(tk.read_profiles(mac.mirror / 'profiles' / 'a.jsonl')), 1)
        self.assertEqual(json.loads((mac.mirror / 'reports' / 'a' / 'heartbeat.json').read_text(encoding='utf-8'))['meetings'], 3)
        self.assertEqual(result['pushed'], 3)
        with mac.host():   # …and only once: a mirror that already has files is never re-seeded
            (mac.mirror / 'reports' / 'a' / 'heartbeat.json').unlink()
            mac.sync()
        self.assertFalse((mac.mirror / 'reports' / 'a' / 'heartbeat.json').exists())


class HeartbeatTests(CloudFixture):
    def test_the_heartbeat_carries_the_cloud_state(self):
        mac = self.mac('a')
        with mac.host():
            mac.sync()
            beat = reports._team_cloud(mac.data)
        self.assertEqual(sorted(beat), ['hosts', 'last_error', 'last_ok'])
        self.assertTrue(beat['last_ok']); self.assertIsNone(beat['last_error'])

    def test_setup_status_calls_the_mirror_a_cloud_and_not_a_picked_folder(self):
        from meeting_os.desktop import dispatch
        mac = self.mac('a')
        with mac.host(), patch('meeting_os.updater.check', return_value={}):
            answer = dispatch({'action': 'setup_status'}, mac.data / 'meeting-os.sqlite')
        self.assertEqual(answer['team_root_kind'], 'cloud')
        self.assertEqual(answer['team_root'], str(mac.mirror))
        self.assertEqual(answer['team_cloud']['configured'], True)
        self.assertEqual(answer['team_cloud']['url'], self.url)
        self.assertIn('hosts', answer['team_cloud'])


if __name__ == '__main__':
    unittest.main()
