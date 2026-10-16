"""The user's own notes (meeting_os/notes.py): a document beside the transcript, never part of it.

Every test runs on a tempfile database. The network is a fake: a capturing LLM for the analysis and the
in-process sync server of test_team_cloud for the team cloud. The acceptance table is ONERILER.md §3.
"""
import json
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from meeting_os import assistant, diagnostics, notes as N, reports
from meeting_os import errors as E
from meeting_os.desktop import dispatch, note_action, storage_cleanup
from meeting_os.store import Store
from meeting_os.types import Segment

try: from test_team_cloud import CloudFixture             # discover -s tests puts tests/ on sys.path
except ImportError: from tests.test_team_cloud import CloudFixture

SECRET = 'GIZLI-NOT-7f3a Karar: deneme cuma, Ayşe bütçeyi saklıyor'


class CapturingLLM:
    """Records every prompt it is sent and answers with one valid summary item quoting the first row."""
    model_id = 'fixture'

    def __init__(self, sid, quote):
        self.prompts = []
        self.answer = json.dumps({'summary': [{'text': 'Proje konuşuldu', 'evidence': [{'segment_id': sid, 'quote': quote}]}],
                                  'decisions': [], 'risks': [], 'questions': [], 'actions': []})

    def count(self, text): return len(text) // 4 + 1

    def complete(self, system, prompt, **kwargs):
        self.prompts.append(system + '\n' + prompt); return self.answer


class _FailingDB:
    """The store's connection with one statement made to fail, as a disk error or a kill would."""

    def __init__(self, db, needle):
        self._db, self.needle = db, needle

    def execute(self, sql, *args):
        if self.needle in sql: raise sqlite3.OperationalError('disk I/O error')
        return self._db.execute(sql, *args)

    def __getattr__(self, name): return getattr(self._db, name)


class NoteFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.data = Path(self._tmp.name)
        self.db = self.data / 'meeting-os.sqlite'
        self.store = Store(self.db)
        self.mid = self.store.create_meeting('Plan')
        self.sid = self.store.add_segment(self.mid, Segment(10.0, 14.0, 'Proje A için deneme cuma yapılacak.', 'system', 'system:S1'))
        self.store.add_segment(self.mid, Segment(2.0, 5.0, 'Merhaba herkese.', 'mic', 'Ben'))

    def tearDown(self):
        self.store.close(); self._tmp.cleanup()

    def anchor(self, **kw):
        return {'id': 'a1', 'source': 'system', 'start': 10.5, 'end': 13.0, 'segment': self.sid, **kw}


class TranscriptNeverWritesTheNote(NoteFixture):
    def test_finalizer_retry_and_analysis_leave_the_note_byte_for_byte(self):
        text = 'Karar: deneme cuma\n  • ikinci satır, boşluklar korunur  \n'
        saved = N.save_note(self.store, meeting=self.mid, base_revision=0, text=text, anchors=[self.anchor()])
        self.assertEqual((saved['ok'], saved['revision']), (True, 1))
        # Fake finalizer: the whole transcript is replaced with the final one ("proje A" → "proje B").
        with self.store.db: self.store.db.execute('DELETE FROM segments WHERE meeting=?', (self.mid,))
        final = self.store.add_segment(self.mid, Segment(10.0, 14.0, 'Proje B için deneme cuma yapılacak.', 'system', 'system:S1'))
        # Fake retry: a correction lands on the new transcript through the untouched correct_text path.
        self.store.status(self.mid, 'complete')
        self.store.correct_text(self.mid, final, 'Proje B için deneme perşembe yapılacak.')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM text_edits WHERE meeting=?', (self.mid,)).fetchone()[0], 1)
        # Fake analysis: a model summary is saved for the meeting.
        llm = CapturingLLM(final, 'Proje B için deneme perşembe yapılacak.')
        assistant.analyze(self.store, self.mid, llm)
        self.assertEqual(len(llm.prompts), 1)
        note = N.get_note(self.store, meeting=self.mid)
        self.assertEqual(note['text'].encode('utf-8'), text.encode('utf-8'))
        self.assertEqual((note['revision'], note['author']), (1, 'user'))
        self.assertEqual([h['revision'] for h in N.history(self.store, meeting=self.mid)], [1])
        # The anchor kept its audio range and now resolves to the final row for that moment.
        a = note['anchors'][0]
        self.assertEqual((a['start'], a['end'], a['status'], a['segments']), (10.5, 13.0, 'ok', [final]))
        self.assertNotIn('text', a); self.assertNotIn('quote', a)

    def test_ai_text_becomes_a_revision_only_through_an_explicit_save(self):
        N.save_note(self.store, meeting=self.mid, base_revision=0, text='Benim notum')
        out = note_action(self.store, 'note_save', {'meeting': self.mid, 'base_revision': 1, 'text': 'Benim notum\nÖzet: kabul edildi', 'author': 'ai_accepted'}, self.data)
        self.assertEqual(out['revision'], 2)
        out = note_action(self.store, 'note_save', {'meeting': self.mid, 'base_revision': 2, 'text': 'x', 'author': 'robot'}, self.data)
        self.assertEqual([h['author'] for h in N.history(self.store, meeting=self.mid)], ['user', 'ai_accepted', 'user'])
        with self.assertRaises(N.NoteError): N.save_note(self.store, meeting=self.mid, base_revision=3, text='y', author='model')


class CompareAndSwap(NoteFixture):
    def test_two_windows_on_revision_three_one_wins_the_other_gets_a_conflict(self):
        for revision, text in enumerate(('bir', 'iki', 'üç')):
            self.assertEqual(N.save_note(self.store, meeting=self.mid, base_revision=revision, text=text)['revision'], revision + 1)
        first = N.save_note(self.store, meeting=self.mid, base_revision=3, text='pencere 1')
        second = N.save_note(self.store, meeting=self.mid, base_revision=3, text='pencere 2')
        self.assertEqual((first.get('ok'), first['revision']), (True, 4))
        self.assertEqual(second, {'conflict': True, 'parked': True, 'revision': 4, 'text': 'pencere 1', 'anchors': []})
        self.assertEqual(N.get_note(self.store, meeting=self.mid)['text'], 'pencere 1')
        self.assertEqual([h['text'] for h in N.history(self.store, meeting=self.mid)], ['pencere 1', 'üç', 'iki', 'bir'])
        # The loser resolves by saving on top of the current revision: nothing of either window is lost.
        self.assertEqual(N.save_note(self.store, meeting=self.mid, base_revision=4, text='pencere 1\npencere 2')['revision'], 5)

    def test_the_text_that_lost_the_cas_is_parked_on_disk_until_the_user_picks_a_side(self):
        # Judge 2026-10-16: a conflict wrote nothing, so quitting before choosing lost the text that lived only in
        # the editor. Now the refused text is a draft in the same transaction and comes back with the note.
        N.save_note(self.store, meeting=self.mid, base_revision=0, text='ilk')
        N.save_note(self.store, meeting=self.mid, base_revision=1, text='diğer Mac')
        lost = N.save_note(self.store, meeting=self.mid, base_revision=1, text='benim yazım', anchors=[self.anchor()])
        self.assertTrue(lost['conflict'] and lost['parked'])
        self.store.close(); self.store = Store(self.db)   # the app quit and came back
        note = N.get_note(self.store, meeting=self.mid)
        self.assertEqual((note['revision'], note['text']), (2, 'diğer Mac'), 'park notu yazmaz')
        self.assertEqual((note['draft']['text'], note['draft']['base_revision'], note['draft']['anchors'][0]['status']), ('benim yazım', 1, 'ok'))
        # Text typed into the conflict bar is parked too — even on an equal revision a park never writes the note.
        parked = N.save_note(self.store, meeting=self.mid, base_revision=2, text='benim yazım, devamı', park=True)
        self.assertTrue(parked['parked']); self.assertEqual(N.get_note(self.store, meeting=self.mid)['text'], 'diğer Mac')
        self.assertEqual(N.get_note(self.store, meeting=self.mid)['draft']['text'], 'benim yazım, devamı')
        self.assertEqual(len(N.history(self.store, meeting=self.mid)), 2)
        # "Benim sürümümü kaydet": the save succeeds and no other side is left.
        self.assertEqual(N.save_note(self.store, meeting=self.mid, base_revision=2, text='benim yazım, devamı')['revision'], 3)
        self.assertNotIn('draft', N.get_note(self.store, meeting=self.mid))
        # "Diğerini al": only that explicit choice drops a draft.
        N.save_note(self.store, meeting=self.mid, base_revision=1, text='eski pencere')
        self.assertIn('draft', N.get_note(self.store, meeting=self.mid))
        self.assertEqual(N.drop_draft(self.store, meeting=self.mid), {'dropped': 1})
        self.assertNotIn('draft', N.get_note(self.store, meeting=self.mid))
        # Through the bridge: the same contract.
        r = dispatch({'action': 'note_save', 'meeting': self.mid, 'base_revision': 0, 'text': 'köprü', 'park': True}, self.db)
        self.assertTrue(r['parked'])
        self.assertEqual(dispatch({'action': 'note_get', 'meeting': self.mid}, self.db)['draft']['text'], 'köprü')
        self.assertEqual(dispatch({'action': 'note_draft_drop', 'meeting': self.mid}, self.db), {'dropped': 1})

    def test_the_winning_windows_next_autosave_leaves_the_losing_windows_parked_text_alone(self):
        # Judge 2026-10-16 (s6): window B's ordinary autosave after the CAS dropped the draft window A had parked;
        # with A closed, A's text was gone and nobody had picked a side.
        N.save_note(self.store, meeting=self.mid, base_revision=0, text='ilk')
        N.save_note(self.store, meeting=self.mid, base_revision=1, text='B penceresi')
        self.assertTrue(N.save_note(self.store, meeting=self.mid, base_revision=1, text='A penceresi', anchors=[self.anchor()])['parked'])
        self.assertEqual(N.save_note(self.store, meeting=self.mid, base_revision=2, text='B penceresi, devam')['revision'], 3)
        r = dispatch({'action': 'note_save', 'meeting': self.mid, 'base_revision': 3, 'text': 'B penceresi, devam.'}, self.db)
        self.assertEqual(r['revision'], 4)
        self.store.close(); self.store = Store(self.db)   # A was closed; the app comes back
        note = N.get_note(self.store, meeting=self.mid)
        self.assertEqual((note['text'], note['draft']['text']), ('B penceresi, devam.', 'A penceresi'), 'A penceresinin metni seçilmeden silinmez')
        # A save that makes the draft redundant (same text and anchors are the note now) may take it.
        anchors = [{k: v for k, v in a.items() if k != 'status'} for a in note['draft']['anchors']]
        N.save_note(self.store, meeting=self.mid, base_revision=4, text='A penceresi', anchors=anchors)
        self.assertNotIn('draft', N.get_note(self.store, meeting=self.mid))
        # "Benim sürümümü kaydet" (resolve) drops the parked side even when the text kept was edited further.
        N.save_note(self.store, meeting=self.mid, base_revision=1, text='A eski')
        r = dispatch({'action': 'note_save', 'meeting': self.mid, 'base_revision': 5, 'text': 'A eski, düzeltilmiş', 'resolve': True}, self.db)
        self.assertEqual(r['revision'], 6)
        self.assertNotIn('draft', N.get_note(self.store, meeting=self.mid))

    def test_a_draft_parked_under_the_pending_key_survives_the_claim_and_the_meeting_deletion_takes_it(self):
        N.save_note(self.store, pending_key='UUID-9', base_revision=0, text='hazırlık')
        N.save_note(self.store, pending_key='UUID-9', base_revision=0, text='ikinci pencere')
        mid = self.store.create_meeting('Bağlanan')
        self.assertTrue(N.claim_pending(self.store, 'UUID-9', mid)['claimed'])
        self.assertEqual(N.get_note(self.store, meeting=mid)['draft']['text'], 'ikinci pencere')
        self.store.delete_meeting(mid)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM note_drafts').fetchone()[0], 0)

    def test_an_older_notes_database_gets_the_draft_table_on_its_next_write(self):
        self.store.db.executescript(N.DDL.split('CREATE TABLE IF NOT EXISTS note_drafts')[0])
        self.assertFalse(N._has_drafts(self.store))
        self.assertNotIn('draft', N.get_note(self.store, meeting=self.mid))
        self.assertTrue(N.save_note(self.store, meeting=self.mid, base_revision=7, text='x')['parked'])
        self.assertEqual(N.get_note(self.store, meeting=self.mid)['draft']['text'], 'x')

    def test_an_unchanged_autosave_is_not_a_revision_and_a_new_note_starts_at_zero(self):
        self.assertTrue(N.save_note(self.store, meeting=self.mid, base_revision=5, text='x')['conflict'])
        N.save_note(self.store, meeting=self.mid, base_revision=0, text='x')
        self.assertTrue(N.save_note(self.store, meeting=self.mid, base_revision=1, text='x')['unchanged'])
        self.assertEqual(len(N.history(self.store, meeting=self.mid)), 1)

    def test_a_failure_inside_the_save_leaves_the_old_or_the_new_revision_whole(self):
        for revision, text in enumerate(('bir', 'iki', 'üç')):
            N.save_note(self.store, meeting=self.mid, base_revision=revision, text=text)
        real = self.store.db
        for needle in ('INSERT INTO note_revisions', 'COMMIT', 'UPDATE meeting_notes'):
            self.store.db = _FailingDB(real, needle)
            try:
                with self.assertRaises(sqlite3.OperationalError): N.save_note(self.store, meeting=self.mid, base_revision=3, text='yarım kalan')
            finally: self.store.db = real
            note = N.get_note(self.store, meeting=self.mid)
            self.assertEqual((note['revision'], note['text']), (3, 'üç'), needle)
            self.assertEqual(real.execute('SELECT max(revision) FROM note_revisions').fetchone()[0], 3, needle)
            self.assertFalse(real.in_transaction)
        # Through the bridge the user sees a sentence, not the sqlite message; the journal keeps the type only.
        self.store.db = _FailingDB(real, 'INSERT INTO note_revisions')
        try:
            with self.assertRaises(ValueError) as caught:
                note_action(self.store, 'note_save', {'meeting': self.mid, 'base_revision': 3, 'text': SECRET}, self.data)
        finally: self.store.db = real
        self.assertIn('Not kaydedilemedi', str(caught.exception)); self.assertNotIn('disk I/O', str(caught.exception))
        journal = (self.data / 'errors.jsonl').read_text(encoding='utf-8')
        self.assertIn('OperationalError', journal); self.assertNotIn('GIZLI-NOT', journal)
        # The next save works and is complete.
        self.assertEqual(N.save_note(self.store, meeting=self.mid, base_revision=3, text='dört')['revision'], 4)


class Anchors(NoteFixture):
    def test_a_resplit_transcript_keeps_the_anchor_audio_range(self):
        N.save_note(self.store, meeting=self.mid, base_revision=0, text='Karar: deneme cuma', anchors=[self.anchor()])
        with self.store.db: self.store.db.execute('DELETE FROM segments WHERE meeting=? AND source=?', (self.mid, 'system'))
        left = self.store.add_segment(self.mid, Segment(9.0, 12.0, 'Proje A için', 'system', 'system:S2', 'Yanlış Ad'))
        right = self.store.add_segment(self.mid, Segment(12.0, 16.0, 'deneme cuma yapılacak.', 'system', 'system:S2'))
        self.store.add_segment(self.mid, Segment(20.0, 22.0, 'Başka konu.', 'system', 'system:S2'))
        a = N.get_note(self.store, meeting=self.mid)['anchors'][0]
        self.assertEqual((a['source'], a['start'], a['end'], a['segment']), ('system', 10.5, 13.0, self.sid))
        self.assertEqual((a['status'], a['segments'], a['segment_current']), ('ok', [left, right], False))
        self.assertNotIn('speaker', a); self.assertNotIn('speaker_name', a)   # no new speaker name is adopted into the note

    def test_a_reused_segment_id_on_another_source_or_moment_is_not_the_anchor(self):
        # Judge s8: after a retry SQLite hands the deleted row's id to an unrelated sentence; the bare id must not
        # pull it into the link nor keep a link whose source is gone 'ok'.
        N.save_note(self.store, meeting=self.mid, base_revision=0, text='Karar: deneme cuma', anchors=[self.anchor()])
        with self.store.db: self.store.db.execute('DELETE FROM segments WHERE meeting=?', (self.mid,))
        for source, start, end in (('mic', 10.0, 14.0), ('system', 300.0, 304.0)):
            with self.store.db: self.store.db.execute('DELETE FROM segments WHERE meeting=?', (self.mid,))
            with self.store.db:
                self.store.db.execute('INSERT INTO segments(id,meeting,start,end,source,speaker,payload) VALUES(?,?,?,?,?,?,?)',
                                      (self.sid, self.mid, start, end, source, 'Ben', json.dumps({'text': 'Başka bir cümle.'})))
            a = N.get_note(self.store, meeting=self.mid)['anchors'][0]
            self.assertEqual((a['status'], a['segments'], a['segment_current']), ('source_unavailable', [], False), source)
        # The same id back on the same source and moment is the anchor again.
        with self.store.db: self.store.db.execute('UPDATE segments SET source=?,start=?,end=? WHERE id=?', ('system', 10.0, 14.0, self.sid))
        a = N.get_note(self.store, meeting=self.mid)['anchors'][0]
        self.assertEqual((a['status'], a['segments'], a['segment_current']), ('ok', [self.sid], True))

    def test_retention_removes_audio_and_rows_the_note_stays_and_says_source_unavailable(self):
        folder = self.data / 'recordings' / uuid.uuid4().hex; folder.mkdir(parents=True)
        (folder / 'system.wav').write_bytes(b'RIFF0000WAVE'); (folder / 'mic.wav').write_bytes(b'RIFF0000WAVE')
        meta = {'capture_dir': str(folder), 'paths': {'system': str(folder / 'system.wav'), 'mic': str(folder / 'mic.wav')}}
        with self.store.db:
            self.store.db.execute("UPDATE meetings SET metadata=?,status='complete',created=? WHERE id=?",
                                  (json.dumps(meta), datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(), self.mid))
        N.save_note(self.store, meeting=self.mid, base_revision=0, text='Karar: deneme cuma',
                    anchors=[self.anchor(), {'id': 'a2', 'source': 'system', 'start': 40.0, 'end': 41.0}])
        first, second = N.get_note(self.store, meeting=self.mid)['anchors']
        self.assertEqual((first['status'], first['audio']), ('ok', True))
        self.assertEqual((second['status'], second['segments'], second['audio']), ('ok', [], True))   # no row there, but the audio is
        removed = storage_cleanup(self.store, self.data, days=30, dry_run=False)
        self.assertEqual([m['meeting'] for m in removed['meetings']], [self.mid]); self.assertFalse(folder.exists())
        first, second = N.get_note(self.store, meeting=self.mid)['anchors']
        self.assertEqual((first['status'], second['status']), ('ok', 'source_unavailable'))   # the transcript row still covers the first
        with self.store.db: self.store.db.execute('DELETE FROM segments WHERE meeting=?', (self.mid,))
        note = N.get_note(self.store, meeting=self.mid)
        self.assertEqual(note['text'], 'Karar: deneme cuma')
        self.assertEqual([a['status'] for a in note['anchors']], ['source_unavailable'] * 2)
        self.assertEqual([(a['segments'], a['audio'], a['segment_current']) for a in note['anchors']], [([], False, False), ([], False, None)])
        self.assertFalse(any(k in a for a in note['anchors'] for k in ('text', 'quote', 'excerpt')))

    def test_bad_anchors_are_refused_with_a_sentence(self):
        for bad in ([{'source': 'system', 'start': 5, 'end': 2}], [{'source': 'system', 'start': float('nan')}], [{'source': '../x', 'start': 1}], 'x'):
            with self.assertRaises(N.NoteError): N.save_note(self.store, meeting=self.mid, base_revision=0, text='x', anchors=bad)
        with self.assertRaises(N.NoteError) as caught: N.save_note(self.store, meeting='yok', base_revision=0, text='x')
        self.assertEqual(str(caught.exception), 'Toplantı bulunamadı.')


class PendingAndBridge(NoteFixture):
    def test_a_note_written_before_the_meeting_is_claimed_atomically(self):
        key = str(uuid.uuid4()).upper()
        out = dispatch({'action': 'note_save', 'pending_key': key, 'base_revision': 0, 'text': 'Hazırlık notu',
                        'anchors': [{'source': 'mic', 'start': 3.0, 'end': 4.0}]}, self.db)
        self.assertEqual(out['revision'], 1)
        pending = dispatch({'action': 'note_get', 'pending_key': key}, self.db)
        self.assertEqual((pending['meeting'], pending['anchors'][0]['status'], pending['anchors'][0]['verified']), (None, 'ok', False))
        mid = self.store.create_meeting('Yeni')
        self.assertFalse(dispatch({'action': 'note_get', 'meeting': mid}, self.db)['exists'])
        self.assertEqual(dispatch({'action': 'note_claim', 'pending_key': key, 'meeting': mid}, self.db), {'claimed': True, 'revision': 1})
        self.assertEqual(dispatch({'action': 'note_claim', 'pending_key': key, 'meeting': mid}, self.db)['already'], True)
        bound = dispatch({'action': 'note_get', 'meeting': mid}, self.db)
        self.assertEqual((bound['text'], bound['revision'], bound['pending_key']), ('Hazırlık notu', 1, key))
        # An editor still saving under the pending key lands on the same, now bound, note.
        self.assertEqual(dispatch({'action': 'note_save', 'pending_key': key, 'base_revision': 1, 'text': 'Hazırlık notu 2'}, self.db)['revision'], 2)
        self.assertEqual(dispatch({'action': 'note_get', 'meeting': mid}, self.db)['text'], 'Hazırlık notu 2')
        self.assertEqual(len(dispatch({'action': 'note_history', 'meeting': mid}, self.db)['revisions']), 2)
        # A meeting that already has its own note is never merged into.
        other = str(uuid.uuid4()); N.save_note(self.store, pending_key=other, base_revision=0, text='başka')
        self.assertEqual(dispatch({'action': 'note_claim', 'pending_key': other, 'meeting': mid}, self.db)['conflict'], True)
        with self.assertRaises(ValueError) as caught: dispatch({'action': 'note_claim', 'pending_key': key, 'meeting': self.mid}, self.db)
        self.assertEqual(str(caught.exception), 'Bu not başka bir toplantıya bağlı.')
        with self.assertRaises(ValueError) as caught: dispatch({'action': 'note_get', 'pending_key': '../../etc'}, self.db)
        self.assertEqual(str(caught.exception), 'Kayıt kimliği geçersiz.')

    def test_export_includes_notes_only_when_asked_and_says_so(self):
        N.save_note(self.store, meeting=self.mid, base_revision=0, text=SECRET, anchors=[self.anchor()])
        plain = self.data / 'plain.md'
        out = dispatch({'action': 'export', 'meeting': self.mid, 'path': str(plain), 'format': 'md'}, self.db)
        self.assertEqual((out['include_notes'], out['notes_included']), (False, False))
        self.assertNotIn('GIZLI-NOT', plain.read_text(encoding='utf-8'))
        for fmt in ('json', 'srt'):
            path = self.data / f'plain.{fmt}'; dispatch({'action': 'export', 'meeting': self.mid, 'path': str(path), 'format': fmt}, self.db)
            self.assertNotIn('GIZLI-NOT', path.read_text(encoding='utf-8'))
        with_notes = self.data / 'notes.md'
        out = dispatch({'action': 'export', 'meeting': self.mid, 'path': str(with_notes), 'format': 'md', 'include_notes': True}, self.db)
        self.assertEqual((out['include_notes'], out['notes_included']), (True, True))
        body = with_notes.read_text(encoding='utf-8')
        self.assertIn('## Notlarım', body); self.assertIn(SECRET, body); self.assertIn('00:00:10.500–00:00:13.000 · system', body)
        as_json = self.data / 'notes.json'
        dispatch({'action': 'export', 'meeting': self.mid, 'path': str(as_json), 'format': 'json', 'include_notes': True}, self.db)
        payload = json.loads(as_json.read_text(encoding='utf-8'))
        self.assertEqual((payload['notes']['text'], len(payload['segments'])), (SECRET, 2))
        with self.assertRaises(ValueError): dispatch({'action': 'export', 'meeting': self.mid, 'path': str(self.data / 'x.srt'), 'format': 'srt', 'include_notes': True}, self.db)
        self.assertFalse((self.data / 'x.srt').exists())

    def test_deleting_the_meeting_deletes_its_notes_and_revisions(self):
        N.save_note(self.store, meeting=self.mid, base_revision=0, text='bir'); N.save_note(self.store, meeting=self.mid, base_revision=1, text='iki')
        N.save_note(self.store, pending_key='kayit-1', base_revision=0, text='başka kayıt')
        dispatch({'action': 'delete_meeting', 'meeting': self.mid}, self.db)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM meeting_notes').fetchone()[0], 1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM note_revisions').fetchone()[0], 1)
        self.assertEqual(N.get_note(self.store, pending_key='kayit-1')['text'], 'başka kayıt')

    def test_a_database_without_notes_answers_without_creating_tables(self):
        self.assertEqual(dispatch({'action': 'note_get', 'meeting': self.mid}, self.db)['exists'], False)
        self.assertEqual(dispatch({'action': 'note_history', 'meeting': self.mid}, self.db), {'revisions': []})
        self.assertIsNone(self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='meeting_notes'").fetchone())


class NotesNeverLeaveInAPayload(CloudFixture):
    """Notes are not on the cloud whitelist (docs/EKIP.md). A synthetic private note is written next to a meeting
    and every payload builder that sends meeting data somewhere is run: none of them may carry it."""

    def test_analysis_team_cloud_and_diagnostics_payloads_never_carry_the_note(self):
        a = self.mac('a', share_reports=True, share_text=True)   # the widest sharing a user can pick
        with a.host():
            mid = a.store.create_meeting('Plan'); sid = self.segment(a.store, mid, 'Proje A için deneme cuma yapılacak.')
            a.store.status(mid, 'complete')
            N.save_note(a.store, meeting=mid, base_revision=0, text=SECRET, anchors=[{'source': 'system', 'start': 0.0, 'end': 4.0, 'segment': sid}])
            llm = CapturingLLM(sid, 'Proje A için deneme cuma yapılacak.')
            assistant.analyze(a.store, mid, llm)
            self.assertTrue(llm.prompts)
            for prompt in llm.prompts: self.assertNotIn('GIZLI-NOT', prompt); self.assertNotIn('saklıyor', prompt)
            E.record('ui', 'note_save: OperationalError', data_dir=a.data)
            self.assertIsNotNone(reports.write_meeting_report(a.store, mid, a.data))
            reports.write_heartbeat(a.store, a.data)
            a.sync()
            uploaded = [p for p in self.server.root.rglob('*') if p.is_file()]
            self.assertTrue(any('reports/' in p.as_posix() for p in uploaded))
            for path in uploaded: self.assertNotIn('GIZLI-NOT', path.read_text(encoding='utf-8'), path.name)
            # The meeting text itself did travel (share_text), so the check above is not vacuous.
            self.assertTrue(any('deneme cuma yapılacak' in p.read_text(encoding='utf-8') for p in uploaded))
            beat = json.dumps(reports.build_heartbeat(a.store, a.data), ensure_ascii=False)
            self.assertNotIn('GIZLI-NOT', beat)
            report = json.dumps(diagnostics.collect(a.data, None, a.data), ensure_ascii=False)
            self.assertNotIn('GIZLI-NOT', report)



class LiveAnchorOnTheAudioClock(NoteFixture):
    """Audit 2026-10-16: "Bu ana bağla" stored the app's elapsed wall seconds as audio time. The app's clock
    counts the permission dialog, sleep and relaunches; the audio timeline does not."""
    ORIGIN = 1_790_000_000.0

    def test_a_live_anchor_after_permission_wait_and_sleep_plays_the_audio_it_was_written_about(self):
        cap = self.data / 'rec'; cap.mkdir()
        lines = [{'event': 'permission', 'kind': 'microphone', 'state': 'requested', 'wall': self.ORIGIN - 40},
                 {'event': 'permission', 'kind': 'microphone', 'state': 'granted', 'wall': self.ORIGIN - 1},
                 {'event': 'started', 'wall': self.ORIGIN}]
        # 96 s of audio, a 300 s lid-close the audio clock never counted, then the recording carries on.
        for wall, start in [(t, t - 12) for t in range(12, 97, 12)] + [(396 + 12 * k, 96 + 12 * (k - 1)) for k in range(1, 10)]:
            lines.append({'event': 'chunk', 'source': 'system', 'path': str(cap / 'x.wav'), 'start': float(start), 'duration': 12.0, 'wall': self.ORIGIN + wall})
        (cap / 'capture-native.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in lines))
        mid = self.store.create_meeting('Canlı', {'capture_dir': str(cap)})
        # Pressed 500 wall seconds after the helper started; the app's own clock began 40 s earlier, at the dialog.
        anchor = {'id': 'canli', 'source': 'system', 'start': 525.0, 'end': 540.0, 'wall': self.ORIGIN + 500}
        N.save_note(self.store, meeting=mid, base_revision=0, text='Karar burada', anchors=[anchor])
        a = N.get_note(self.store, meeting=mid)['anchors'][0]
        self.assertEqual((a['start'], a['end'], a['clock'], a['wall']), (185.0, 200.0, 'audio', self.ORIGIN + 500))
        # The app saves what it read back: derived from the stamp again, never shifted twice.
        N.save_note(self.store, meeting=mid, base_revision=1, text='Karar burada.', anchors=[a])
        b = N.get_note(self.store, meeting=mid)['anchors'][0]
        self.assertEqual((b['start'], b['end']), (185.0, 200.0))
        # No journal to measure with (the fixture meeting has no capture folder): the app's estimate stays.
        N.save_note(self.store, meeting=self.mid, base_revision=0, text='x', anchors=[anchor])
        c = N.get_note(self.store, meeting=self.mid)['anchors'][0]
        self.assertEqual((c['start'], c['end']), (525.0, 540.0)); self.assertNotIn('clock', c)
        # Judge 2026-10-16: added at wall 400, four seconds after waking, BEFORE the first post-wake chunk closed
        # at 408. The earlier chunk had not seen the sleep; the later one has, and only it is believed here.
        early = {'id': 'uyanis', 'source': 'system', 'start': 425.0, 'end': 440.0, 'wall': self.ORIGIN + 400}
        self.assertEqual(N._on_audio_clock({'capture_dir': str(cap)}, early)['end'], 100.0)
        # Before the lid closed, the same pair of chunks keeps the link where it was.
        before = {**early, 'id': 'once', 'wall': self.ORIGIN + 90}
        self.assertEqual(N._on_audio_clock({'capture_dir': str(cap)}, before)['end'], 90.0)
        # A segment anchor is the segment's own time and is never re-derived.
        pinned = {**anchor, 'id': 'seg', 'segment': self.sid, 'start': 10.5, 'end': 13.0}
        self.assertEqual(N._on_audio_clock({'capture_dir': str(cap)}, pinned), pinned)


if __name__ == '__main__': unittest.main()
