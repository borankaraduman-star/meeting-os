"""Explicit synthetic-only check: persisted profile, different utterance, same TTS voice."""
import argparse
import json
from pathlib import Path
import tempfile
from meeting_os.audio import read_audio
from meeting_os.speakers import Embedder
from meeting_os.store import Store
p=argparse.ArgumentParser(); p.add_argument('first'); p.add_argument('second'); p.add_argument('--output',type=Path,required=True); args=p.parse_args()
results=[]
root=Path(__file__).resolve().parents[1]
for engine,model in [('resemblyzer',None),('ecapa',str(root/'models/ecapa'))]:
    embedder=Embedder(engine,model)
    x=read_audio(args.first); y=read_audio(args.second)
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'profile.sqlite'
        db=Store(path); db.enroll('SYNTHETIC Yelda',embedder.embed(x),embedder.model_id,len(x)/16000,'synthetic-enrollment-session'); db.close()
        db=Store(path); identified=db.identify(embedder.embed(y),embedder.model_id); db.close()
    results.append({'engine':engine,'model':embedder.model_id,'result':identified,'passed':identified['name']=='SYNTHETIC Yelda'})
args.output.write_text(json.dumps({'kind':'synthetic','scope':'same TTS voice, different utterance, reopened SQLite; not human speaker validation','results':results},indent=2))
print(json.dumps(results,indent=2))
if not all(r['passed'] for r in results): raise SystemExit(1)
