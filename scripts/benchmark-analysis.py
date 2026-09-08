"""Real local-model evaluation on explicitly fictional transcripts. Never uses private data."""
import argparse,json,time,sys,resource
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meeting_os.llm import LocalLLM
from meeting_os.intelligence import analyze_rows
from meeting_os.metrics import normalize
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--case');args=p.parse_args()
model=LocalLLM();results=[]
original=model.complete
def logged(*a,**k):
 raw=original(*a,**k)
 with args.output.with_suffix('.raw.txt').open('a') as f:f.write(raw+'\nEND\n')
 return raw
model.complete=logged
for path in sorted((Path(__file__).resolve().parents[1]/'tests/fixtures/analysis').glob('*.json')):
 if args.case and path.stem!=args.case:continue
 case=json.loads(path.read_text());rows=[{'id':i+1,'start':i*10.,'end':i*10.+9,'source':'system','speaker':'S'+str(i),'speaker_name':s['speaker'],'text':s['text'],'flags':[]} for i,s in enumerate(case['segments'])];started=time.monotonic()
 try:
  result=analyze_rows(rows,model);actions=result['actions'];forbidden=[w for w in case['forbidden_action_terms'] if any(normalize(w) in normalize(a['title']) for a in actions)]
  checks={'valid_evidence_schema':True,'action_count':len(actions)==case['expected_actions'],'owner_set':sorted(a['owner'] or '' for a in actions)==sorted(o or '' for o in case['expected_owners']),'no_forbidden_actions':not forbidden}
  item={'case':path.stem,'checks':checks,'passed':all(checks.values()),'result':result}
 except Exception as exc:item={'case':path.stem,'passed':False,'error':str(exc)}
 item['elapsed_seconds']=time.monotonic()-started;results.append(item);print(path.stem,item['passed'],item['elapsed_seconds'],flush=True)
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({'model_revision':model.model_id,'cases':results,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'scope':'Fictional Turkish transcripts; not a real-meeting accuracy estimate.'},ensure_ascii=False,indent=2))
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
