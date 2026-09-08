import os
import runpy
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class DownloadDefaultsTests(unittest.TestCase):
    def test_recommended_setup_omits_optional_large_model(self):
        with patch('meeting_os.models.fetch', return_value='cached') as fetch:
            runpy.run_path(str(ROOT / 'scripts/fetch-recommended.py'), run_name='__main__')
        self.assertEqual([c.args[0] for c in fetch.call_args_list],
                         ['mlx-turbo', 'sherpa', 'analysis-qwen3'])

    def test_download_defaults_apply_before_hub_import(self):
        env = dict(os.environ)
        for key in ('HF_HUB_DISABLE_XET', 'HF_HUB_DOWNLOAD_TIMEOUT'):
            env.pop(key, None)
        result = subprocess.run([sys.executable, '-c',
            'import meeting_os; from huggingface_hub import constants as c; '
            'assert c.HF_HUB_DISABLE_XET; assert c.HF_HUB_DOWNLOAD_TIMEOUT == 120'],
            env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_download_settings_and_offline_inference_are_preserved(self):
        env = dict(os.environ, HF_HUB_DISABLE_XET='0', HF_HUB_DOWNLOAD_TIMEOUT='45')
        env.pop('HF_HUB_OFFLINE', None)
        result = subprocess.run([sys.executable, '-c',
            'import meeting_os; from huggingface_hub import constants as c; '
            'assert not c.HF_HUB_DISABLE_XET; assert c.HF_HUB_DOWNLOAD_TIMEOUT == 45; '
            'assert c.HF_HUB_OFFLINE'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
