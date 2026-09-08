import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from meeting_os.cli import parser
from meeting_os.live_worker import IsolatedLivePipeline

class LiveWorkerTests(unittest.TestCase):
    def test_chunk_uses_isolated_worker_and_reconstructs_segments(self):
        args=parser().parse_args(['record','capture','--live'])
        def run(command,**options):
            self.assertTrue(options['isolated']);self.assertFalse(options['handle_signals'])
            request=json.loads(Path(command[-2]).read_text())
            self.assertEqual(request['offset'],12)
            Path(command[-1]).write_text(json.dumps({'segments':[{'start':12,'end':15,'text':'Merhaba','source':'mic'}],'turns':[],'duration':3}))
        with patch('meeting_os.live_worker.run_guarded',side_effect=run):
            rows,_,_=IsolatedLivePipeline(args).process('chunk.wav','mic',12,True)
        self.assertEqual(rows[0].text,'Merhaba')
