"""Isolate long-audio residency using fake models; never transcribe private audio.
Run from repository root. Creates and removes a 3154-second synthetic PCM fixture.
"""
import subprocess,sys,tempfile,json
from pathlib import Path
import numpy as np,soundfile as sf
from meeting_os.resources import check_pressure
check_pressure()
with tempfile.TemporaryDirectory(prefix='meetingos-memory-fixture-') as tmp:
 p=Path(tmp)/'fixture.wav'
 with sf.SoundFile(p,'w',samplerate=16000,channels=1,subtype='PCM_16') as f:
  for _ in range(3154):f.write(np.full(16000,.1,dtype=np.float32))
 script='''import sys,json,os
from unittest.mock import patch
from meeting_os.pipeline import Pipeline
from meeting_os.supervisor import footprint
class D:
 mode='cluster'
 def turns(self,a,s):return []
class A:
 def transcribe(self,a):
  print(json.dumps({'bounded':sys.argv[2]=='1','python_footprint_bytes_at_asr':footprint(os.getpid()),'clip_samples':len(a)}));return []
with patch('meeting_os.pipeline.speech_regions',new=lambda a:[(0,16000)]):Pipeline(A(),D(),None).process(sys.argv[1],bounded_final=sys.argv[2]=='1')
'''
 results=[]
 for mode in ['0','1']:
  check_pressure()
  r=subprocess.run([sys.executable,'-c',script,str(p),mode],capture_output=True,text=True,check=True,timeout=30);results.append(json.loads(r.stdout))
 report={'fixture_seconds':3154,'results':results,'limit':'Fake ASR/VAD/diarization: isolates audio residency, not total real model memory or recognition quality.'}
 Path('build/benchmarks/bounded-final-memory.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
