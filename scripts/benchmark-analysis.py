"""Real local-model evaluation on explicitly fictional transcripts. Never uses private data."""
import argparse,json,time,sys,resource
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meeting_os.llm import LocalLLM
from meeting_os.intelligence import analyze_rows
from meeting_os.evaluation import check_fixture_analysis
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--case');p.add_argument('--internal-worker',action='store_true',help=argparse.SUPPRESS);args=p.parse_args()
paths=[path for path in sorted((Path(__file__).resolve().parents[1]/'tests/fixtures/analysis').glob('*.json')) if not args.case or path.stem==args.case]
if not paths:p.error('No matching analysis fixture; no model loaded')
args.output.parent.mkdir(parents=True,exist_ok=True)
if not args.internal_worker:
 from meeting_os.supervisor import run_guarded
 run_guarded([sys.executable,str(Path(__file__).resolve()),*sys.argv[1:],'--internal-worker'],timeout=600,isolated=True,passthrough=True)
 raise SystemExit(0)
model=LocalLLM();results=[]
original=model.complete
def logged(*a,**k):
 raw=original(*a,**k)
 with args.output.with_suffix('.raw.txt').open('a') as f:f.write(raw+'\nEND\n')
 return raw
model.complete=logged
for path in paths:
 case=json.loads(path.read_text());rows=[{'id':i+1,'start':i*10.,'end':i*10.+9,'source':'system','speaker':'S'+str(i),'speaker_name':s['speaker'],'text':s['text'],'flags':[]} for i,s in enumerate(case['segments'])];started=time.monotonic()
 try:
  result=analyze_rows(rows,model)
  checks={'valid_evidence_schema':True,**check_fixture_analysis(result,case)}
  item={'case':path.stem,'checks':checks,'passed':all(checks.values()),'result':result}
 except Exception as exc:item={'case':path.stem,'passed':False,'error':str(exc)}
 item['elapsed_seconds']=time.monotonic()-started;results.append(item);print(path.stem,item['passed'],item['elapsed_seconds'],flush=True)
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({'model_revision':model.model_id,'cases':results,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'requires_independent_semantic_review':True,'scope':'Development fixtures with lexical gates, not held-out semantic or real-meeting accuracy.'},ensure_ascii=False,indent=2))
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
