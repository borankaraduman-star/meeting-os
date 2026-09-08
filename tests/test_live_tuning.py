import json,tempfile,time,unittest
from pathlib import Path
class LiveTuningTests(unittest.TestCase):
 def test_only_bounded_matching_experiment_can_override_default(self):
  from meeting_os.live_tuning import cpp_threads
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);cfg=root/'config.json';data={'path':str(root/'audio.wav')}
   self.assertEqual(cpp_threads(data,cfg),2)
   valid={'capture_dir':str(root),'expires_at':time.time()+120,'cpp_threads':4}
   cfg.write_text(json.dumps(valid));self.assertEqual(cpp_threads(data,cfg),4)
   for updates in ({'expires_at':0},{'expires_at':time.time()+3600},{'cpp_threads':16},{'capture_dir':'/elsewhere'}):
    cfg.write_text(json.dumps({**valid,**updates}));self.assertEqual(cpp_threads(data,cfg),2)
   cfg.write_text('{broken');self.assertEqual(cpp_threads(data,cfg),2)
