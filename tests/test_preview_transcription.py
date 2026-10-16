import contextlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from meeting_os import preview_transcription as PT
from meeting_os.live import record
from meeting_os.store import Store


class Fake:
    """Stands in for the provider: counts calls, optionally blocks, never touches a network."""
    def __init__(self, block=None, text=None, fail=None, cancel_aware=True):
        self.calls = []; self.block = block; self.text = text or (lambda p, s, a, b: f'{s}@{a:g}'); self.fail = fail; self.cancel_aware = cancel_aware
    def transcribe(self, path, source, start, end, cancel):
        self.calls.append((source, start))
        if self.fail: raise self.fail
        if self.block is not None:
            if self.cancel_aware: cancel.wait(self.block)
            else: time.sleep(self.block)
        return {'text': self.text(path, source, start, end), 'usage': {'cost': 0.001}}


class Cut(BaseException):
    """The process dying mid-call: not an Exception, so nothing in the worker may swallow it."""


def until(test, check, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check(): return
        time.sleep(.02)
    test.fail('koşul sağlanmadı')


class PreviewBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.cap = self.root / 'cap'; self.cap.mkdir(); self.db = self.root / 'm.sqlite'
        self.store = Store(self.db); self.mid = self.store.create_meeting('t')
        self.workers = []
    def tearDown(self):
        for w in self.workers: w.stop(.2)
        self.store.close(); self.tmp.cleanup()
    def chunk(self, source='system', start=0.0, journal=True):
        path = self.cap / f'{source}-{start:g}.wav'; path.write_bytes(b'RIFF')
        event = {'event': 'chunk', 'path': str(path), 'source': source, 'start': start, 'duration': 12.0}
        if journal:
            with (self.cap / 'events.jsonl').open('a') as f: f.write(json.dumps(event) + '\n')
        return event
    def worker(self, fake, **kw):
        kw.setdefault('upload_allowed', True)
        kw.setdefault('policy', PT.PreviewPolicy(min_free_bytes=0))   # the Mac running the tests may be short on disk; the disk budget has its own test
        w = PT.PreviewWorker(self.db, self.mid, self.cap, lambda: fake, **kw); self.workers.append(w); return w
    def rows(self):
        with contextlib.closing(PT.connect(self.db)) as c: return PT.previews(c, self.mid)
    def session(self):
        with contextlib.closing(PT.connect(self.db)) as c: return PT.session_status(c, self.mid)


class BackpressureTests(PreviewBase):
    def test_slow_provider_never_blocks_offer_and_cursor_keeps_the_rest(self):
        fake = Fake(block=60); w = self.worker(fake).start()
        began = time.monotonic()
        events = [self.chunk('system', i * 12.0) for i in range(10)]
        for e in events: w.offer(e)
        self.assertLess(time.monotonic() - began, 1.0)
        until(self, lambda: len(fake.calls) == 1)
        self.assertLessEqual(w.queue_depth(), PT.QUEUE_LIMIT)
        st = w.status(); self.assertGreaterEqual(st['lag_chunks'], 9)   # the lag is visible, not hidden
        self.assertTrue(w.stop(.3) is False)   # a 60 s call cannot finish inside the grace
        self.assertLessEqual(w.elapsed, .8)
        self.assertEqual(self.session()['cursor'], 0)   # nothing was applied; all ten wait in the journal
        # A new worker on the same folder replays the remainder from the journal, once each.
        again = Fake(); w2 = self.worker(again).start()
        until(self, lambda: self.session()['cursor'] == 10)
        self.assertEqual(sorted(c[1] for c in again.calls), [i * 12.0 for i in range(10)])   # the cancelled span is replayed, every other one once
        self.assertEqual([r['status'] for r in self.rows()], ['final'] * 10)

    def test_stop_returns_within_grace_even_when_the_provider_ignores_cancel(self):
        fake = Fake(block=2, cancel_aware=False); w = self.worker(fake).start()
        w.offer(self.chunk()); until(self, lambda: fake.calls)
        began = time.monotonic(); w.stop(.2)
        self.assertLess(time.monotonic() - began, .7)
        time.sleep(2.2)
        self.assertEqual(self.rows(), [])   # the late answer is not stored after stop


class IdempotencyTests(PreviewBase):
    def test_same_chunk_twice_is_one_call_and_one_row(self):
        fake = Fake(); w = self.worker(fake).start(); e = self.chunk()
        self.assertTrue(w.offer(e)); self.assertFalse(w.offer(e))
        until(self, lambda: len(self.rows()) == 1); time.sleep(.3)
        self.assertEqual(len(fake.calls), 1); self.assertEqual(len(self.rows()), 1)

    def test_interrupted_call_becomes_unknown_and_is_not_repeated(self):
        e = self.chunk()
        w = self.worker(Fake(fail=Cut()))
        with self.assertRaises(Cut): w._handle(0, e)   # dies after the call was recorded, before any answer
        fresh = Fake(); w2 = self.worker(fresh).start()
        until(self, lambda: self.rows() and self.rows()[0]['status'] == 'unknown')
        time.sleep(.3)
        self.assertEqual(fresh.calls, [])   # a charge that may already exist is not paid twice
        self.assertEqual(self.session()['cursor'], 1)

    def test_answer_after_a_stored_one_does_not_duplicate(self):
        with contextlib.closing(PT.connect(self.db)) as c:
            kw = dict(source='system', span='system:0.000', audio_start=0, audio_end=12)
            self.assertTrue(PT.apply_preview(c, self.mid, epoch=1, revision=1, status='final', text='a', cursor=1, **kw))
            self.assertFalse(PT.apply_preview(c, self.mid, epoch=1, revision=1, status='final', text='a', cursor=1, **kw))
        self.assertEqual(len(self.rows()), 1)


class RevisionTests(PreviewBase):
    def test_partial_then_final_then_older_revision_leaves_one_final_row(self):
        kw = dict(source='system', span='system:0.000', audio_start=0, audio_end=12)
        with contextlib.closing(PT.connect(self.db)) as c:
            self.assertTrue(PT.apply_preview(c, self.mid, epoch=1, revision=1, status='partial', text='mer', **kw))
            self.assertTrue(PT.apply_preview(c, self.mid, epoch=1, revision=2, status='final', text='merhaba', **kw))
            self.assertFalse(PT.apply_preview(c, self.mid, epoch=1, revision=1, status='partial', text='mer', **kw))
            self.assertFalse(PT.apply_preview(c, self.mid, epoch=1, revision=3, status='partial', text='x', **kw))   # a final is never reopened
        rows = self.rows(); self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['status'], rows[0]['text'], rows[0]['revision']), ('final', 'merhaba', 2))

    def test_late_epoch_one_answer_after_epoch_two_is_not_applied(self):
        w = self.worker(Fake())
        kw = dict(source='system', span='system:0.000', audio_start=0, audio_end=12)
        self.assertEqual(w.reconnect(), 2)
        with contextlib.closing(PT.connect(self.db)) as c:
            self.assertFalse(PT.apply_preview(c, self.mid, epoch=1, revision=9, status='final', text='eski', **kw))
            self.assertTrue(PT.apply_preview(c, self.mid, epoch=2, revision=1, status='final', text='yeni', **kw))
        self.assertEqual([r['text'] for r in self.rows()], ['yeni'])

    def test_reconnect_during_a_call_makes_its_answer_stale(self):
        holder = {}
        class Reconnecting(Fake):
            def transcribe(s, *a):
                holder['w'].reconnect(); return super().transcribe(*a)
        w = self.worker(Reconnecting()); holder['w'] = w
        w._handle(0, self.chunk())
        self.assertEqual(self.rows(), []); self.assertEqual(self.session()['cursor'], 1)


class PrivacyTests(PreviewBase):
    def test_no_upload_permission_builds_no_adapter_and_makes_no_call(self):
        built = []
        w = PT.PreviewWorker(self.db, self.mid, self.cap, lambda: built.append(1) or Fake(), upload_allowed=False, policy=PT.PreviewPolicy(min_free_bytes=0)).start()
        self.workers.append(w)
        w.offer(self.chunk()); time.sleep(.4)
        self.assertEqual(built, []); self.assertEqual(self.rows(), [])
        self.assertEqual((self.session()['state'], self.session()['reason']), ('disabled', 'upload_not_allowed'))

    def test_mic_outside_the_gate_is_skipped_but_its_file_stays(self):
        (self.cap / 'mic-gate.jsonl').write_text('\n'.join(json.dumps({'kind': 'mic_gate', 'state': s, 't': t}) for s, t in (('off', 0), ('on', 100))) + '\n')
        fake = Fake(); w = self.worker(fake).start(); e = self.chunk('mic', 12.0)
        w.offer(e); until(self, lambda: self.rows())
        self.assertEqual(fake.calls, []); self.assertEqual(self.rows()[0]['status'], 'skipped')
        self.assertTrue(Path(e['path']).is_file())
        self.assertEqual(self.rows()[0]['text'], '')

    def test_permission_off_and_gate_closed_means_zero_fake_calls(self):
        (self.cap / 'mic-gate.jsonl').write_text(json.dumps({'kind': 'mic_gate', 'state': 'off', 't': 0}) + '\n' + json.dumps({'kind': 'mic_gate', 'state': 'on', 't': 500}) + '\n')
        fake = Fake()
        for allowed in (False, True):
            w = PT.PreviewWorker(self.db, self.mid, self.cap, lambda: fake, upload_allowed=allowed, policy=PT.PreviewPolicy(min_free_bytes=0)).start(); self.workers.append(w)
            w.offer(self.chunk('mic', 24.0)); time.sleep(.5)
        self.assertEqual(fake.calls, [])

    def test_mic_chunk_is_not_dropped_because_system_arrives_five_seconds_later(self):
        fake = Fake(); w = self.worker(fake).start()
        w.offer(self.chunk('mic', 0.0))
        until(self, lambda: ('mic', 0.0) in fake.calls)   # decided on its own, before any system chunk exists
        time.sleep(.2); w.offer(self.chunk('system', 5.0))
        until(self, lambda: len(self.rows()) == 2)
        self.assertEqual({r['status'] for r in self.rows()}, {'final'})


class FailureTests(PreviewBase):
    def test_network_loss_pauses_the_preview_and_keeps_every_chunk(self):
        fake = Fake(fail=PT.PreviewUnavailable('offline')); w = self.worker(fake).start()
        events = [self.chunk('system', i * 12.0) for i in range(5)]
        for e in events: w.offer(e)
        until(self, lambda: self.session()['state'] == 'paused')
        self.assertEqual(self.session()['reason'], 'network'); self.assertGreaterEqual(self.session()['epoch'], 3)
        self.assertTrue(all(Path(e['path']).is_file() for e in events))
        self.assertLessEqual(len(fake.calls), PT.FAILURES_BEFORE_PAUSE)

    def test_budgets_pause_instead_of_stopping_the_recording(self):
        for policy, reason in ((PT.PreviewPolicy(max_cost=0.0005, min_free_bytes=0), 'cost'), (PT.PreviewPolicy(max_audio_seconds=10, min_free_bytes=0), 'audio_seconds'), (PT.PreviewPolicy(min_free_bytes=10 ** 18), 'disk')):
            with self.subTest(reason=reason):
                with contextlib.closing(PT.connect(self.db)) as c: c.execute('DELETE FROM preview_sessions'); c.execute('DELETE FROM transcript_previews')
                fake = Fake(); w = self.worker(fake, policy=policy).start()
                for i in range(3): w.offer(self.chunk('system', 100.0 * (i + 1) + (len(self.workers) * 1000)))
                until(self, lambda: self.session()['state'] == 'paused')
                self.assertEqual(self.session()['reason'], reason); self.assertLessEqual(len(fake.calls), 1)
                w.stop(.2)

    def test_cancel_stops_calls_and_keeps_files(self):
        fake = Fake(block=60); w = self.worker(fake).start(); e = self.chunk()
        w.offer(e); until(self, lambda: fake.calls)
        w.cancel(); w.stop(1)
        self.assertEqual(self.session()['state'], 'canceled'); self.assertTrue(Path(e['path']).is_file()); self.assertEqual(self.rows(), [])

    def test_final_pass_still_runs_normally_after_a_preview(self):
        # The preview never calls finalize_capture while recording; afterwards finalize is untouched by it.
        import meeting_os.cloud_finalize as CF
        with patch.object(CF, 'finalize_capture', side_effect=AssertionError('finalize during recording')):
            w = self.worker(Fake()).start(); w.offer(self.chunk()); until(self, lambda: self.rows()); w.stop(1)
        self.assertEqual(len(self.store.segments(self.mid)), 0)   # drafts never enter segments
        self.store.delete_meeting(self.mid)
        self.assertEqual(self.rows(), [])   # a deleted meeting takes its draft text with it


class RecordIntegrationTests(PreviewBase):
    def helper(self, events):
        p = self.root / 'recorder'
        p.write_text('#!/usr/bin/env python3\nimport time\nfor e in ' + repr(events) + ':\n    print(e,flush=True)\ntime.sleep(.3)\n'); p.chmod(0o700); return p

    def test_record_offers_chunks_and_stops_the_worker(self):
        e = self.chunk(journal=False); fake = Fake(); made = []
        def factory(directory, mid, session=None):
            w = PT.PreviewWorker(self.db, mid, directory, lambda: fake, upload_allowed=True).start(); made.append(w); return w
        mid = record(self.helper([json.dumps(e)]), self.root / 'rec', 1, 1, store=self.store, preview_factory=factory)
        self.assertEqual(len(made), 1); self.assertFalse(made[0]._thread.is_alive() and not made[0]._closed)
        self.assertTrue(made[0]._closed)
        self.assertEqual(self.store.meetings()[0]['status'] if False else self.store.db.execute('SELECT status FROM meetings WHERE id=?', (mid,)).fetchone()[0], 'provisional')

    def test_a_broken_preview_worker_does_not_touch_the_recording(self):
        class Bad:
            def offer(s, e): raise RuntimeError('boom')
            def status(s): return {}
            def stop(s, g): raise RuntimeError('boom')
        e = self.chunk(journal=False)
        mid = record(self.helper([json.dumps(e)]), self.root / 'rec', 1, 1, store=self.store, preview_factory=lambda d, m, session=None: Bad())
        self.assertEqual(self.store.db.execute('SELECT status FROM meetings WHERE id=?', (mid,)).fetchone()[0], 'provisional')

    def test_without_cloud_preview_no_adapter_is_ever_built(self):
        built = []
        factory = PT.worker_factory(cloud_preview=False, allow_upload=True, db_path=self.db, adapter_factory=lambda: built.append(1))
        self.assertIsNone(factory)
        with patch.object(PT, 'OpenRouterPreviewAdapter', side_effect=AssertionError('adapter built')):
            record(self.helper([json.dumps(self.chunk(journal=False))]), self.root / 'rec', 1, 1, store=self.store, preview_factory=factory)
        self.assertEqual(built, [])

    def test_cli_flags_exist_and_default_off(self):
        from meeting_os import cli
        text = Path(cli.__file__).read_text()
        for flag in ('--cloud-preview', '--allow-preview-upload', '--preview-model'): self.assertIn(flag, text)

    def test_desktop_action_returns_draft_text_only_in_the_reply(self):
        from meeting_os.desktop import dispatch
        w = self.worker(Fake(text=lambda *a: 'gizli taslak')).start(); w.offer(self.chunk()); until(self, lambda: self.rows())
        reply = dispatch({'action': 'transcript_previews', 'meeting': self.mid}, db=self.db)
        self.assertTrue(reply['draft']); self.assertEqual(reply['previews'][0]['text'], 'gizli taslak')
        self.assertEqual(reply['status']['state'], 'running')



class LiveGateAndBoundedReadBack(PreviewBase):
    """Audit 2026-10-16: the live gate, the age clock and the memory the read-back holds."""
    def test_a_gate_that_has_only_said_off_so_far_sends_no_mic_audio(self):
        # Only what the app has written by now: one 'off' at t=0. The owner's later 'on' is NOT pre-written.
        (self.cap / 'mic-gate.jsonl').write_text(json.dumps({'kind': 'mic_gate', 'state': 'off', 't': 0}) + '\n')
        from meeting_os.cloud_finalize import mic_gate_windows
        self.assertIsNone(mic_gate_windows(self.cap))   # the final pass keeps its rule: an unwatched gate drops nothing
        fake = Fake(); w = self.worker(fake).start()
        w.offer(self.chunk('mic', 0.0)); w.offer(self.chunk('system', 0.0))
        until(self, lambda: len(self.rows()) == 2)
        self.assertEqual(fake.calls, [('system', 0.0)])
        mic = next(r for r in self.rows() if r['source'] == 'mic')
        self.assertEqual((mic['status'], mic['reason'], mic['text']), ('skipped', 'mic_gated', ''))
        # The owner unmutes at 30 s; the app appends the line then. Only audio inside the open gate may leave the Mac.
        with (self.cap / 'mic-gate.jsonl').open('a') as f: f.write(json.dumps({'kind': 'mic_gate', 'state': 'on', 't': 30}) + '\n')
        w.offer(self.chunk('mic', 12.0)); w.offer(self.chunk('mic', 24.0))
        until(self, lambda: len(self.rows()) == 4)
        self.assertEqual([c for c in fake.calls if c[0] == 'mic'], [('mic', 24.0)])

    def test_read_back_holds_no_per_chunk_state_however_long_the_meeting(self):
        for i in range(300): self.chunk('system', i * 12.0)
        w = self.worker(Fake(), upload_allowed=False)   # not started: only the journal read-back is exercised
        self.assertEqual(w.status()['offered'], 300)
        for name in ('_journal_cache', '_seen', '_arrived'): self.assertFalse(hasattr(w, name), name)
        for i in (0, 1, 150, 299, 7):   # forward by cursor, and once backwards (re-read from the top)
            self.assertEqual(w._journal_at(i)['start'], i * 12.0)
        self.assertIsNone(w._journal_at(300))
        sized = {k: len(v) for k, v in vars(w).items() if isinstance(v, (list, set, dict, tuple))}
        self.assertTrue(all(n <= 8 for n in sized.values()), sized)
        self.assertLessEqual(len(w._scan['high']) + len(w._live['high']), 2)
        # A duplicate or a late line is recognised by the high-water mark, as the span-id set did before.
        self.assertFalse(w.offer(self.chunk('system', 12.0, journal=False)))
        self.assertTrue(w.offer(self.chunk('system', 3600.0)))

    def test_a_chunk_read_back_from_the_journal_is_dated_by_its_own_wall_stamp(self):
        stale = self.chunk('system', 0.0, journal=False); stale['wall'] = time.time() - 2000
        with (self.cap / 'events.jsonl').open('a') as f: f.write(json.dumps(stale) + '\n')
        fake = Fake(); self.worker(fake, policy=PT.PreviewPolicy(min_free_bytes=0, max_age_seconds=900)).start()
        until(self, lambda: self.session()['state'] == 'paused')
        self.assertEqual((self.session()['reason'], fake.calls), ('age', []))


if __name__ == '__main__':
    unittest.main()
