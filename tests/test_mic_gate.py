"""Mikrofon kapısı: which parts of the owner's own microphone track are meeting audio at all.

Boran, 11 Eyl 2026: "Mikrofondan gelen her sesi almak yerine sadece toplantıda unmute edince ya da bir
yerden 'benim sesimi de al' dediğimde alsın. Dışarıdan normal konuşmalar da toplantı notu gibi oluyor."
"""
import json, math, tempfile, unittest
from pathlib import Path
import numpy as np
import soundfile as sf
from meeting_os.audio import gate_events
from meeting_os.cloud_finalize import MIC_GATE_MIN_OVERLAP, finalize_capture, gate_overlap, mic_gate_windows
from meeting_os.store import Store


def gate_journal(directory, events, name='mic-gate.jsonl'):
    (Path(directory)/name).write_text(''.join(json.dumps(e, ensure_ascii=False)+'\n' for e in events))


def line(state, t, reason='zoom', **extra):
    return {'kind': 'mic_gate', 'state': state, 't': t, 'reason': reason, **extra}


class GateWindowTests(unittest.TestCase):
    def test_events_become_on_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate_journal(tmp, [line('off', 0), line('on', 30), line('off', 90), line('on', 300, 'manual')])
            self.assertEqual(mic_gate_windows(tmp), [(30.0, 90.0), (300.0, math.inf)])

    def test_a_gate_that_opens_at_second_zero_and_never_closes_covers_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate_journal(tmp, [line('on', 0, 'always')])
            windows = mic_gate_windows(tmp)
            self.assertEqual(windows, [(0.0, math.inf)])
            self.assertEqual(gate_overlap(windows, 0, 300), 300)

    def test_no_journal_at_all_is_the_old_behaviour(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(mic_gate_windows(tmp))
            self.assertIsNone(mic_gate_windows(Path(tmp)/'yok'))
            self.assertEqual(gate_overlap(None, 10, 40), 30)   # None: every piece is kept whole

    def test_a_gate_that_never_opened_is_an_empty_window_list_not_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate_journal(tmp, [line('off', 0), line('off', 120)])
            self.assertEqual(mic_gate_windows(tmp), [])
            self.assertEqual(gate_overlap([], 0, 300), 0)

    def test_junk_lines_and_out_of_order_events_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'mic-gate.jsonl'
            path.write_text('\n'.join([
                json.dumps(line('on', 60)),
                'not json at all',
                json.dumps(line('off', 20)),          # written late, belongs earlier
                json.dumps(line('on', 10)),
                json.dumps({'kind': 'mic_gate', 'state': 'belki', 't': 5}),
                json.dumps({'kind': 'mic_gate', 'state': 'on', 't': -3}),
                json.dumps({'kind': 'mic_gate', 'state': 'on', 't': 'çok'}),
                json.dumps({'kind': 'marker', 'seconds': 12}),
                '{"kind":"mic_gate","state":"off","t":',   # crash-truncated final line
            ]))
            self.assertEqual(mic_gate_windows(tmp), [(10.0, 20.0), (60.0, math.inf)])

    def test_repeated_states_do_not_reopen_or_split_a_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate_journal(tmp, [line('on', 5), line('on', 9), line('off', 40), line('off', 41)])
            self.assertEqual(mic_gate_windows(tmp), [(5.0, 40.0)])

    def test_gate_lines_are_also_read_out_of_the_capture_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'capture-native.jsonl').write_text('\n'.join([
                json.dumps({'event': 'started', 'wall': 1000.0}),
                json.dumps(line('on', 12)),
            ])+'\n')
            self.assertEqual([e['t'] for e in gate_events(tmp)], [12])
            self.assertEqual(mic_gate_windows(tmp), [(12.0, math.inf)])

    def test_the_wall_clock_puts_a_gate_after_a_sleep_where_the_audio_is(self):
        """The app counts from its own record start; the transcript runs on the helper's audio clock, which
        stops while the Mac sleeps. The same correction `read_markers` applies is applied here."""
        with tempfile.TemporaryDirectory() as tmp:
            origin = 1_757_000_000.0
            journal = [{'event': 'started', 'wall': origin}]
            # Two chunks before a 300 s lid-close, one after: the wall clock has run 300 s ahead of the audio.
            journal.append({'event': 'chunk', 'source': 'mic', 'start': 0.0, 'duration': 12.0, 'wall': origin+12})
            journal.append({'event': 'chunk', 'source': 'mic', 'start': 12.0, 'duration': 12.0, 'wall': origin+24})
            journal.append({'event': 'chunk', 'source': 'mic', 'start': 24.0, 'duration': 12.0, 'wall': origin+336})
            (Path(tmp)/'capture-native.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in journal))
            gate_journal(tmp, [line('off', 0, wall=origin), line('on', 340, wall=origin+340)])
            windows = mic_gate_windows(tmp)
            self.assertEqual(len(windows), 1)
            self.assertAlmostEqual(windows[0][0], 40.0, places=1)   # 340 s on the wall is second 40 of the audio
            self.assertEqual(windows[0][1], math.inf)


class GateOverlapTests(unittest.TestCase):
    def test_a_piece_is_kept_whole_for_any_real_overlap_and_dropped_below_a_second(self):
        windows = [(100.0, 200.0)]
        self.assertEqual(gate_overlap(windows, 0, 100), 0)              # touches the boundary only
        self.assertAlmostEqual(gate_overlap(windows, 99.5, 100.3), 0.3)   # under the floor: skipped
        self.assertLess(gate_overlap(windows, 99.5, 100.3), MIC_GATE_MIN_OVERLAP)
        self.assertEqual(gate_overlap(windows, 99, 101), 1.0)           # exactly the floor: kept
        self.assertEqual(gate_overlap(windows, 0, 300), 100)            # the piece is kept whole, audio untrimmed
        self.assertEqual(gate_overlap(windows, 200, 500), 0)

    def test_several_short_openings_add_up(self):
        windows = [(10.0, 10.4), (20.0, 20.4), (30.0, 30.4)]
        self.assertAlmostEqual(gate_overlap(windows, 0, 300), 1.2)      # three touches are one second of meeting
        self.assertGreaterEqual(gate_overlap(windows, 0, 300), MIC_GATE_MIN_OVERLAP)
        self.assertAlmostEqual(gate_overlap(windows, 0, 15), 0.4)


def capture_dir(root, seconds=70):
    """A two-source capture whose microphone carries speech-like audio of its own: without a gate every mic
    piece is uploaded. The two envelopes are deliberately uncorrelated, so nothing is skipped as echo and the
    gate is the only thing under test."""
    d = Path(root)/'rec'; d.mkdir(); events = []
    t = np.arange(16000*seconds)/16000
    def envelope(seed):
        """One amplitude per 50 ms, held: an ASR-shaped envelope that correlates with nothing else."""
        steps = np.random.default_rng(seed).uniform(0.05, 1.0, size=int(len(t)/800)+1)
        return np.repeat(steps, 800)[:len(t)]
    mic = (0.3*envelope(11)*np.sin(2*np.pi*220*t)).astype('float32')
    system = (0.3*envelope(29)*np.sin(2*np.pi*440*t)).astype('float32')
    for source, signal in (('mic', mic), ('system', system)):
        path = d/f'{source}-000000.wav'; sf.write(path, signal, 16000, subtype='FLOAT')
        events.append({'event': 'chunk', 'source': source, 'start': 0, 'duration': seconds, 'path': str(path), 'sample_rate': 16000, 'index': 0})
    (d/'capture-native.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
    return d


class FakeClient:
    def __init__(self): self.calls = []
    def transcribe(self, audio, fmt, *, model, consent, diarize=False, timeout=90, **kw):
        self.calls.append({'bytes': len(audio), 'diarize': diarize})
        return {'text': 'Bir cümle.', 'usage': {'seconds': 30, 'cost': .0003}}


class GatedFinalizeTests(unittest.TestCase):
    """30 s pieces (no provider diarization): mic 0–30/30–60/60–70, system the same."""
    def finalize(self, tmp, gate):
        d = capture_dir(tmp)
        if gate is not None: gate_journal(d, gate)
        store = Store(Path(tmp)/'db.sqlite')
        mid = store.create_meeting('Kayıt', {'capture_dir': str(d)}); store.status(mid, 'incomplete')
        client = FakeClient()
        finalize_capture(store, mid, tmp, consent=True, model='openai/gpt-transcribe', client=client)
        meta = json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?', (mid,)).fetchone()[0])
        usage = [json.loads(u) for (u,) in store.db.execute('SELECT usage FROM cloud_chunks WHERE meeting=? ORDER BY position', (mid,))]
        rows = store.segments(mid)
        store.close()
        return meta, usage, rows, client

    def test_mic_pieces_outside_the_gate_are_never_uploaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Open only for 35–50 s: the middle mic piece (30–60) is kept, the other two are gated away.
            meta, usage, rows, client = self.finalize(tmp, [line('off', 0), line('on', 35), line('off', 50)])
            gated = [u for u in usage if u.get('skipped') == 'mic_gated']
            self.assertEqual(len(gated), 2)
            self.assertEqual(meta['mic_gated_windows'], 2)
            self.assertEqual(meta['echo_windows_skipped'], 0)
            self.assertEqual(sorted({r['source'] for r in rows}), ['mic', 'system'])
            self.assertEqual(sum(1 for r in rows if r['source'] == 'mic'), 1)
            self.assertEqual(len(client.calls), 4)   # three system pieces plus the one mic piece the gate kept
            self.assertEqual(rows[0]['start'], 0)    # the kept piece is whole: no audio was trimmed

    def test_a_gate_that_never_opened_uploads_no_microphone_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta, usage, rows, client = self.finalize(tmp, [line('off', 0)])
            self.assertEqual(meta['mic_gated_windows'], 3)
            self.assertEqual([r['source'] for r in rows], ['system', 'system', 'system'])
            self.assertEqual(len(client.calls), 3)

    def test_without_a_gate_journal_every_microphone_piece_is_still_transcribed(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta, usage, rows, client = self.finalize(tmp, None)
            self.assertEqual(meta.get('mic_gated_windows'), 0)
            self.assertEqual(len(client.calls), 6)
            self.assertEqual(sum(1 for r in rows if r['source'] == 'mic'), 3)

    def test_an_always_on_gate_matches_the_old_behaviour(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta, usage, rows, client = self.finalize(tmp, [line('on', 0, 'always')])
            self.assertEqual(meta['mic_gated_windows'], 0)
            self.assertEqual(len(client.calls), 6)

    def test_a_piece_that_only_brushes_the_gate_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 59.7–60.2: half a second inside the second mic piece and two tenths inside the third.
            meta, usage, rows, client = self.finalize(tmp, [line('off', 0), line('on', 59.7), line('off', 60.2)])
            self.assertEqual(meta['mic_gated_windows'], 3)
            self.assertEqual(sum(1 for r in rows if r['source'] == 'mic'), 0)


if __name__ == '__main__':
    unittest.main()
