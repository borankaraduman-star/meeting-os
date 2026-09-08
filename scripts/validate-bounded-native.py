"""Guarded synthetic native-model equality check for bounded final audio.
Refuses active Meeting OS audio jobs; writes numeric evidence without transcripts.
"""
import sys,json,tempfile,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
(ROOT/'build/benchmarks').mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('benchmark',ROOT/'scripts/benchmark-cpp-batch.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
from meeting_os.supervisor import run_guarded
if b.competing_job():raise SystemExit('Active job; deferred')
if '--worker' not in sys.argv:
 result=run_guarded([sys.executable,__file__,'--worker'],timeout=180,isolated=True,passthrough=True,cancel_requested=b.competing_job)
 p=ROOT/'build/benchmarks/bounded-native.json';d=json.loads(p.read_text());d['supervisor']=result;p.write_text(json.dumps(d,indent=2));print(json.dumps(result));raise SystemExit()
from meeting_os.cli import parser,make_pipeline
from meeting_os.store import Store
from meeting_os.audio import read_audio,RATE
import soundfile as sf,time,math
with tempfile.TemporaryDirectory(prefix='meetingos-bounded-native-') as tmp:
 p=Path(tmp);wav=p/'fixture.wav';audio=read_audio(ROOT/'benchmarks/code-switch-synthetic/mixed.wav');sf.write(wav,audio,RATE,subtype='PCM_16');del audio
 args=parser().parse_args(['--db',str(p/'db'),'transcribe',str(wav),'--engine','cpp']);store=Store(p/'db')
 pipe=make_pipeline(args,store);runs=[];outputs=[]
 for bounded in [False,True]:
  start=time.monotonic();rows,turns,duration=pipe.process(wav,bounded_final=bounded)
  outputs.append([r.to_dict() for r in rows])
  runs.append({'bounded':bounded,'elapsed_seconds':time.monotonic()-start,'segments':len(rows),'turns':len(turns),'audio_seconds':duration,'invalid_segment_times':sum(not (math.isfinite(r.start) and math.isfinite(r.end) and 0<=r.start<r.end<=duration) for r in rows)})
 report={'kind':'synthetic real local models; no private audio','runs':runs,'exact_segment_match':outputs[0]==outputs[1],'text_match':[r['text'] for r in outputs[0]]==[r['text'] for r in outputs[1]],'profiles_created':len(store.profiles())}
 (ROOT/'build/benchmarks/bounded-native.json').write_text(json.dumps(report,indent=2));store.close();print(json.dumps(report))
