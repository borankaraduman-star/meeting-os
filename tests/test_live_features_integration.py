"""The three live features together (docs/CANLI_DURUM_ONIZLEME_NOTLAR.md): recording session state, the opt-in cloud
draft and the user's notes, joined through live.record, the bridge and the final pass.

Everything is synthetic: the fake helper of test_live (a Python script, no ScreenCaptureKit), a fake preview adapter
that never opens a socket, a fake OpenRouter client for finalize_capture, and tempfile folders. No real audio, no real
STT call, no real data folder."""
import contextlib
import hashlib
import json
import os
import signal
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from meeting_os import notes as N
from meeting_os import preview_transcription as PT
from meeting_os.cloud_finalize import finalize_capture
from meeting_os.desktop import capture_state, dispatch
from meeting_os.live import record
from meeting_os.openrouter import OpenRouterError
from meeting_os.store import Store

try: from test_live import FAKE_HELPER          # discover -s tests puts tests/ on sys.path
except ImportError: from tests.test_live import FAKE_HELPER


class FakeAdapter:
    """The preview provider: answers with the chunk's file name, counts calls, never touches a network."""
    def __init__(self, text=None):
        self.calls = []; self.text = text
    def transcribe(self, path, source, start, end, cancel):
        self.calls.append((source, start, Path(path).name))
        return {'text': self.text(source, start) if self.text else Path(path).name, 'status': 'final', 'usage': {'cost': 0.0001}}


class FakeClient:
    """finalize_capture's OpenRouter: the final text differs from the draft ("proje A" → "proje B")."""
    def __init__(self, fail_at=None):
        self.calls = []; self.fail_at = fail_at
    def transcribe(self, audio, fmt, *, model, consent, diarize=False, timeout=90, **kw):
        self.calls.append({'bytes': len(audio), 'diarize': diarize})
        if self.fail_at == len(self.calls): raise OpenRouterError('network')
        return {'text': 'Proje B için deneme cuma yapılacak.', 'usage': {'seconds': 12, 'cost': .0003}}


def until(check, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check(): return True
        time.sleep(.02)
    return False


def stop_when(check, timeout=10):
    """A pipeline_factory that only delivers the recorder's own SIGINT handler once `check()` holds (or the
    timeout passes, so a broken test fails instead of hanging). Returns no pipeline: record() then has none."""
    def factory():
        def wait():
            until(check, timeout); time.sleep(.05)
            handler = signal.getsignal(signal.SIGINT)
            if callable(handler): handler(signal.SIGINT, None)
        threading.Thread(target=wait, daemon=True).start()
    return factory


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.root = Path(self._tmp.name)
        self.db = self.root / 'meeting-os.sqlite'; self.store = Store(self.db)
        self.workers = []
    def tearDown(self):
        for w in self.workers:
            with contextlib.suppress(Exception): w.stop(.2)
        self.store.close(); self._tmp.cleanup()

    def fake_helper(self, plan):
        (self.root / 'plan.json').write_text(json.dumps(plan))
        p = self.root / 'fake-helper'; p.write_text(FAKE_HELPER); p.chmod(0o700)
        return p

    def quiet_helper(self, ready):
        """A helper that is up (its SIGINT handler installed) but has not written a single line yet."""
        p = self.root / 'quiet-helper'
        p.write_text('#!/usr/bin/env python3\nimport signal,sys,time\nfrom pathlib import Path\n'
                     'signal.signal(signal.SIGINT,lambda *a: sys.exit(0))\n'
                     f'Path({str(ready)!r}).write_text("ready")\ntime.sleep(20)\n')
        p.chmod(0o700); return p

    def worker(self, mid, capture, adapter, **kw):
        kw.setdefault('upload_allowed', True); kw.setdefault('policy', PT.PreviewPolicy(min_free_bytes=0))
        w = PT.PreviewWorker(self.db, mid, capture, lambda: adapter, **kw); self.workers.append(w); return w

    def drafts(self, mid=None):
        with contextlib.closing(PT.connect(self.db)) as c:
            if mid is not None: return PT.previews(c, mid)
            return [dict(r) for r in c.execute('SELECT * FROM transcript_previews ORDER BY span_id')]

    def has_table(self, name):
        with contextlib.closing(sqlite3.connect(self.db)) as c:
            return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

    def meta(self, mid):
        return json.loads(self.store.db.execute('SELECT metadata FROM meetings WHERE id=?', (mid,)).fetchone()[0])

    def status(self, mid):
        return self.store.db.execute('SELECT status FROM meetings WHERE id=?', (mid,)).fetchone()[0]

    def capture_folder(self, name, seconds=12):
        """A finished two-source capture: a 220 Hz mic and a 440 Hz system tone, one closed chunk each, in both the
        helper journal (capture-native.jsonl) and the recorder journal the preview reads back (events.jsonl)."""
        d = self.root / 'recordings' / name; d.mkdir(parents=True)
        t = np.arange(16000 * seconds) / 16000; lines = []
        for source, freq in (('mic', 220), ('system', 440)):
            path = d / f'{source}-000000.wav'
            sf.write(path, (0.3 * np.sin(2 * np.pi * freq * t)).astype('float32'), 16000, subtype='FLOAT')
            lines.append({'event': 'chunk', 'source': source, 'start': 0.0, 'duration': float(seconds), 'path': str(path), 'sample_rate': 16000, 'index': 0})
        for journal in ('capture-native.jsonl', 'events.jsonl'): (d / journal).write_text(''.join(json.dumps(e) + '\n' for e in lines))
        return d, lines


class RelaunchKeepsStateAndDraft(Base):
    """A preview-enabled recording whose helper dies once and is relaunched; the first helper also wrote one chunk
    line stamped with another session (FAKE_HELPER `foreign`), at the same span the new helper then records."""

    def test_a_late_line_of_another_session_or_launch_moves_neither_capture_state_nor_the_draft(self):
        binary = self.fake_helper({'chunks': 1, 'exit': 3, 'exit_runs': 1, 'chunks_after': 1, 'foreign': True, 'sleep': 30})
        adapter = FakeAdapter(); cap = self.root / 'capture'
        def factory(directory, mid, session=None):
            return self.worker(mid, directory, adapter, session=session).start()
        def both_drafted():
            if not (cap / 'relaunched').exists(): return False
            return {r['span_id'] for r in self.drafts() if r['status'] == 'final'} >= {'mic:0.000', 'mic:24.000'}
        with patch.dict(os.environ, {'FAKE_PLAN': str(self.root / 'plan.json')}), \
             patch('meeting_os.live.RELAUNCH_MIN_UPTIME_SECONDS', 0), patch('meeting_os.live.RELAUNCH_WAIT_SECONDS', .01):
            mid = record(binary, cap, 600, 12, store=self.store, pipeline_factory=stop_when(both_drafted), preview_factory=factory)
        self.assertEqual(self.status(mid), 'provisional')
        meta = self.meta(mid); session = meta['capture_session']
        argv = [json.loads((cap / f'argv-{n}.json').read_text()) for n in (1, 2)]
        self.assertEqual([(a[a.index('--session') + 1], a[a.index('--launch') + 1]) for a in argv], [(session, '1'), (session, '2')])

        # The relaunch offset follows every chunk line the helper printed (live.py: audio on disk is never withheld
        # because of a stamp), so the new helper continues at 24 s.
        self.assertEqual([e['start_offset'] for e in map(json.loads, (cap / 'events.jsonl').read_text().splitlines()) if e.get('event') == 'relaunch'], [24.0])
        # The draft: one row per chunk of THIS session. The foreign line's 12 s chunk gets none (it would have been a
        # 'failed' row for a file that is not there, or a stranger's text under this meeting).
        rows = {r['span_id']: (r['status'], r['text']) for r in self.drafts(mid)}
        self.assertEqual(rows, {'mic:0.000': ('final', 'mic-000000.wav'), 'mic:24.000': ('final', 'mic-000002.wav')})
        self.assertNotIn('mic-foreign.wav', [c[2] for c in adapter.calls])
        self.assertEqual(self.workers[0].status()['state'], 'stopped')
        # A worker reading the journal back (cursor path) sees the same two chunks, so seq and journal index agree.
        again = PT.PreviewWorker(self.db, 'yeniden-okuma', cap, lambda: adapter, session=session)
        self.assertEqual([Path(e['path']).name for e in again._journal_chunks()], ['mic-000000.wav', 'mic-000002.wav'])

        before = capture_state(meta)
        self.assertEqual((before['session'], before['relaunches'], before['sources']), (session, 1, {'mic': 36.0}))
        # Late lines after the fact: another session announcing itself and its chunk, and the replaced launch 1.
        with (cap / 'capture-native.jsonl').open('a') as f:
            for e in ({'event': 'started', 'session': 'baska-oturum', 'launch': 9, 'schema': 2, 'epoch': 0},
                      {'event': 'first_buffer', 'session': 'baska-oturum', 'launch': 9, 'source': 'system', 'epoch': 0, 'seq': 1, 'silent': False},
                      {'event': 'chunk', 'session': 'baska-oturum', 'launch': 9, 'source': 'system', 'path': str(cap / 'x.wav'), 'start': 100.0, 'duration': 12.0},
                      {'event': 'channel_flow', 'session': session, 'launch': 1, 'source': 'mic', 'state': 'stalled', 'epoch': 0, 'seq': 9},
                      {'event': 'error', 'session': session, 'launch': 1, 'message': 'eski yardımcı'},
                      {'event': 'stopped', 'session': session, 'launch': 1}):
                f.write(json.dumps(e) + '\n')
        after = capture_state(meta)
        for key in ('state', 'seconds', 'sources', 'schema', 'session', 'session_state', 'relaunches', 'restarts'):
            self.assertEqual(after.get(key), before.get(key), key)
        self.assertEqual({k: v['state'] for k, v in after['channels'].items()}, {k: v['state'] for k, v in before['channels'].items()})

    def test_the_worker_drops_a_replaced_launchs_late_chunk_in_offer_and_in_read_back_alike(self):
        cap = self.root / 'cap'; cap.mkdir(); mid = self.store.create_meeting('t'); adapter = FakeAdapter()
        lines = [{'event': 'chunk', 'source': 'mic', 'path': str(cap / f'{n}.wav'), 'start': s, 'duration': 12.0, 'session': 'S', 'launch': l}
                 for n, s, l in (('a', 0.0, 1), ('b', 12.0, 2), ('late', 24.0, 1), ('c', 24.0, 2), ('other', 36.0, 2))]
        lines[-1]['session'] = 'T'
        w = self.worker(mid, cap, adapter, session='S', upload_allowed=False)
        offered = [w.offer(e) for e in lines]
        self.assertEqual(offered, [True, True, False, True, False])
        (cap / 'events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in lines))
        reread = PT.PreviewWorker(self.db, mid, cap, lambda: adapter, session='S')
        self.assertEqual([Path(e['path']).stem for e in reread._journal_chunks()], ['a', 'b', 'c'])
        self.assertEqual(adapter.calls, [])   # no upload permission: never asked


class DefaultRecordingSendsNothing(Base):
    def test_default_cli_recording_builds_no_adapter_and_makes_zero_calls(self):
        from meeting_os import cli
        cap = self.root / 'capture'
        args = cli.parser().parse_args(['record', str(cap)])
        self.assertEqual((args.cloud_preview, args.allow_preview_upload, args.preview_model), (False, False, None))
        built = []
        factory = PT.worker_factory(cloud_preview=args.cloud_preview, allow_upload=args.allow_preview_upload, model=args.preview_model,
                                    db_path=self.db, adapter_factory=lambda: built.append(1) or FakeAdapter())
        self.assertIsNone(factory)
        binary = self.fake_helper({'chunks': 2, 'sleep': 30})
        chunks = lambda: (cap / 'events.jsonl').exists() and (cap / 'events.jsonl').read_text().count('"chunk"') >= 2
        with patch.dict(os.environ, {'FAKE_PLAN': str(self.root / 'plan.json')}), \
             patch.object(PT, 'OpenRouterPreviewAdapter', side_effect=AssertionError('adapter built')), \
             patch('meeting_os.openrouter.OpenRouterClient', side_effect=AssertionError('client built')):
            mid = record(binary, cap, 600, 12, store=self.store, pipeline_factory=stop_when(chunks), preview_factory=factory)
        self.assertEqual((built, self.status(mid)), ([], 'provisional'))
        self.assertFalse(self.has_table('transcript_previews'))   # lazy: a default recording leaves no draft table behind
        reply = dispatch({'action': 'transcript_previews', 'meeting': mid}, db=self.db)
        self.assertEqual((reply['state'], reply['status'], reply['previews']), ('off', None, []))

    def test_asking_for_the_preview_without_upload_permission_is_off_and_still_calls_nothing(self):
        cap = self.root / 'capture'; adapter = FakeAdapter(); built = []
        factory = PT.worker_factory(cloud_preview=True, allow_upload=False, db_path=self.db,
                                    adapter_factory=lambda: built.append(1) or adapter, policy=PT.PreviewPolicy(min_free_bytes=0))
        binary = self.fake_helper({'chunks': 2, 'sleep': 30})
        chunks = lambda: (cap / 'events.jsonl').exists() and (cap / 'events.jsonl').read_text().count('"chunk"') >= 2
        with patch.dict(os.environ, {'FAKE_PLAN': str(self.root / 'plan.json')}):
            mid = record(binary, cap, 600, 12, store=self.store, pipeline_factory=stop_when(chunks), preview_factory=factory)
        self.assertEqual((built, adapter.calls, self.drafts(mid)), ([], [], []))
        reply = dispatch({'action': 'transcript_previews', 'meeting': mid}, db=self.db)
        self.assertEqual((reply['state'], reply['reason']), ('disabled', 'upload_not_allowed'))
        self.assertTrue(all((cap / f'mic-{n:06d}.wav').exists() for n in (0, 1)))   # the audio is untouched either way


class NoteAnchoredToADraftSurvivesTheFinalPass(Base):
    def test_note_anchor_keeps_its_audio_range_and_the_final_text_covers_the_draft(self):
        cap, lines = self.capture_folder('3F0C2A9E-1111-4222-8333-944455556666')
        key = cap.name
        # Typed while preparing, before the meeting row exists: filed under the recording folder's UUID.
        first = dispatch({'action': 'note_save', 'pending_key': key, 'base_revision': 0, 'text': 'Karar: deneme cuma', 'anchors': []}, self.db)
        self.assertEqual(first['revision'], 1)
        mid = self.store.create_meeting('Plan', {'capture_dir': str(cap), 'provisional': True, 'cloud_intent': 'capture'})
        adapter = FakeAdapter(text=lambda source, start: 'proje A için deneme cuma' if source == 'system' else 'merhaba')
        w = self.worker(mid, cap, adapter).start()
        for e in lines: w.offer(e)
        self.assertTrue(until(lambda: len([r for r in self.drafts(mid) if r['status'] == 'final']) == 2))
        w.stop(1)
        draft = next(r for r in self.drafts(mid) if r['source'] == 'system')
        # "Bu ana bağla" while the draft is on screen: the anchor is the draft's SOURCE AUDIO time, not the row.
        anchor = {'id': 'a1', 'source': draft['source'], 'start': draft['audio_start'] + 2.0, 'end': draft['audio_start'] + 6.0}
        text = 'Karar: deneme cuma\n  • proje A taslakta böyle duyuldu  \n'
        saved = dispatch({'action': 'note_save', 'pending_key': key, 'base_revision': 1, 'text': text, 'anchors': [anchor]}, self.db)
        self.assertEqual(saved['revision'], 2)
        self.assertEqual(dispatch({'action': 'note_claim', 'pending_key': key, 'meeting': mid}, self.db), {'claimed': True, 'revision': 2})

        self.store.status(mid, 'incomplete')
        finalize_capture(self.store, mid, self.root, consent=True, model='openai/gpt-transcribe', client=FakeClient())
        self.assertEqual(self.status(mid), 'complete')
        finals = [r for r in self.store.segments(mid) if r['source'] == 'system']
        self.assertTrue(finals and all('Proje B' in r['text'] for r in finals))
        self.assertFalse(any('proje A' in r['text'] for r in self.store.segments(mid)))   # a draft never becomes a segment

        note = dispatch({'action': 'note_get', 'meeting': mid}, self.db)
        self.assertEqual(note['text'].encode('utf-8'), text.encode('utf-8'))
        self.assertEqual((note['revision'], note['author'], note['pending_key']), (2, 'user', key))
        a = note['anchors'][0]
        self.assertEqual((a['source'], a['start'], a['end'], a['status']), ('system', anchor['start'], anchor['end'], 'ok'))
        self.assertTrue(draft['audio_start'] <= a['start'] < a['end'] <= draft['audio_end'])   # still inside the drafted span
        self.assertEqual(a['segments'], [r['id'] for r in finals if r['start'] < a['end'] and r['end'] > a['start']])
        self.assertEqual([h['author'] for h in N.history(self.store, meeting=mid)], ['user', 'user'])   # the final pass wrote no revision
        # The final rows cover the draft's span (PreviewDrafts.covered: at least half of it), so the app hides it.
        overlap = sum(max(0.0, min(r['end'], draft['audio_end']) - max(r['start'], draft['audio_start'])) for r in finals)
        self.assertGreaterEqual(overlap, (draft['audio_end'] - draft['audio_start']) / 2)
        # The draft row itself is untouched by the final pass: its own table, its own text.
        self.assertEqual(next(r for r in self.drafts(mid) if r['source'] == 'system')['text'], 'proje A için deneme cuma')


class StopWhilePreparing(Base):
    def run_canceled(self, cap, ready, factory, pipeline_factory=None):
        receipt = self.root / 'receipt.json'
        mid = record(self.quiet_helper(ready), cap, 600, 12, store=self.store, result_path=receipt,
                     pipeline_factory=pipeline_factory, preview_factory=factory)
        return mid, json.loads(receipt.read_text())

    def test_stop_before_the_helpers_first_line_cancels_without_a_worker_and_keeps_the_pending_note(self):
        cap = self.root / 'recordings' / 'C0FFEE00-0000-4000-8000-000000000001'; ready = self.root / 'ready'
        dispatch({'action': 'note_save', 'pending_key': cap.name, 'base_revision': 0, 'text': 'Hazırlık notu', 'anchors': []}, self.db)
        calls = []; adapter = FakeAdapter()
        inner = PT.worker_factory(cloud_preview=True, allow_upload=True, db_path=self.db, adapter_factory=lambda: adapter)
        factory = lambda directory, mid, session=None: calls.append(mid) or inner(directory, mid, session=session)
        def stop_now():   # the stop arrives while preparing: the helper is up but has written nothing
            until(ready.exists, 5); signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
        mid, receipt = self.run_canceled(cap, ready, factory, stop_now)
        self.assertEqual((receipt['status'], receipt['finalized_chunks'], self.status(mid)), ('canceled', 0, 'canceled'))
        self.assertEqual((calls, adapter.calls), ([], []))   # no worker, no thread, no adapter
        self.assertFalse(self.has_table('transcript_previews'))
        self.assert_pending_note_kept(cap.name, mid)

    def test_stop_after_the_worker_started_but_before_any_line_leaves_no_draft(self):
        cap = self.root / 'recordings' / 'C0FFEE00-0000-4000-8000-000000000002'; ready = self.root / 'ready'
        dispatch({'action': 'note_save', 'pending_key': cap.name, 'base_revision': 0, 'text': 'Hazırlık notu', 'anchors': []}, self.db)
        adapter = FakeAdapter(); built = []
        def factory(directory, mid, session=None):
            w = self.worker(mid, directory, adapter, session=session); w.adapter_factory = lambda: built.append(1) or adapter; w.start()
            until(ready.exists, 5); signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
            return w
        mid, receipt = self.run_canceled(cap, ready, factory)
        self.assertEqual((receipt['status'], self.status(mid)), ('canceled', 'canceled'))
        self.assertEqual((built, adapter.calls, self.drafts(mid)), ([], [], []))
        reply = dispatch({'action': 'transcript_previews', 'meeting': mid}, db=self.db)
        self.assertEqual((reply['state'], reply['previews']), ('stopped', []))
        self.assertFalse(self.workers[0]._thread.is_alive())
        self.assert_pending_note_kept(cap.name, mid)

    def assert_pending_note_kept(self, key, mid):
        note = dispatch({'action': 'note_get', 'pending_key': key}, self.db)
        self.assertEqual((note['exists'], note['text'], note['revision'], note['meeting']), (True, 'Hazırlık notu', 1, None))
        # The canceled meeting stays in the list ("İptal edildi"); the app claims the note onto it by folder name.
        self.assertEqual(dispatch({'action': 'note_claim', 'pending_key': key, 'meeting': mid}, self.db)['claimed'], True)
        self.assertEqual(dispatch({'action': 'note_get', 'meeting': mid}, self.db)['text'], 'Hazırlık notu')
        # Nothing leaks into the next recording: its folder UUID has no note and its meeting no draft.
        self.assertFalse(dispatch({'action': 'note_get', 'pending_key': 'C0FFEE00-0000-4000-8000-0000000000FF'}, self.db)['exists'])
        self.assertEqual(capture_state(self.meta(mid))['session_state'], 'awaiting_stream')   # no helper line: nothing claimed


class EchoRecoveryAndCheckpointsUnchanged(Base):
    def finalize_twice(self, name, with_preview):
        cap, lines = self.capture_folder(name)
        mid = self.store.create_meeting('Kayıt', {'capture_dir': str(cap), 'provisional': True}); self.store.status(mid, 'incomplete')
        before = {p.name: digest(p) for p in sorted(cap.iterdir())}
        if with_preview:
            w = self.worker(mid, cap, FakeAdapter()).start()
            for e in lines: w.offer(e)
            self.assertTrue(until(lambda: len(self.drafts(mid)) == 2)); w.stop(1)
            self.assertEqual({p.name: digest(p) for p in sorted(cap.iterdir())}, before)   # the worker writes nothing into the capture folder
        client = FakeClient(fail_at=1)
        with self.assertRaises(OpenRouterError): finalize_capture(self.store, mid, self.root, consent=True, model='openai/gpt-transcribe', client=client)
        self.assertEqual(self.status(mid), 'incomplete')   # the failed piece is resumable
        partial = [(r['source'], r['start'], r['text']) for r in self.store.segments(mid)]
        finalize_capture(self.store, mid, self.root, consent=True, client=client)   # resume from the checkpoint, model kept from the first run
        return mid, client, (partial, [(r['source'], r['start'], r['text']) for r in self.store.segments(mid)])

    def test_finalize_uploads_resumes_and_writes_the_same_with_or_without_a_preview(self):
        plain_mid, plain, plain_rows = self.finalize_twice('A0000000-0000-4000-8000-00000000000A', False)
        mid, client, rows = self.finalize_twice('B0000000-0000-4000-8000-00000000000B', True)
        self.assertEqual(len(client.calls), len(plain.calls))
        # Uploads run in parallel, so WHICH source finished before the injected failure is a race: compare the checkpoint size, not its identity.
        self.assertEqual((len(rows[0]), rows[1]), (len(plain_rows[0]), plain_rows[1]))
        self.assertEqual({r[0] for r in rows[1]}, {'mic', 'system'})   # the mic tone is transcribed, never dropped as a whole-piece echo
        self.assertEqual((self.status(mid), self.status(plain_mid)), ('complete', 'complete'))
        self.assertEqual(len(self.drafts(mid)), 2)   # the drafts stay apart from the result, in their own table
        self.store.delete_meeting(mid)
        self.assertEqual(self.drafts(mid), [])   # and go with the meeting


if __name__ == '__main__':
    unittest.main()
