import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meeting_os import glossary


def line(term, **rest):
    return json.dumps({'term': term, **rest}, ensure_ascii=False)


def terms(path):
    return [json.loads(l)['term'] for l in Path(path).read_text(encoding='utf-8').splitlines() if l.strip()]


class ImportTests(unittest.TestCase):
    """A file other Macs also write is merged, never overwritten: one import must not delete their terms."""

    def test_the_shared_icloud_file_is_merged_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'; data.mkdir()
            shared = Path(tmp) / 'icloud' / glossary.FILENAME
            shared.parent.mkdir(parents=True)
            shared.write_text(line('Trendyol') + '\n' + line('PMD') + '\n', encoding='utf-8')
            source = Path(tmp) / 'yeni.jsonl'
            source.write_text(line('Splendo') + '\n' + line('PMD', category='kısaltma') + '\n', encoding='utf-8')
            with patch.object(glossary, 'shared_path', return_value=shared):
                result = glossary.import_file(source, data, shared=True)
            self.assertEqual(result['path'], str(shared)); self.assertTrue(result['shared'])
            self.assertEqual(terms(shared), ['Trendyol', 'PMD', 'Splendo'])   # the other Mac's terms survive; what is there wins
            self.assertFalse((data / glossary.FILENAME).exists())

    def test_the_local_file_is_this_macs_own_and_is_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'; data.mkdir()
            local = data / glossary.FILENAME
            local.write_text(line('Eski') + '\n', encoding='utf-8')
            source = Path(tmp) / 'yeni.jsonl'
            source.write_text(line('Splendo') + '\n' + 'bozuk satır\n', encoding='utf-8')
            with patch.object(glossary, 'shared_path', return_value=None):
                result = glossary.import_file(source, data)
            self.assertEqual(terms(local), ['Splendo'])
            self.assertEqual((result['imported'], result['skipped'], result['shared']), (1, 1, False))

    def test_a_file_with_no_valid_line_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'; data.mkdir()
            source = Path(tmp) / 'bos.jsonl'; source.write_text('bozuk\n{"x":1}\n', encoding='utf-8')
            with patch.object(glossary, 'shared_path', return_value=None):
                with self.assertRaises(ValueError): glossary.import_file(source, data)

    def test_merge_keeps_what_is_already_there_and_reports_what_it_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / glossary.FILENAME
            path.write_text(line('PMD', expansion='Product Market Definition') + '\n', encoding='utf-8')
            entries = [glossary.parse_line(line('PMD', expansion='başka bir şey')), glossary.parse_line(line('Splendo'))]
            result = glossary.merge_into(path, entries)
            self.assertEqual((result['added'], result['total']), (1, 2))
            kept = [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
            self.assertEqual(kept[0]['expansion'], 'Product Market Definition')   # the file wins over the import


class RankHintTests(unittest.TestCase):
    """The 900-character budget did not grow; the order it is spent in did (Codex #7)."""

    def entry(self, term, source_count=None):
        return {'term': term, 'source_count': source_count, 'aliases': [], 'mishearings': [],
                'expansion': None, 'category': 'diğer', 'context': None, 'confidence': None}

    def test_the_ranking_is_evidence_first_and_deduplicates_by_folded_form(self):
        result = glossary.rank_hint_terms(
            repeat=['Trendyol'], recent=['Splendo'], verified=['Ayşe', 'trendyol'],
            team=['Jira'], entries=[self.entry('PMD', 1), self.entry('Kanban', 9)], vocabulary=['Boran', 'jira'])
        self.assertEqual(result['included'], ['Trendyol', 'Splendo', 'Ayşe', 'Jira', 'Kanban', 'PMD', 'Boran'])
        self.assertEqual(result['hint'], 'Trendyol, Splendo, Ayşe, Jira, Kanban, PMD, Boran')
        self.assertEqual(result['excluded'], 0)
        self.assertEqual(result['candidates'], 7)   # "trendyol" and "jira" folded onto terms already ranked
        self.assertEqual(result['tiers'], {'repeat': 1, 'recent': 1, 'verified': 1, 'team': 1, 'glossary': 2, 'vocabulary': 1})

    def test_glossary_terms_are_ordered_by_source_count_then_file_order(self):
        result = glossary.rank_hint_terms(entries=[self.entry('Bir'), self.entry('İki', 2), self.entry('Üç', 2), self.entry('Dört', 5)])
        self.assertEqual(result['included'], ['Dört', 'İki', 'Üç', 'Bir'])

    def test_the_budget_is_the_budget_and_what_did_not_fit_is_counted(self):
        result = glossary.rank_hint_terms(repeat=['Trendyol'], vocabulary=['Splendo', 'Ayşe'], limit=12)
        self.assertEqual(result['included'], ['Trendyol'])     # 8 characters; "Splendo" would need 8 + 2 more
        self.assertEqual((result['excluded'], result['characters']), (2, 8))
        self.assertLessEqual(len(result['hint']), 12)

    def test_an_empty_ranking_is_an_empty_hint_not_an_error(self):
        result = glossary.rank_hint_terms()
        self.assertEqual((result['hint'], result['included'], result['excluded'], result['limit']), ('', [], 0, glossary.HINT_LIMIT))

    def test_ranking_is_pure_and_reads_nothing(self):
        """No store, no clock, no disk: the same input gives the same answer, twice."""
        args = {'recent': ['Splendo'], 'entries': [self.entry('PMD')], 'vocabulary': ['Boran']}
        self.assertEqual(glossary.rank_hint_terms(**args), glossary.rank_hint_terms(**args))


class RankedHintTests(unittest.TestCase):
    """The gathering half: what this Mac knows, in the order `rank_hint_terms` wants it."""

    def store(self, tmp):
        from meeting_os.store import Store
        return Store(Path(tmp) / 'meeting-os.sqlite')

    def test_a_taught_word_outranks_the_glossary_and_the_vocabulary(self):
        from meeting_os import correction_memory as cm
        from meeting_os.types import Segment
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); (data / glossary.FILENAME).write_text(line('PMD') + '\n', encoding='utf-8')
            (data / 'vocabulary.txt').write_text('Boran\n', encoding='utf-8')
            store = self.store(tmp)
            mid = store.create_meeting('a'); store.add_segment(mid, Segment(0, 4, 'Spilendo demosu.', 'system', 'system:S1'))
            with patch.object(glossary, 'shared_path', return_value=None):
                cm.teach(store, mid, 'Spilendo', 'Splendo', data)
                cm.dismiss_word(store, mid, 'demosu')
                entries, from_file = glossary.load(data, with_counts=True, store=store)
                ranked = glossary.ranked_hint(store, entries, data_dir=data, from_file=from_file)
            self.assertEqual(ranked['included'][0], 'Splendo')        # taught here, in the last 30 days
            self.assertIn('demosu', ranked['included'])               # "bu doğru" is a locally verified spelling
            self.assertLess(ranked['included'].index('Splendo'), ranked['included'].index('PMD'))
            self.assertEqual(ranked['excluded'], 0)
            store.close()

    def test_a_word_the_raw_transcript_got_wrong_again_goes_first(self):
        """The hint exists for exactly this word: taught, and the model wrote the old spelling anyway."""
        from meeting_os import correction_memory as cm
        from meeting_os.types import Segment
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / 'vocabulary.txt').write_text('Boran\n', encoding='utf-8')
            store = self.store(tmp)
            with patch.object(glossary, 'shared_path', return_value=None):
                first = store.create_meeting('ilk'); store.add_segment(first, Segment(0, 4, 'Spilendo demosu.', 'system', 'system:S1'))
                cm.teach(store, first, 'Spilendo', 'Splendo', data)
                cm.teach(store, first, 'Trendyoll', 'Trendyol', data)
                later = store.create_meeting('sonra')   # created after both rules: only one of them goes wrong again
                store.add_segment(later, Segment(0, 4, 'Yine Spilendo dedi.', 'system', 'system:S1'))
                store.status(later, 'complete')
                entries, from_file = glossary.load(data, with_counts=True, store=store)
                ranked = glossary.ranked_hint(store, entries, data_dir=data, from_file=from_file)
            self.assertEqual(ranked['included'][0], 'Splendo')
            self.assertEqual(ranked['tiers']['repeat'], 1)
            store.close()

    def test_with_no_store_the_hint_is_the_plain_glossary_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); (data / glossary.FILENAME).write_text(line('PMD') + '\n' + line('Trendyol') + '\n', encoding='utf-8')
            (data / 'vocabulary.txt').write_text('Boran\n', encoding='utf-8')
            with patch.object(glossary, 'shared_path', return_value=None):
                entries, from_file = glossary.load(data, with_counts=True)
                ranked = glossary.ranked_hint(None, entries, data_dir=data, from_file=from_file)
            self.assertEqual(ranked['hint'], 'PMD, Trendyol, Boran')
            self.assertEqual(ranked['hint'], glossary.stt_hint(entries))


if __name__ == '__main__':
    unittest.main()
