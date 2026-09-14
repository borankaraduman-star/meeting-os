"""A mostly echoed microphone piece can still contain the owner's only turn."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from meeting_os.cloud_finalize import envelope_correlation, transcribe_sources
from meeting_os.store import Store
from tests.test_cloud_finalize import FakeClient


def mixed_sources(root):
    rate = 16000
    t = np.arange(rate * 300) / rate
    envelope = np.repeat(np.random.default_rng(12).uniform(.02, 1., 6000), 800)
    system = (.25 * np.sin(2 * np.pi * 220 * t) * envelope).astype('float32')
    system[rate * 120:rate * 122] = 0
    mic = .4 * system.copy()
    # A short local turn while the remote side is silent. The rest is pure bleed.
    mic[rate * 120:rate * 122] = .2 * np.sin(2 * np.pi * 330 * t[rate * 120:rate * 122])
    sources = {}
    for source, audio in (('mic', mic), ('system', system)):
        sources[source] = Path(root) / (source + '.wav')
        sf.write(sources[source], audio, rate, subtype='FLOAT')
    return sources, envelope_correlation(mic, system)


class LocalTurnPreservationTests(unittest.TestCase):
    def test_mostly_echoed_piece_still_transcribes_the_local_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, correlation = mixed_sources(tmp)
            self.assertGreater(correlation, .8, 'fixture must trigger the old whole-piece drop')
            store = Store(Path(tmp) / 'db.sqlite')
            self.addCleanup(store.close)
            mid = store.create_meeting('Short local turn', {})
            transcribe_sources(store, mid, sources, FakeClient(), consent=True,
                               model='microsoft/mai-transcribe-2', owner='Boran')
            rows = store.segments(mid)
            self.assertEqual({r['source'] for r in rows}, {'mic', 'system'})
            self.assertTrue(all(r['speaker'] == 'Boran' for r in rows if r['source'] == 'mic'))
            usage = [json.loads(r[0]) for r in store.db.execute(
                'SELECT usage FROM cloud_chunks WHERE meeting=?', (mid,))]
            self.assertFalse(any(u.get('skipped') == 'echo' for u in usage))

    def test_resume_reconsiders_legacy_echo_skip_without_replacing_paid_system_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, _ = mixed_sources(tmp)
            store = Store(Path(tmp) / 'db.sqlite')
            self.addCleanup(store.close)
            mid = store.create_meeting('Legacy checkpoint', {})
            client = FakeClient()
            transcribe_sources(store, mid, sources, client, consent=True,
                               model='microsoft/mai-transcribe-2')
            original_system = [r for r in store.segments(mid) if r['source'] == 'system']
            # Model an old incomplete job: mic piece 0 was skipped for free, system piece 1 paid.
            with store.db:
                store.db.execute('DELETE FROM segments WHERE meeting=? AND source=?', (mid, 'mic'))
                store.db.execute('UPDATE cloud_chunks SET usage=? WHERE meeting=? AND position=0',
                                 ('{"skipped":"echo"}', mid))
            transcribe_sources(store, mid, sources, client, consent=True,
                               model='microsoft/mai-transcribe-2')
            rows = store.segments(mid)
            self.assertTrue(any(r['source'] == 'mic' for r in rows), 'legacy skip must not suppress recovery')
            self.assertEqual([r for r in rows if r['source'] == 'system'], original_system)
