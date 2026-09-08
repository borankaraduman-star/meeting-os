import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from meeting_os.progress import emit
class ProgressTests(unittest.TestCase):
    def test_latest_event_replaces_prior_event_without_transcript(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'progress.json'
            with patch.dict(os.environ,{'MEETING_OS_PROGRESS_PATH':str(p)}):
                emit('diarizing',source='system');emit('transcribing',current=2,total=5,source='mic')
            data=json.loads(p.read_text())
            self.assertEqual((data['stage'],data['current'],data['total'],data['source']),('transcribing',2,5,'mic'))
            self.assertEqual(set(data),{'stage','current','total','source','updated_at'})
    def test_unwritable_progress_does_not_fail_audio(self):
        with tempfile.TemporaryDirectory() as t:
            with patch.dict(os.environ,{'MEETING_OS_PROGRESS_PATH':t}):emit('loading_models')
