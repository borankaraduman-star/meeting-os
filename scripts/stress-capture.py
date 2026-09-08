"""Accelerated 3h reconstruction and recorder broken-pipe regression. No mic access."""
from pathlib import Path
import tempfile,subprocess,json,time
import numpy as np,soundfile as sf
from meeting_os.audio import assemble_capture,RATE
ROOT=Path(__file__).resolve().parents[1]
started=time.monotonic()
with tempfile.TemporaryDirectory(prefix='meeting-stress-') as tmp:
 root=Path(tmp); cap=root/'native'
 p=subprocess.Popen([str(ROOT/'build/MeetingCapture.app/Contents/MacOS/MeetingCapture'),'--self-test','--output',str(cap)],stdout=subprocess.PIPE)
 p.stdout.close()
 assert p.wait(timeout=15)==0, 'Recorder failed when UI/inference pipe closed'
 events=[json.loads(x) for x in (cap/'capture-native.jsonl').read_text().splitlines()]
 assert len([e for e in events if e['event']=='chunk'])==2
 reconstructed=assemble_capture(cap)
 assert abs(sf.info(reconstructed['mic']).duration-1.25)<1/RATE
 long=root/'three-hours';long.mkdir()
 chunk=long/'chunk.wav';sf.write(chunk,np.zeros(12*RATE,dtype=np.float32),RATE)
 with (long/'capture-native.jsonl').open('w') as log:
  for source in ('mic','system'):
   for n in range(900):
    log.write(json.dumps({'event':'chunk','source':source,'path':str(chunk),'start':n*12,'duration':12})+'\n')
 paths=assemble_capture(long)
 for path in paths.values(): assert sf.info(path).frames==3*3600*RATE
 report={'native_broken_stdout':'passed','native_journal_recovery':'passed','accelerated_duration_hours':3,'sources':2,'chunks':1800,'reconstructed_frames_per_source':3*3600*RATE,'elapsed_seconds':time.monotonic()-started,'scope':'Accelerated WAV reconstruction; not a 3-hour hardware or ASR soak test'}
 (ROOT/'docs/STRESS_CAPTURE.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
