"""Reproductions for the 2026-09-13 reliability audit (docs/reviews/2026-09-13-reliability-audit.md).

Every test here states the behaviour the app SHOULD have. They are marked `@unittest.expectedFailure` so the
suite stays green while the bugs stand: fixing one turns it into an unexpected success, which unittest
reports as a failure, so the marker has to be removed in the same commit as the fix. That is the point.
"""
import json, sqlite3, tempfile, unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from meeting_os import cloud_finalize as CF
from meeting_os.store import Store


def capture_dir(root, seconds=4, silent_mic=False):
    """A two-source capture folder. The mic carries the owner's voice at 220 Hz and the system carries the
    other side at 880 Hz: uncorrelated, so the echo test keeps them apart and neither reads as silence."""
    d = Path(root)/'rec'; d.mkdir(); events = []
    t = np.arange(16000*seconds)/16000
    mic = np.zeros(len(t), dtype='float32') if silent_mic else (0.3*np.sin(2*np.pi*220*t)).astype('float32')
    system = (0.3*np.sin(2*np.pi*880*t)).astype('float32')
    for source, signal in (('mic', mic), ('system', system)):
        path = d/f'{source}-000000.wav'; sf.write(path, signal, 16000, subtype='FLOAT')
        events.append({'event': 'chunk', 'source': source, 'start': 0, 'duration': seconds,
                       'path': str(path), 'sample_rate': 16000, 'index': 0})
    (d/'capture-native.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
    return d


class FakeClient:
    def __init__(self): self.uploads = []
    def transcribe(self, audio, fmt, *, model, consent, diarize=False, timeout=90, **kw):
        self.uploads.append(model)
        return {'text': 'Tam transkript.', 'usage': {'seconds': 4, 'cost': .0003}}


class MicGateTests(unittest.TestCase):
    """P0-1 — the microphone gate silently throws away the owner's half of the meeting."""

    @unittest.expectedFailure
    def test_a_gate_that_never_opened_still_transcribes_the_owner(self):
        """A teammate on Google Meet (or on Zoom without the Accessibility grant) gets `zoomMuted == nil`
        for the whole recording. MicGate.state treats unknown as muted, so the app journals one `off` line at
        t=0 and never another. `mic_gate_windows` then returns [] — not None — and every mic piece is dropped
        as `mic_gated`. The transcript contains everyone except the person who recorded it, with no warning.

        The gate should not be able to discard a whole track on an answer it never actually got: a recording
        whose gate never opened once must fall back to transcribing the microphone."""
        with tempfile.TemporaryDirectory() as tmp:
            d = capture_dir(tmp)
            (d/'mic-gate.jsonl').write_text(json.dumps(
                {'kind': 'mic_gate', 'state': 'off', 't': 0.0, 'reason': 'zoom'})+'\n')
            store = Store(Path(tmp)/'db.sqlite')
            mid = store.create_meeting('Meet toplantısı', {'capture_dir': str(d)}); store.status(mid, 'incomplete')
            CF.finalize_capture(store, mid, tmp, consent=True, model='openai/gpt-transcribe', client=FakeClient())
            sources = {r['source'] for r in store.segments(mid)}
            store.close()
            self.assertIn('mic', sources, 'the owner is missing from their own transcript')


class FinalizeAtomicityTests(unittest.TestCase):
    """P0-2 — a finished, paid-for transcript is flipped back to `incomplete` by a bookkeeping failure."""

    @unittest.expectedFailure
    def test_a_complete_transcript_survives_a_failing_post_complete_step(self):
        """cloud_finalize.py:924 marks the meeting complete; lines 925-930 then compact the chunks, archive
        the WAVs to FLAC and write the team report. All three sit INSIDE the `except BaseException` at :933,
        which sets the meeting back to `incomplete` and schedules a cloud retry.

        `compact_capture` (:817) and `archive_meeting` (audio_archive.py:57) each open a write transaction, so
        an ordinary `database is locked` from the concurrent poll or the hourly housekeeping is enough. The
        transcript is already in the database and already paid for; the user is shown a failed meeting, the
        team report is never written, and one of the thirty retries is spent.

        Once the transcript is committed, the meeting is complete. Housekeeping after that point may fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = capture_dir(tmp, silent_mic=True); store = Store(Path(tmp)/'db.sqlite')
            mid = store.create_meeting('Kayıt', {'capture_dir': str(d)}); store.status(mid, 'incomplete')
            real = CF.compact_capture
            def locked(store, mid):
                real(store, mid)
                raise sqlite3.OperationalError('database is locked')
            CF.compact_capture = locked
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    CF.finalize_capture(store, mid, tmp, consent=True, model='openai/gpt-transcribe', client=FakeClient())
            finally:
                CF.compact_capture = real
            row = store.db.execute('SELECT status,metadata FROM meetings WHERE id=?', (mid,)).fetchone()
            status, meta = row['status'], json.loads(row['metadata'])
            segments = len(store.segments(mid)); store.close()
            self.assertEqual(segments, 1, 'guard: the transcript really was committed')
            self.assertEqual(status, 'complete', 'a committed transcript was demoted by a housekeeping failure')
            self.assertIsNone(meta.get('cloud_error'), 'a retry was scheduled for a meeting that succeeded')


class HousekeepingIsolationTests(unittest.TestCase):
    """P0-3 — one unreachable folder stops every later housekeeping step, for good and in silence."""

    @unittest.expectedFailure
    def test_retention_and_pruning_still_run_when_the_team_sync_fails(self):
        """desktop.py:810-843 is one unguarded straight line: archive, team_sync, audio retention, text
        retention, learning prune, calibration, experiments, preferences, task errors. `team_knowledge.sync`
        (:819) touches a shared folder that may be an unmounted network volume or a signed-out iCloud Drive.
        When it raises, nothing after it runs — and the Swift caller discards the error
        (`ModelActions.swift:132` is `_=try? await requestSlow(...)`), so the user is never told.

        The pass runs hourly and at every launch, so a teammate whose team folder is unreachable never prunes
        audio, never prunes text, never prunes the event log and never refreshes calibration — for months,
        while the disk fills. Each step should be isolated: a failing sync costs the sync, not the retention."""
        from meeting_os import desktop as D, learning as L, team_knowledge as TK
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)/'data'; data.mkdir()
            db = data/'meeting-os.sqlite'
            store = Store(db); store.status(store.create_meeting('Eski', {}), 'complete'); store.close()
            (data/'settings.json').write_text(json.dumps({'audio_retention_days': 30, 'text_retention_days': 0}))
            ran = []
            real_sync, real_prune = TK.sync, L.prune
            def unreachable(store, data_dir, settings=None): raise OSError(5, 'Input/output error')
            def spy(store): ran.append('prune'); return real_prune(store)
            TK.sync, L.prune = unreachable, spy
            try:
                result = D.dispatch({'action': 'storage_housekeeping'}, db=str(db))
            finally:
                TK.sync, L.prune = real_sync, real_prune
            self.assertEqual(ran, ['prune'], 'the event-log prune was skipped by an unrelated sync failure')
            self.assertIn('retention_days', result)


class MigrationTests(unittest.TestCase):
    """P0-4 — opening an older database leaves a write transaction open for the life of the process."""

    @unittest.expectedFailure
    def test_upgrading_an_old_database_does_not_hold_the_write_lock(self):
        """store.py:67 runs `_backfill_sample_dates` (store.py:103-111), whose `executemany` opens an implicit
        transaction and never commits it — unlike `_backfill_feedback` (store.py:275), which wraps its writes
        in `with self.db:`. On a database that already has `corrections.feedback` (so that later migration's
        commit does not accidentally rescue this one) the transaction stays open until `close()` rolls it back.

        Two consequences on the first launch after an upgrade: every other process — the 2 s poll, a bridge
        call, the hourly pass — blocks on the write lock and then reports `database is locked`; and the dates
        are rolled back while the column survives, so the `if 'created' not in sample_columns` guard never
        fires again and the backfill is lost permanently."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'old.sqlite'
            seed = sqlite3.connect(path)
            seed.executescript('''
                CREATE TABLE meetings(id TEXT PRIMARY KEY,title TEXT,created TEXT,status TEXT,metadata TEXT);
                CREATE TABLE samples(id INTEGER PRIMARY KEY,name TEXT,model TEXT,vector TEXT,duration REAL,provenance TEXT);
                CREATE TABLE corrections(id INTEGER PRIMARY KEY,meeting TEXT,speaker TEXT,name TEXT,created TEXT,previous_name TEXT,feedback TEXT);''')
            seed.execute("INSERT INTO meetings VALUES('m1','T','2026-01-01T00:00:00+00:00','complete','{}')")
            seed.execute("INSERT INTO samples(name,model,vector,duration,provenance) VALUES('Ayşe','m','[]',3.0,'m1:42')")
            seed.commit(); seed.close()

            store = Store(path)
            open_transaction = store.db.in_transaction
            other = sqlite3.connect(path, timeout=1.0)
            try:
                other.execute("INSERT INTO meetings VALUES('m2','T2','2026-01-02T00:00:00+00:00','complete','{}')")
                other.commit(); locked = False
            except sqlite3.OperationalError:
                locked = True
            finally:
                other.close(); store.close()
            dates = sqlite3.connect(path).execute('SELECT created FROM samples').fetchone()[0]
            self.assertFalse(open_transaction, 'Store.__init__ left a write transaction open')
            self.assertFalse(locked, 'another process could not write while the store was merely open')
            self.assertIsNotNone(dates, 'the sample-date backfill was rolled back and can never run again')


class LearningLoopTests(unittest.TestCase):
    """P1 — the summary/Kontrol decisions the learning loop exists to measure are recorded blank."""

    @unittest.expectedFailure
    def test_a_summary_decision_records_which_item_it_was(self):
        """insight_layer.py:92 and review.py:138 call the recorder with `meeting=mid`, which
        `learning.record_event` (learning.py:105) has no parameter for. The TypeError lands on the fallback at
        insight_layer.py:34 — `record_event(store, action)` — so the row is written with no object, no
        outcome and no scope. The learning loop shipped in 1.2.80-1.2.86 is measuring nothing here."""
        from meeting_os import insight_layer as IL, learning as L
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'db.sqlite')
            mid = store.create_meeting('Kayıt', {}); store.status(mid, 'complete')
            IL.record(store, mid, 'i1', section='summary', action='edit', text='Düzeltilmiş madde', version=1)
            rows = L.events(store) if hasattr(L, 'events') else [
                dict(r) for r in store.db.execute('SELECT action,object,scope,outcome FROM learning_events')]
            store.close()
            self.assertTrue(rows, 'the decision was not recorded at all')
            self.assertEqual(rows[-1]['object'], 'i1', f'recorded without the item it was about: {rows[-1]}')


if __name__ == '__main__':
    unittest.main()
