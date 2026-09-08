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
 def test_batch_requires_explicit_boolean_and_matching_unexpired_recording(self):
  from meeting_os.live_tuning import batch_regions
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);cfg=root/'cfg';data={'path':str(root/'clip.wav')}
   valid={'capture_dir':str(root),'expires_at':time.time()+120,'cpp_threads':2,'batch_regions':True}
   cfg.write_text(json.dumps(valid));self.assertTrue(batch_regions(data,cfg))
   for updates in ({'batch_regions':1},{'batch_regions':'true'},{'expires_at':0},{'capture_dir':'/other'}):
    cfg.write_text(json.dumps({**valid,**updates}));self.assertFalse(batch_regions(data,cfg))
 def test_attention_trial_is_explicit_and_not_combined_with_batch(self):
  from meeting_os.live_tuning import no_flash_attention,batch_regions
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);cfg=root/'cfg';data={'path':str(root/'clip.wav')}
   valid={'capture_dir':str(root),'expires_at':time.time()+120,'cpp_threads':2,'no_flash_attention':True}
   cfg.write_text(json.dumps(valid));self.assertTrue(no_flash_attention(data,cfg));self.assertFalse(batch_regions(data,cfg))
   for change in ({'no_flash_attention':1},{'expires_at':0},{'batch_regions':True},{'cpp_threads':4}):
    cfg.write_text(json.dumps({**valid,**change}));self.assertFalse(no_flash_attention(data,cfg))
 def test_live_gpu_remains_disabled_after_failed_pressure_trial(self):
  from meeting_os.live_tuning import cpp_gpu
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);cfg=root/'cfg';data={'path':str(root/'clip.wav')}
   valid={'capture_dir':str(root),'expires_at':time.time()+60,'cpp_threads':2,'cpp_gpu':True}
   cfg.write_text(json.dumps(valid));self.assertFalse(cpp_gpu(data,cfg))
   for change in ({'cpp_gpu':1},{'expires_at':time.time()+300},{'batch_regions':True},{'no_flash_attention':True},{'cpp_threads':4},{'capture_dir':'/other'}):
    cfg.write_text(json.dumps({**valid,**change}));self.assertFalse(cpp_gpu(data,cfg))

 def test_failure_rollback_does_not_delete_a_replacement_profile(self):
  from meeting_os.live_tuning import revision,disable_trial
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);cfg=root/'cfg';data={'path':str(root/'clip.wav')}
   valid={'capture_dir':str(root),'expires_at':time.time()+60,'cpp_threads':2}
   cfg.write_text(json.dumps(valid));data['_tuning_revision']=revision(data,cfg)
   cfg.write_text(json.dumps({**valid,'cpp_threads':4}));self.assertFalse(disable_trial(data,cfg));self.assertTrue(cfg.exists())
   data['_tuning_revision']=revision(data,cfg);self.assertTrue(disable_trial(data,cfg));self.assertFalse(cfg.exists())
