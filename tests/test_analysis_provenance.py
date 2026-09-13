"""Saved analyses identify the responders of this run, including parallel fallbacks."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from meeting_os import assistant, intelligence
from meeting_os.openrouter import OpenRouterLLM, OpenRouterError
from meeting_os.store import Store
from meeting_os.types import Segment


class AnalysisProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'meeting.sqlite')
        self.mid = self.store.create_meeting('Plan')
        self.store.add_segment(self.mid, Segment(0, 8, 'Arama indeksi yenilenecek.', 'system', 'S1'))
        self.store.status(self.mid, 'complete')
        self.fallback = 'openai/gpt-4.1-mini'

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def client(self, fail, barrier=None, usage=False):
        class Client:
            def _post(inner, endpoint, payload, **kwargs):
                rows = json.loads(payload['messages'][1]['content'])['transcript']
                if barrier and payload['model'] == 'deepseek/deepseek-v3.2':
                    barrier.wait(timeout=5)
                if payload['model'] == 'deepseek/deepseek-v3.2' and fail(rows):
                    raise OpenRouterError('unavailable')
                record = {key: [] for key in intelligence.CATEGORIES}
                record['summary'] = [{'text': row['text'], 'evidence': [
                    {'segment_id': row['segment_id'], 'quote': row['text']}]} for row in rows]
                response = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(record)}}]}
                if usage:
                    response['usage'] = {'prompt_tokens': 100, 'completion_tokens': 20, 'cost': .0001}
                return response
        return Client()

    def test_fallback_is_saved_even_when_provider_omits_usage(self):
        llm = OpenRouterLLM(self.client(lambda rows: True), 'deepseek/deepseek-v3.2')
        saved = assistant.analyze(self.store, self.mid, llm)
        self.assertEqual(saved['model'], 'openai/gpt-4.1-mini')
        self.assertEqual(saved['payload']['model_provenance'], {
            'requested': 'deepseek/deepseek-v3.2', 'responded': ['openai/gpt-4.1-mini']})
        self.assertEqual(llm.model_id, 'deepseek/deepseek-v3.2')

    def test_parallel_mixed_responders_are_saved_without_relabeling_shared_adapter(self):
        self.store.add_segment(self.mid, Segment(10, 18, 'Mobil bildirimler düzenlenecek.', 'system', 'S2'))
        llm = OpenRouterLLM(self.client(lambda rows: rows[0]['text'].startswith('Mobil'), threading.Barrier(2), True),
                            'deepseek/deepseek-v3.2')
        chunker = intelligence.chunks
        with patch.object(intelligence, 'chunks', lambda rows, model, **kw: chunker(rows, model, budget=1)):
            saved = assistant.analyze(self.store, self.mid, llm)
        self.assertEqual(saved['payload']['model_provenance']['responded'],
                         ['deepseek/deepseek-v3.2', 'openai/gpt-4.1-mini'])
        self.assertEqual(saved['model'], 'deepseek/deepseek-v3.2 + openai/gpt-4.1-mini')
        self.assertEqual(len(saved['payload']['summary']), 2)
        self.assertEqual(len(self.store.analysis_usage(self.mid)), 2)
        from meeting_os.reports import build_meeting_report
        from meeting_os.telemetry_schema import filter as filter_telemetry
        report = build_meeting_report(self.store, self.mid, Path(self.tmp.name))
        shared = filter_telemetry('report', report)
        self.assertEqual(shared['analysis'].get('model_provenance'), {
            'requested': 'deepseek/deepseek-v3.2',
            'responded': ['deepseek/deepseek-v3.2', 'openai/gpt-4.1-mini']})

    def test_forced_retry_does_not_inherit_previous_runs_models(self):
        llm = OpenRouterLLM(self.client(lambda rows: True), 'deepseek/deepseek-v3.2')
        assistant.analyze(self.store, self.mid, llm)
        llm.client = self.client(lambda rows: False)
        saved = assistant.analyze(self.store, self.mid, llm, force=True)
        self.assertEqual(saved['model'], 'deepseek/deepseek-v3.2')
        self.assertEqual(saved['payload']['model_provenance']['responded'], ['deepseek/deepseek-v3.2'])

    def test_rejected_response_model_is_not_an_author_of_the_saved_analysis(self):
        class Client:
            calls = 0
            def _post(inner, endpoint, payload, **kwargs):
                inner.calls += 1
                if inner.calls == 1:
                    # A transport-complete answer that fails the analysis parser must not receive credit.
                    return {'choices': [{'finish_reason': 'stop', 'message': {'content': 'invalid JSON'}}],
                            'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'cost': .0001}}
                if payload['model'] == 'deepseek/deepseek-v3.2':
                    raise OpenRouterError('unavailable')
                # A schema-nudge retry appends instructions after the initial transcript JSON.
                rows = json.JSONDecoder().raw_decode(payload['messages'][1]['content'])[0]['transcript']
                record = {key: [] for key in intelligence.CATEGORIES}
                record['summary'] = [{'text': row['text'], 'evidence': [
                    {'segment_id': row['segment_id'], 'quote': row['text']}]} for row in rows]
                return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(record)}}],
                        'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'cost': .0001}}
        llm = OpenRouterLLM(Client(), 'deepseek/deepseek-v3.2')
        saved = assistant.analyze(self.store, self.mid, llm)
        self.assertEqual(saved['model'], 'openai/gpt-4.1-mini')
        self.assertEqual(saved['payload']['model_provenance'], {
            'requested': 'deepseek/deepseek-v3.2', 'responded': ['openai/gpt-4.1-mini']})

        # Rejected content has no authorship credit but its paid response still belongs in the bill.
        self.assertEqual(len(self.store.analysis_usage(self.mid)), 2)
        self.assertAlmostEqual(self.store.analysis_cost_totals(self.mid)['cost'], .0002)

    def test_local_adapter_keeps_its_model_name(self):
        row = self.store.display_segments(self.mid)[0]
        class Local:
            model_id = 'local-fixture'
            def count(inner, text): return len(text)
            def complete(inner, *args, **kwargs):
                record = {key: [] for key in intelligence.CATEGORIES}
                record['summary'] = [{'text': row['text'], 'evidence': [
                    {'segment_id': row['id'], 'quote': row['text']}]}]
                return json.dumps(record)
        saved = assistant.analyze(self.store, self.mid, Local())
        self.assertEqual(saved['model'], 'local-fixture')


if __name__ == '__main__':
    unittest.main()
