import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class LiveTimingTests(unittest.TestCase):
 def test_stage_durations_are_aggregated_and_no_content_saved(self):
  from meeting_os.live_timing import observe_worker
  from meeting_os.progress import emit
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); (root/'capture-native.jsonl').touch()
   with patch('meeting_os.live_timing.time.monotonic',side_effect=[0,1,3,6]):
    with observe_worker({'path':str(root/'mic.wav'),'source':'mic','offset':12}):
     emit('loading_models');emit('transcribing')
   row=json.loads((root/'live-mic-timing.json').read_text())
   self.assertEqual(row['stages'],{'startup':1,'loading_models':2,'transcribing':3})
   self.assertEqual(row['elapsed_seconds'],6)
   self.assertEqual(set(row),{'stages','elapsed_seconds','offset','source','updated_at','failed','cpp_threads'})
 def test_diagnostics_failure_does_not_mask_pipeline_error(self):
  from meeting_os.live_timing import observe_worker
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'capture-native.jsonl').touch();(root/'live-mic-timing.json').mkdir()
   with self.assertRaisesRegex(ValueError,'original'):
    with observe_worker({'path':str(root/'mic.wav'),'source':'mic','offset':0}):raise ValueError('original')
 def test_unrecognized_source_does_not_write_outside_recording(self):
  from meeting_os.live_timing import observe_worker
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'capture-native.jsonl').touch()
   with observe_worker({'path':str(root/'x.wav'),'source':'../escape','offset':0}):pass
   self.assertEqual([p.name for p in root.iterdir()],['capture-native.jsonl'])
