"""1.1.0–1.2.87 skipped whole microphone pieces as "echo" — with the owner's turns inside (Boran, 14 Eyl 2026,
Zoom over speakers: "herkesin transkripti çıkardı benim çıkarmadı"). `reopen_echo_skips` hands such finished
meetings back to the idle retry queue, which then uploads only the skipped mic pieces."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meeting_os.cloud_finalize import reopen_echo_skips
from meeting_os.desktop import retry_candidates
from meeting_os.store import Store


def _meeting(store, root, *, created, usages, with_audio=True, status='complete', extra=None):
    mid = store.create_meeting('Zoom', {})
    paths = {}
    for source in ('mic', 'system'):
        f = Path(root) / f'{mid}-{source}.flac'
        if with_audio: f.write_bytes(b'x')
        paths[source] = str(f)
    meta = {'cloud_mode': 'capture', 'engine': 'openrouter', 'paths': paths, **(extra or {})}
    with store.db:
        store.db.execute('CREATE TABLE IF NOT EXISTS cloud_chunks(meeting TEXT REFERENCES meetings(id), position INTEGER, usage TEXT, PRIMARY KEY(meeting,position))')
        store.db.execute('UPDATE meetings SET created=?,status=?,metadata=? WHERE id=?',
                         (created.isoformat(), status, json.dumps(meta), mid))
        for position, usage in enumerate(usages):
            store.db.execute('INSERT INTO cloud_chunks VALUES(?,?,?)', (mid, position, json.dumps(usage)))
    return mid


class ReopenEchoSkips(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'db.sqlite'); self.addCleanup(self.store.close)
        self.now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)

    def meta(self, mid):
        return json.loads(self.store.db.execute('SELECT metadata FROM meetings WHERE id=?', (mid,)).fetchone()[0])

    def test_a_recent_meeting_with_echo_skips_goes_back_to_the_retry_queue_once(self):
        mid = _meeting(self.store, self.tmp.name, created=self.now - timedelta(hours=3),
                       usages=[{'cost': 0.01}, {'skipped': 'echo'}, {'skipped': 'echo'}, {'skipped': 'silent'}])
        self.assertEqual(reopen_echo_skips(self.store, now=self.now), [mid])
        row = self.store.db.execute('SELECT status FROM meetings WHERE id=?', (mid,)).fetchone()
        self.assertEqual(row[0], 'incomplete')
        meta = self.meta(mid)
        self.assertEqual(meta['echo_reopen_pieces'], 2)
        self.assertIn('Mikrofon sesi geri getiriliyor', meta['cloud_error']['message'])
        # the idle queue sees it as due now
        due = [c['meeting'] for c in retry_candidates(self.store, now=self.now)['candidates']]
        self.assertEqual(due, [mid])
        # the paid system checkpoint stays; only transcribe_sources' resume touches the echo ones
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM cloud_chunks WHERE meeting=?', (mid,)).fetchone()[0], 4)
        # once: a second pass does nothing, even after the retry completed
        self.store.status(mid, 'complete')
        self.assertEqual(reopen_echo_skips(self.store, now=self.now + timedelta(hours=1)), [])

    def test_meetings_without_echo_skips_or_without_audio_or_too_old_are_left_alone(self):
        clean = _meeting(self.store, self.tmp.name, created=self.now - timedelta(hours=1), usages=[{'cost': 0.01}, {'skipped': 'silent'}])
        gone = _meeting(self.store, self.tmp.name, created=self.now - timedelta(hours=1), usages=[{'skipped': 'echo'}], with_audio=False)
        old = _meeting(self.store, self.tmp.name, created=self.now - timedelta(days=4), usages=[{'skipped': 'echo'}])
        canceled = _meeting(self.store, self.tmp.name, created=self.now - timedelta(hours=1), usages=[{'skipped': 'echo'}], extra={'cloud_canceled': True})
        self.assertEqual(reopen_echo_skips(self.store, now=self.now), [])
        for mid in (clean, gone, old, canceled):
            self.assertEqual(self.store.db.execute('SELECT status FROM meetings WHERE id=?', (mid,)).fetchone()[0], 'complete')

    def test_a_database_that_never_saw_the_cloud_is_simply_empty(self):
        self.assertEqual(reopen_echo_skips(self.store, now=self.now), [])

    def test_the_skip_counters_no_longer_call_silence_echo(self):
        from meeting_os import cloud_finalize
        text = Path(cloud_finalize.__file__).read_text(encoding='utf-8')
        self.assertIn("metadata['silent_windows_skipped']", text)
        self.assertNotIn("'skipped' in u and 'mic_gated' not in u", text)


if __name__ == '__main__':
    unittest.main()
