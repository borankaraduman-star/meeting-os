"""The team folder as one knowledge base: what one Mac learns, every Mac learns.

Two "Macs" here are two data folders and two databases pointed at the same temp team folder, with
`host_name` patched to tell them apart — exactly the shape three or five people in an office have.
Nothing in this file touches iCloud or the real data folder: every path is a temp directory.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meeting_os import correction_memory as cm
from meeting_os import glossary, reports, team_knowledge as tk
from meeting_os.store import Store
from meeting_os.types import Segment


class TeamFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / 'ekip'; self.root.mkdir()
        self.stores = []

    def tearDown(self):
        for store in self.stores: store.close()
        self._tmp.cleanup()

    def mac(self, name, **settings):
        """One Mac: its own data folder, its own database, the shared team folder."""
        data = self.tmp / name; data.mkdir()
        (data / 'vocabulary.txt').write_text('Jira\n', encoding='utf-8')   # a fixed list; the repo seed is never copied
        saved = reports.save_settings(data, {'team_dir': str(self.root), **settings})
        store = Store(data / 'meeting-os.sqlite'); self.stores.append(store)
        return data, store, saved

    def segment(self, store, mid, text, start=0.0):
        return store.add_segment(mid, Segment(start, start + 4, text, 'system', 'system:S1'))

    def words_file(self):
        path = self.root / tk.WORDS_FILE
        return [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()] if path.is_file() else []


class WordTests(TeamFixture):
    def test_a_word_one_mac_teaches_reaches_the_other_and_fixes_its_meetings(self):
        data_a, a, _ = self.mac('a'); data_b, b, settings_b = self.mac('b')
        mid = a.create_meeting('a'); self.segment(a, mid, 'Trendyoll ile görüştük.')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.teach(a, mid, 'Trendyoll', 'Trendyol', data_a)   # teaching publishes on its own
        self.assertEqual([(e['original'], e['replacement'], e['host']) for e in self.words_file()],
                         [('Trendyoll', 'Trendyol', 'mac-a')])
        with patch.object(tk, 'host_name', return_value='mac-b'):
            self.assertEqual(tk.pull_words(b, settings_b, data_b), {'imported': 1, 'hosts': 1})
            rule = cm.word_rules(b)[0]
            self.assertEqual((rule['source'], rule['host'], rule['active'], rule['enabled']), ('team', 'mac-a', True, True))
            other = b.create_meeting('b'); self.segment(b, other, 'Trendyoll güzel.')
            self.assertEqual(cm.apply_rules(b, other, data_dir=data_b)['fixes'], 1)
            self.assertEqual(b.segments(other)[0]['text'], 'Trendyol güzel.')

    def test_a_team_word_rewrites_the_exact_spelling_only(self):
        """Same bar as a taught rule: a near-miss is a Kontrol suggestion, never an automatic rewrite."""
        data_a, a, _ = self.mac('a'); data_b, b, settings_b = self.mac('b')
        mid = a.create_meeting('a'); self.segment(a, mid, 'Trendyoll.')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.teach(a, mid, 'Trendyoll', 'Trendyol', data_a)
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.pull_words(b, settings_b, data_b)
            other = b.create_meeting('b'); self.segment(b, other, 'Trendyolll ve Trendyoll ve Trendyoll’a')
            cm.apply_rules(b, other, data_dir=data_b)
            self.assertEqual(b.segments(other)[0]['text'], 'Trendyolll ve Trendyol ve Trendyol’a')

    def test_the_local_spelling_wins_and_the_teammates_stays_visible(self):
        data_a, a, _ = self.mac('a'); data_b, b, settings_b = self.mac('b')
        mid = a.create_meeting('a'); self.segment(a, mid, 'Ayşen geldi.')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.teach(a, mid, 'Ayşen', 'Ayşe Nur', data_a)
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.pull_words(b, settings_b, data_b)
            own = b.create_meeting('b'); self.segment(b, own, 'Ayşen geldi.')
            cm.teach(b, own, 'Ayşen', 'Ayşe', data_b)   # this Mac's user has their own answer
            rules = {r['source']: r for r in cm.word_rules(b)}
            self.assertEqual(rules['taught']['replacement'], 'Ayşe')
            self.assertEqual((rules['team']['replacement'], rules['team']['host'], rules['team']['active']), ('Ayşe Nur', 'mac-a', False))
            later = b.create_meeting('c'); self.segment(b, later, 'Ayşen geldi.')
            cm.apply_rules(b, later, data_dir=data_b)
            self.assertEqual(b.segments(later)[0]['text'], 'Ayşe geldi.')
        # …and both Macs still share their own line: neither publish deleted the other's
        self.assertEqual({(e['host'], e['replacement']) for e in self.words_file()},
                         {('mac-a', 'Ayşe Nur'), ('mac-b', 'Ayşe')})

    def test_between_two_teammates_the_newest_word_wins(self):
        data_b, b, settings_b = self.mac('b')
        path = self.root / tk.WORDS_FILE
        path.write_text('\n'.join(json.dumps(e, ensure_ascii=False) for e in [
            {'original': 'Trendyoll', 'replacement': 'Trendyol', 'host': 'mac-a', 'created': '2026-01-01', 'updated': '2026-01-01'},
            {'original': 'Trendyoll', 'replacement': 'Trendyol A.Ş.', 'host': 'mac-c', 'created': '2026-02-01', 'updated': '2026-02-01'}]) + '\n', encoding='utf-8')
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.pull_words(b, settings_b, data_b)
            active = [r for r in tk.team_rules(b) if r['active']]
            self.assertEqual([(r['host'], r['replacement']) for r in active], [('mac-c', 'Trendyol A.Ş.')])
            self.assertEqual(len(cm.word_rules(b)), 2)   # the loser is listed too, with the Mac it came from

    def test_a_team_word_switched_off_here_is_not_applied_and_the_shared_file_is_untouched(self):
        data_a, a, _ = self.mac('a'); data_b, b, settings_b = self.mac('b')
        mid = a.create_meeting('a'); self.segment(a, mid, 'Trendyoll.')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.teach(a, mid, 'Trendyoll', 'Trendyol', data_a)
        before = self.words_file()
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.pull_words(b, settings_b, data_b)
            tk.team_word_toggle(b, 'Trendyoll', 'mac-a', enabled=False)
            self.assertEqual([r['active'] for r in tk.team_rules(b)], [False])
            other = b.create_meeting('b'); self.segment(b, other, 'Trendyoll güzel.')
            self.assertEqual(cm.apply_rules(b, other, data_dir=data_b), {'segments': 0, 'fixes': 0, 'rules': 0})
            self.assertEqual(b.segments(other)[0]['text'], 'Trendyoll güzel.')
            row = cm.word_rules(b)[0]
            self.assertEqual((row['enabled'], row['active'], row['host']), (False, False, 'mac-a'))
            tk.publish_words(b, settings_b, data_b)
        self.assertEqual(self.words_file(), before)   # switching off is local: the teammate keeps sharing it
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.pull_words(b, settings_b, data_b)   # a later pull must not switch it back on
            self.assertEqual([r['enabled'] for r in tk.team_rules(b)], [False])

    def test_forgetting_a_word_removes_this_macs_line_only(self):
        data_a, a, _ = self.mac('a'); data_b, b, settings_b = self.mac('b')
        mid = b.create_meeting('b'); self.segment(b, mid, 'Splendoo çıktı.')
        with patch.object(tk, 'host_name', return_value='mac-b'):
            cm.teach(b, mid, 'Splendoo', 'Splendo', data_b)
        mid_a = a.create_meeting('a'); self.segment(a, mid_a, 'Trendyoll ile.')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.teach(a, mid_a, 'Trendyoll', 'Trendyol', data_a)
            cm.forget(a, 'Trendyoll', data_a)
        self.assertEqual([(e['host'], e['original']) for e in self.words_file()], [('mac-b', 'Splendoo')])

    def test_a_word_a_teammate_forgot_stops_applying_here_too(self):
        data_a, a, _ = self.mac('a'); data_b, b, settings_b = self.mac('b')
        mid = a.create_meeting('a'); self.segment(a, mid, 'Trendyoll.')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.teach(a, mid, 'Trendyoll', 'Trendyol', data_a)
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.pull_words(b, settings_b, data_b)
            self.assertEqual(len(tk.team_rules(b)), 1)
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.forget(a, 'Trendyoll', data_a)
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.pull_words(b, settings_b, data_b)
            self.assertEqual(tk.team_rules(b), [])

    def test_the_team_spelling_joins_the_asr_hint_but_never_the_vocabulary_file(self):
        data_a, a, _ = self.mac('a'); data_b, b, settings_b = self.mac('b')
        mid = a.create_meeting('a'); self.segment(a, mid, 'Splendoo çıktı.')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.teach(a, mid, 'Splendoo', 'Splendo', data_a)
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.pull_words(b, settings_b, data_b)
        with patch.object(glossary, 'shared_path', return_value=None):
            terms = [e['term'] for e in glossary.load(data_b, store=b)]
        self.assertIn('Splendo', terms)
        self.assertEqual(cm.vocabulary_terms(data_b), ['Jira'])   # the file on this disk stays the user's own list

    def test_publishing_is_off_when_the_user_said_so(self):
        data_a, a, _ = self.mac('a', share_words=False)
        mid = a.create_meeting('a'); self.segment(a, mid, 'Trendyoll.')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.teach(a, mid, 'Trendyoll', 'Trendyol', data_a)
        self.assertFalse((self.root / tk.WORDS_FILE).exists())

    def test_nothing_is_shared_without_a_team_folder(self):
        """No team folder and no iCloud fall-back for a private data folder: `words_path` is simply None."""
        data = self.tmp / 'yalnız'; data.mkdir()
        settings = reports.load_settings(data)
        self.assertIsNone(tk.words_path(settings, data))
        self.assertIsNone(tk.profiles_dir(settings, data))


class ProfileTests(TeamFixture):
    VECTOR = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.4, 0.2]
    OTHER = [0.9, 0.1, 0.4, 0.2, 0.7, 0.3, 0.5, 0.8, 0.2, 0.6, 0.1, 0.3]

    def test_a_named_voice_reaches_the_other_mac_and_import_is_idempotent(self):
        data_a, a, settings_a = self.mac('a'); data_b, b, settings_b = self.mac('b')
        a.enroll('Ayşe', self.VECTOR, 'emb-1', 12.0, 'toplanti-1:5')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            self.assertEqual(tk.publish_profiles(a, settings_a, data_a)['published'], 1)
        with patch.object(tk, 'host_name', return_value='mac-b'):
            self.assertEqual(tk.pull_profiles(b, settings_b, data_b)['imported'], 1)
            self.assertEqual(tk.pull_profiles(b, settings_b, data_b)['imported'], 0)   # same file, nothing new
        self.assertEqual([(p['name'], p['samples']) for p in b.profiles()], [('Ayşe', 1)])
        sample = b.profile_samples('Ayşe')[0]
        self.assertEqual((sample['kind'], sample['host'], sample['meeting']), ('ekip', 'mac-a', None))
        # …and this Mac does not re-publish what it merely received: a line has one owner
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.publish_profiles(b, settings_b, data_b)
        self.assertEqual(tk.read_profiles(self.root / tk.PROFILES_DIR / 'mac-b.jsonl'), [])

    def test_a_team_voice_is_identified_like_any_other(self):
        data_a, a, settings_a = self.mac('a'); data_b, b, settings_b = self.mac('b')
        a.enroll('Ayşe', self.VECTOR, 'emb-1', 12.0, 'toplanti-1:5')
        with patch.object(tk, 'host_name', return_value='mac-a'): tk.publish_profiles(a, settings_a, data_a)
        with patch.object(tk, 'host_name', return_value='mac-b'): tk.pull_profiles(b, settings_b, data_b)
        self.assertEqual(b.identify(self.VECTOR, 'emb-1')['name'], 'Ayşe')

    def test_the_file_carries_no_audio_no_meeting_and_no_title(self):
        data_a, a, settings_a = self.mac('a')
        mid = a.create_meeting('Gizli müşteri görüşmesi')
        self.segment(a, mid, 'Bu cümle hiçbir yere gitmemeli.')
        a.enroll('Ayşe', self.VECTOR, 'emb-1', 12.0, f'{mid}:5')
        with patch.object(tk, 'host_name', return_value='mac-a'): tk.publish_profiles(a, settings_a, data_a)
        text = (self.root / tk.PROFILES_DIR / 'mac-a.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('Gizli müşteri görüşmesi', text)
        self.assertNotIn(mid, text)
        self.assertNotIn('Bu cümle', text)
        self.assertEqual(sorted(json.loads(text.splitlines()[0])), ['created', 'duration', 'host', 'model', 'name', 'vector'])

    def test_a_name_this_mac_rejected_is_not_imported(self):
        data_a, a, settings_a = self.mac('a'); data_b, b, settings_b = self.mac('b')
        a.enroll('Ayşe', self.VECTOR, 'emb-1', 12.0, 'toplanti-1:5')
        with patch.object(tk, 'host_name', return_value='mac-a'): tk.publish_profiles(a, settings_a, data_a)
        with b.db:
            b.db.execute('INSERT INTO rejections(name,model,vector,provenance,created) VALUES(?,?,?,?,?)',
                         ('Ayşe', 'emb-1', json.dumps(self.OTHER), 'toplanti-9:mark', '2026-01-01'))
        with patch.object(tk, 'host_name', return_value='mac-b'):
            self.assertEqual(tk.pull_profiles(b, settings_b, data_b), {'imported': 0, 'hosts': 1, 'skipped': 1})
        self.assertEqual(b.profiles(), [])

    def test_deleting_a_person_takes_their_team_samples_and_blocks_the_re_import(self):
        data_a, a, settings_a = self.mac('a'); data_b, b, settings_b = self.mac('b')
        a.enroll('Ayşe', self.VECTOR, 'emb-1', 12.0, 'toplanti-1:5')
        with patch.object(tk, 'host_name', return_value='mac-a'): tk.publish_profiles(a, settings_a, data_a)
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.pull_profiles(b, settings_b, data_b)
            b.delete_profile('Ayşe'); tk.block_profile(b, 'Ayşe')
            self.assertEqual(b.profiles(), [])
            self.assertEqual(tk.pull_profiles(b, settings_b, data_b)['imported'], 0)
            self.assertEqual(b.profiles(), [])
            tk.unblock_profile(b, 'ayse')   # the block is by folded name, like every other name comparison
            self.assertEqual(tk.pull_profiles(b, settings_b, data_b)['imported'], 1)

    def test_a_local_sample_is_never_overwritten_and_the_cap_holds(self):
        data_a, a, settings_a = self.mac('a'); data_b, b, settings_b = self.mac('b')
        for i in range(tk.PROFILE_CAP + 3):
            a.enroll('Ayşe', [v + i / 100 for v in self.VECTOR], 'emb-1', 10.0 + i, f'toplanti-{i}:5')
        b.enroll('Ayşe', self.OTHER, 'emb-1', 20.0, 'yerel-1:2')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            self.assertEqual(tk.publish_profiles(a, settings_a, data_a)['published'], tk.PROFILE_CAP)
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.pull_profiles(b, settings_b, data_b)
        samples = b.profile_samples('Ayşe')
        self.assertEqual(len(samples), tk.PROFILE_CAP)
        self.assertEqual(samples[0]['provenance'], 'yerel-1:2')   # the local sample is still there, first and untouched

    def test_sharing_profiles_can_be_switched_off(self):
        data_a, a, settings_a = self.mac('a', share_profiles=False)
        a.enroll('Ayşe', self.VECTOR, 'emb-1', 12.0, 'toplanti-1:5')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            self.assertEqual(tk.publish_profiles(a, settings_a, data_a), {'published': 0, 'path': None})
        self.assertFalse((self.root / tk.PROFILES_DIR).exists())

    def test_a_broken_or_hostile_line_is_ignored_not_imported(self):
        data_b, b, settings_b = self.mac('b')
        directory = self.root / tk.PROFILES_DIR; directory.mkdir(parents=True)
        (directory / 'mac-a.jsonl').write_text('\n'.join([
            'düz metin', '{"name":"Ayşe"}',
            json.dumps({'name': 'Kısa', 'model': 'emb-1', 'vector': self.VECTOR, 'duration': 1.0, 'host': 'mac-a'}),
            json.dumps({'name': 'Ayşe', 'model': 'emb-1', 'vector': ['a'] * 12, 'duration': 9.0, 'host': 'mac-a'}),
            json.dumps({'name': 'Ayşe', 'model': 'emb-1', 'vector': self.VECTOR, 'duration': 9.0, 'host': 'mac-a'})]) + '\n', encoding='utf-8')
        with patch.object(tk, 'host_name', return_value='mac-b'):
            self.assertEqual(tk.pull_profiles(b, settings_b, data_b)['imported'], 1)
        self.assertEqual([(p['name'], p['samples']) for p in b.profiles()], [('Ayşe', 1)])


class SyncTests(TeamFixture):
    def test_sync_publishes_and_pulls_in_one_pass(self):
        data_a, a, _ = self.mac('a'); data_b, b, _ = self.mac('b')
        mid = a.create_meeting('a'); self.segment(a, mid, 'Trendyoll.')
        a.enroll('Ayşe', ProfileTests.VECTOR, 'emb-1', 12.0, 'toplanti-1:5')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.teach(a, mid, 'Trendyoll', 'Trendyol', data_a); tk.sync(a, data_a)
        with patch.object(tk, 'host_name', return_value='mac-b'):
            result = tk.sync(b, data_b)
        self.assertEqual((result['words']['imported'], result['profiles']['imported']), (1, 1))

    def test_an_unreachable_team_folder_never_raises(self):
        data_a, a, settings = self.mac('a')
        mid = a.create_meeting('a'); self.segment(a, mid, 'Trendyoll.')
        with patch.object(tk, 'host_name', return_value='mac-a'), patch.object(tk, '_write', side_effect=OSError('yok')):
            self.assertEqual(cm.teach(a, mid, 'Trendyoll', 'Trendyol', data_a)['fixes'], 1)
            self.assertIn('words_error', tk.sync(a, data_a))


class BackfillTests(TeamFixture):
    """The Mac that has been in use for months is the whole point: everything it already knows has to reach the
    folder on the first pass, not only what it learns from now on."""

    def test_the_first_sync_publishes_everything_this_mac_already_knew(self):
        data_a = self.tmp / 'a'; data_a.mkdir()
        (data_a / 'vocabulary.txt').write_text('Jira\n', encoding='utf-8')
        a = Store(data_a / 'meeting-os.sqlite'); self.stores.append(a)
        # months of use with no team folder at all: nothing was ever published
        mid = a.create_meeting('eski')
        for wrong, right in (('Trendyoll', 'Trendyol'), ('Splendoo', 'Splendo'), ('Purodakk', 'Purodak')):
            self.segment(a, mid, f'{wrong} geçti.')
            cm.teach(a, mid, wrong, right, data_a)
        for i in range(3):
            a.enroll(f'Kişi {i}', [v + i for v in ProfileTests.VECTOR], 'emb-1', 9.0 + i, f'eski-{i}:5')
        self.assertFalse((self.root / tk.WORDS_FILE).exists())
        # …and then the team folder is picked
        settings = reports.save_settings(data_a, {'team_dir': str(self.root)})
        with patch.object(tk, 'host_name', return_value='mac-a'):
            first = tk.sync(a, data_a, settings=settings)
            self.assertEqual((first['words']['published'], first['profiles']['published']), (3, 3))
            second = tk.sync(a, data_a, settings=settings)   # idempotent: the same state writes nothing new
            self.assertTrue(second['words']['unchanged'] and second['profiles']['unchanged'])
        self.assertEqual(len(self.words_file()), 3)
        self.assertEqual(len(tk.read_profiles(self.root / tk.PROFILES_DIR / 'mac-a.jsonl')), 3)

    def test_the_summary_counts_both_directions_and_reaches_the_heartbeat(self):
        data_a, a, settings_a = self.mac('a'); data_b, b, settings_b = self.mac('b')
        mid = a.create_meeting('a'); self.segment(a, mid, 'Trendyoll.')
        a.enroll('Ayşe', ProfileTests.VECTOR, 'emb-1', 12.0, 'toplanti-1:5')
        with patch.object(tk, 'host_name', return_value='mac-a'):
            cm.teach(a, mid, 'Trendyoll', 'Trendyol', data_a); tk.sync(a, data_a)
            self.assertEqual(tk.team_summary(a), {'profiles': 0, 'people': 0, 'words': 0, 'shared_profiles': 1, 'shared_words': 1, 'line': ''})
        with patch.object(tk, 'host_name', return_value='mac-b'):
            tk.sync(b, data_b)
            summary = tk.team_summary(b)
            self.assertEqual((summary['profiles'], summary['people'], summary['words'], summary['line']),
                             (1, 1, 1, 'ekipten 1 profil, 1 kelime'))
            beat = reports.build_heartbeat(b, data_b)
        self.assertEqual((beat['team_profiles'], beat['team_words'], beat['shared_profiles'], beat['shared_words']), (1, 1, 0, 0))
        self.assertEqual([p['team_samples'] for p in b.profile_health()], [1])


class SettingsTests(unittest.TestCase):
    def test_both_halves_of_the_team_knowledge_base_are_on_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = reports.load_settings(Path(tmp))
            self.assertEqual((settings['share_words'], settings['share_profiles']), (True, True))
            saved = reports.save_settings(Path(tmp), {'share_words': False, 'share_profiles': False})
            self.assertEqual((saved['share_words'], saved['share_profiles']), (False, False))
            self.assertEqual(reports.load_settings(Path(tmp))['share_words'], False)
            # a non-bool is refused, like every other switch
            self.assertEqual(reports.save_settings(Path(tmp), {'share_words': 'evet'})['share_words'], False)


if __name__ == '__main__':
    unittest.main()
