"""Public held-out utterance speaker test. No participant meeting data."""
import argparse,tarfile,io,json,tempfile,time
from pathlib import Path
import numpy as np,soundfile as sf
from meeting_os.speakers import Embedder
from meeting_os.store import Store
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('archive',type=Path);args=p.parse_args()
groups={}
with tarfile.open(args.archive) as tar:
 for item in tar:
  if not item.isfile() or not item.name.endswith('.flac'):continue
  parts=Path(item.name).parts;speaker=parts[-3]
  if speaker not in groups and len(groups)>=8:continue
  if len(groups.get(speaker,[]))>=4:continue
  data,rate=sf.read(io.BytesIO(tar.extractfile(item).read()),dtype='float32')
  if rate!=16000 or len(data)<5*rate:continue
  groups.setdefault(speaker,[]).append((parts[-1],data))
  if len(groups)==8 and all(len(v)==4 for v in groups.values()):break
if len(groups)<8 or any(len(v)<4 for v in groups.values()):raise RuntimeError('Insufficient corpus samples')
rng=np.random.default_rng(20260908);results=[]
for engine,model in [('resemblyzer',None),('ecapa',str(ROOT/'models/ecapa'))]:
 emb=Embedder(engine,model);started=time.monotonic()
 with tempfile.TemporaryDirectory() as tmp:
  db=Path(tmp)/'profiles.sqlite';s=Store(db);known=list(groups)[:6]
  for speaker in known:
   name,a=groups[speaker][0];s.enroll(speaker,emb.embed(a),emb.model_id,len(a)/16000,name)
  s.close();s=Store(db)
  for speaker,clips in groups.items():
   for filename,a in clips[1:]:
    for condition in ('clean','noise20dB','short3s'):
     x=a.copy()
     if condition=='noise20dB':x+=rng.normal(0,np.sqrt(np.mean(x*x))/10,len(x)).astype(np.float32)
     if condition=='short3s':x=x[:48000]
     found=s.identify(emb.embed(x),emb.model_id)
     expected=speaker if speaker in known else None
     results.append({'engine':engine,'speaker':speaker,'file':filename,'condition':condition,'expected':expected,**found,'correct':found['name']==expected,'false_accept':found['name'] is not None and found['name']!=expected,'false_reject':expected is not None and found['name'] is None})
  s.close()
 print(engine,'seconds',time.monotonic()-started,flush=True)
report={'source':'LibriSpeech dev-clean / OpenSLR12 CC-BY4','scope':'8 audiobook speakers, first eligible four >=5s clips each. Six enrolled, two unknown. Enrollment utterance never tested; not different-device or Turkish meeting validation. Threshold .80, margin .08; seeded noise20dB; 3s prefix test.','results':results}
(ROOT/'docs/IDENTITY_HUMAN.json').write_text(json.dumps(report,indent=2))
for engine in ('resemblyzer','ecapa'):
 for condition in ('clean','noise20dB','short3s'):
  xs=[x for x in results if x['engine']==engine and x['condition']==condition]
  print(engine,condition,'correct',sum(x['correct'] for x in xs),'/',len(xs),'false_accept',sum(x['false_accept'] for x in xs),'false_reject',sum(x['false_reject'] for x in xs),flush=True)
