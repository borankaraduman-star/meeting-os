import tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch
from meeting_os.resources import check_asr_model
class ResourceTests(unittest.TestCase):
    def test_large_model_rejected_on_16gb_before_loading(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'config.json').write_text(json.dumps({'n_text_layer':32}))
            with patch('meeting_os.resources.physical_memory',return_value=16*1024**3):
                with self.assertRaisesRegex(RuntimeError,'32 GB'):check_asr_model(p)
    def test_turbo_allowed_on_16gb(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'config.json').write_text(json.dumps({'n_text_layer':4}))
            with patch('meeting_os.resources.physical_memory',return_value=16*1024**3):check_asr_model(p)
    def test_import_and_finalize_default_to_turbo(self):
        from meeting_os.cli import parser
        for command in ('import','finalize'):
            self.assertEqual(Path(parser().parse_args([command,'fixture']).model).name,'mlx-turbo')
    def test_pressure_blocks_before_model_load(self):
        from meeting_os.resources import check_pressure
        with patch('meeting_os.resources.sys.platform','darwin'),patch('meeting_os.resources.subprocess.check_output',return_value=b'2'):
            with self.assertRaisesRegex(RuntimeError,'bellek baskısı'):check_pressure()
