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


if __name__ == '__main__':
    unittest.main()
