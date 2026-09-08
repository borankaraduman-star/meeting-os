import unittest
from meeting_os.metrics import text_metrics

class EntityPrecisionTests(unittest.TestCase):
    def test_false_name_and_term_are_counted_in_fixed_universe(self):
        m=text_metrics('İpek checkout konuştu.', 'İpek Boran backlog konuştu.', ['İpek','checkout'], entity_universe=['İpek','Boran','checkout','backlog'])
        self.assertEqual((m['entity_true_positive'],m['entity_false_positive'],m['entity_false_negative']),(1,2,1))
        self.assertEqual(m['entity_precision'],1/3)
        self.assertEqual(m['entity_universe_recall'],.5)
    def test_missing_universe_cannot_claim_precision(self):
        self.assertIsNone(text_metrics('İpek','İpek Boran',['İpek'])['entity_precision'])
    def test_normalized_unique_types_and_word_boundaries(self):
        m=text_metrics('İPEK İpek sprint','İpek sprintler',entity_universe=['İpek','İPEK','sprint'])
        self.assertEqual(m['entity_true_positive'],1)
        self.assertEqual(m['entity_false_negative'],1)
        self.assertEqual(m['entity_precision'],1)
    def test_empty_prediction_undefined_precision(self):
        m=text_metrics('Boran','',entity_universe=['Boran'])
        self.assertIsNone(m['entity_precision'])
        self.assertEqual(m['entity_universe_recall'],0)
    def test_empty_reference_detects_unsupported_entity(self):
        m=text_metrics('','Boran',entity_universe=['Boran'])
        self.assertEqual(m['entity_false_positive'],1)
        self.assertEqual(m['entity_precision'],0)
        self.assertIsNone(m['entity_universe_recall'])
    def test_invalid_universe_rejected(self):
        for value in ('Boran',[None],[''],['!!!']):
            with self.subTest(value=value), self.assertRaises(ValueError):
                text_metrics('a','b',entity_universe=value)
    def test_bad_universe_fails_before_any_inference(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from meeting_os.benchmark import benchmark
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'ref.json').write_text(json.dumps({'text':'a','entity_universe':'invalid'}))
            (root/'manifest.json').write_text(json.dumps({'kind':'real','cases':[{'id':'a','session':'a','audio':'a.wav','reference':'ref.json'}],'configs':[{'name':'a'}]}))
            with patch('meeting_os.benchmark.subprocess.run') as worker:
                with self.assertRaises(ValueError):benchmark(root/'manifest.json',root/'out')
                worker.assert_not_called()
            self.assertFalse((root/'out').exists())
