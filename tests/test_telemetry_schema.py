"""The one door diagnostics leave by.

`test_team_cloud.DiagnosticsContractTests` proves the end-to-end promise — a token, a person, a sentence and a
home path pushed into the journal, a report and the heartbeat, and none of them on the fake server. These are
the unit-level rules underneath it, so a future change breaks a small readable test before it breaks that one.
"""
import unittest

from meeting_os import telemetry_schema as T


class FilterTests(unittest.TestCase):
    def test_an_unlisted_key_does_not_travel_however_harmless_it_looks(self):
        out = T.filter('heartbeat', {'meetings': 3, 'notes': 'Ayşe ile toplantı', 'pad': 'x' * 10})
        self.assertEqual(out, {'meetings': 3})

    def test_an_unknown_payload_kind_produces_nothing(self):
        self.assertEqual(T.filter('mystery', {'meetings': 3}), {})
        self.assertEqual(T.filter('heartbeat', 'not a payload'), {})

    def test_the_two_free_text_diagnostics_paths_are_closed(self):
        beat = {'errors': ['Traceback', 'ValueError: /Users/boran/Belgeler'],
                'error_journal': {'last_24h': {'job': 2}, 'crashes_24h': 1,
                                  'codes': {'ValueError': 2},
                                  'last': [{'time': 't', 'kind': 'job', 'message': 'Ayşe Yılmaz'}]},
                'update_status': {'state': 'failed', 'time': '2026-09-11T08:00:00+00:00', 'message': 'sk-or-v1-gizli'},
                'probe': {'ok': False, 'failed': ['ffmpeg'], 'warnings': [], 'at': '2026-09-11T08:00:00+00:00',
                          'summary': 'Öz-test: ffmpeg'},
                'team_cloud': {'last_ok': None, 'last_error': 'auth: anahtar geçersiz', 'last_error_code': 'auth',
                               'hosts': ['a'], 'device': 'abc123'}}
        out = T.filter('heartbeat', beat)
        self.assertNotIn('errors', out)
        self.assertNotIn('last', out['error_journal'])
        self.assertEqual(out['error_journal']['codes'], {'ValueError': 2})
        self.assertEqual(sorted(out['update_status']), ['state', 'time'])
        self.assertNotIn('summary', out['probe'])
        self.assertNotIn('last_error', out['team_cloud'])
        self.assertEqual(out['team_cloud']['last_error_code'], 'auth')

    def test_a_report_keeps_its_numbers_and_loses_its_log_lines(self):
        report = {'report_version': 1, 'duration_seconds': 612.5, 'review_queue': {'word': 2},
                  'errors': ['ValueError: bir şey'], 'identity_error': 'Ses profili eşleştirmesi yapılamadı',
                  'title': 'Bütçe toplantısı', 'transcript': [{'text': 'gizli'}],
                  'scorecard': {'auto_verified': 1, 'auto_unreviewed': 4, 'auto_precision': 1.0}}
        out = T.filter('report', report)
        self.assertEqual(out['duration_seconds'], 612.5)
        self.assertEqual(out['review_queue'], {'word': 2})
        self.assertEqual(out['scorecard'], {'auto_verified': 1, 'auto_unreviewed': 4, 'auto_precision': 1.0})
        for gone in ('errors', 'identity_error', 'transcript', 'title'):
            self.assertNotIn(gone, out, gone)

    def test_a_title_may_be_empty_and_nothing_else(self):
        """`NULL` keeps the KEY (the fleet view reads `title` and expects it to be there) and refuses any value."""
        self.assertEqual(T.filter('report', {'title': None}), {'title': None})
        self.assertEqual(T.filter('report', {'title': 'Bütçe'}), {})

    def test_a_path_is_dropped_whole_rather_than_shortened(self):
        self.assertEqual(T.filter('heartbeat', {'host': '/Users/boran/Mac'}), {})
        self.assertEqual(T.filter('heartbeat', {'host': 'boran-mac'}), {'host': 'boran-mac'})

    def test_a_number_field_refuses_a_string_and_a_string_field_refuses_a_sentence(self):
        self.assertEqual(T.filter('heartbeat', {'meetings': '3'}), {})
        self.assertEqual(T.filter('heartbeat', {'macos': '26.5.2'}), {'macos': '26.5.2'})
        self.assertEqual(T.filter('heartbeat', {'macos': 'bu bir cümledir ve sürüm değildir'}), {})
        self.assertEqual(T.filter('heartbeat', {'thermal': float('nan')}), {})
        self.assertEqual(T.filter('heartbeat', {'signing_partition': 1}), {})   # 1 is not a flag

    def test_not_measured_is_not_a_leak(self):
        out = T.filter('heartbeat', {'thermal': None, 'last_complete': None, 'recording': None})
        self.assertEqual(out, {'thermal': None, 'last_complete': None, 'recording': None})

    def test_a_map_key_is_data_and_is_bounded_too(self):
        out = T.filter('heartbeat', {'statuses': {'complete': 2, 'x' * 200: 1, 'çok\nuzun': 1, 'ok': 'iki'}})
        self.assertEqual(out['statuses'], {'complete': 2})

    def test_the_learning_block_is_counts_and_only_counts(self):
        out = T.filter('heartbeat', {'learning': {'days': 7, 'events': 3, 'undo': 1,
                                                  'actions': {'word_teach': 2, 'undo': 1},
                                                  'names': {'verified': 1, 'falsified': 0, 'unreviewed': 9},
                                                  'words': ['trendyol'], 'meetings': ['abc123']}})
        self.assertEqual(out['learning'], {'days': 7, 'events': 3, 'undo': 1,
                                           'actions': {'word_teach': 2, 'undo': 1},
                                           'names': {'verified': 1, 'falsified': 0, 'unreviewed': 9}})

    def test_an_error_export_line_carries_flags_numbers_and_identifiers_but_no_prose(self):
        line = {'time': '2026-09-11T08:00:00+00:00', 'kind': 'cloud', 'version': '1.2.80', 'code': 'http-429',
                'context': {'http': 429, 'model': 'openai/gpt-4.1-mini', 'supervised': True,
                            'state': 'Ayşe Yılmaz aradı', 'seconds': 3.5}}
        out = T.filter('errors_export', line)
        self.assertEqual(out['code'], 'http-429')
        self.assertEqual(out['context'], {'http': 429, 'model': 'openai/gpt-4.1-mini', 'supervised': True, 'seconds': 3.5})

    def test_which_schema_a_file_is_judged_by(self):
        self.assertEqual(T.kind_of({'heartbeat_version': 1}), 'heartbeat')
        self.assertEqual(T.kind_of({'report_version': 1, 'meeting': 'x'}), 'report')


class LiveShapeTests(unittest.TestCase):
    """A schema nobody keeps in step with the payloads is a schema that silently empties the fleet view."""

    def test_every_field_a_real_heartbeat_writes_is_either_listed_or_listed_as_dropped(self):
        import tempfile
        from pathlib import Path
        from meeting_os import reports
        from meeting_os.store import Store
        # Everything the schema deliberately refuses. Adding a key to build_heartbeat means deciding, here,
        # whether it travels — which is the point of the gate.
        dropped = {'errors'}
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); store = Store(data / 'meeting-os.sqlite')
            beat = reports.build_heartbeat(store, data, app={'version': '1.2.80'})
            store.close()
        unknown = set(beat) - set(T.ALLOWED['heartbeat']) - dropped
        self.assertEqual(unknown, set(), f'not in telemetry_schema.ALLOWED["heartbeat"]: {sorted(unknown)}')

    def test_every_field_a_real_meeting_report_writes_is_accounted_for(self):
        import tempfile
        from pathlib import Path
        from meeting_os import reports
        from meeting_os.store import Store
        from meeting_os.types import Segment
        dropped = {'errors', 'identity_error'}
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); store = Store(data / 'meeting-os.sqlite')
            mid = store.create_meeting('T', {'paths': {}})
            store.add_segment(mid, Segment(0, 3, 'merhaba', 'system', 'S0'))
            store.status(mid, 'complete')
            report = reports.build_meeting_report(store, mid, data, version='1.2.80')
            store.close()
        unknown = set(report) - set(T.ALLOWED['report']) - dropped
        self.assertEqual(unknown, set(), f'not in telemetry_schema.ALLOWED["report"]: {sorted(unknown)}')


if __name__ == '__main__':
    unittest.main()
