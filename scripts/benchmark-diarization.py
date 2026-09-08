"""Constructed real-voice turn attribution; utterance bounds are not gold speech RTTM."""
from pathlib import Path
import tarfile,io,json,time,sys
import numpy as np,soundfile as sf
from scipy.optimize import linear_sum_assignment
from meeting_os.speakers import Diarizer,overlap
ROOT=Path(__file__).resolve().parents[1];groups={}
with tarfile.open(sys.argv[1]) as tar:
 for f in tar:
  if not f.isfile() or not f.name.endswith('.flac'):continue
  sid=Path(f.name).parts[-3]
  if sid not in groups and len(groups)>=4:continue
  if len(groups.get(sid,[]))>=3:continue
  a,r=sf.read(io.BytesIO(tar.extractfile(f).read()),dtype='float32')
  if r!=16000 or len(a)<5*r:continue
  groups.setdefault(sid,[]).append((f.name,a))
  if len(groups)==4 and all(len(v)==3 for v in groups.values()):break
ref=[];audio=[];cursor=0
for round in range(3):
 for sid,clips in groups.items():
  path,a=clips[round];start=cursor/16000;audio.append(a);cursor+=len(a)
  ref.append({'start':start,'end':cursor/16000,'speaker':sid,'source_file':path})
  audio.append(np.zeros(4000,dtype=np.float32));cursor+=4000
x=np.concatenate(audio);out=ROOT/'benchmarks/human-constructed';out.mkdir(exist_ok=True)
sf.write(out/'four-voices.wav',x,16000)
results=[]
for threshold in (.7,.9):
 diar=Diarizer(None,'sherpa',None,threshold);started=time.monotonic();turns=diar.turns(x,'system')
 speakers=sorted(set(t[2] for t in turns));refs=list(groups)
 weights=np.array([[sum(overlap(r['start'],r['end'],a,b) for r in ref if r['speaker']==sid for a,b,s in turns if s==label) for label in speakers] for sid in refs])
 ir,ic=linear_sum_assignment(-weights);mapping={speakers[c]:refs[r] for r,c in zip(ir,ic)}
 predictions=[]
 for r in ref:
  votes={s:sum(overlap(r['start'],r['end'],a,b) for a,b,label in turns if label==s) for s in speakers}
  winner=max(votes,key=votes.get) if votes else None
  predictions.append({**r,'predicted':mapping.get(winner),'correct':mapping.get(winner)==r['speaker']})
 results.append({'threshold':threshold,'elapsed':time.monotonic()-started,'speaker_count':len(speakers),'turn_majority_correct':sum(p['correct'] for p in predictions),'turns_total':len(predictions),'predictions':predictions,'turns':turns})
 print({k:v for k,v in results[-1].items() if k not in ('predictions','turns')},flush=True)
(out/'SOURCE.md').write_text('Constructed concatenation of real LibriSpeech dev-clean voices. CC-BY4, https://www.openslr.org/12/. Four speakers × three utterances, 250ms gaps. Majority attribution uses known utterance bounds with pauses; not a natural meeting, not gold DER.\n')
(ROOT/'docs/DIARIZATION_HUMAN.json').write_text(json.dumps({'duration':len(x)/16000,'scope':'Constructed human audiobook turns; majority attribution after optimal global label mapping. Not natural meeting DER.','results':results},indent=2))
