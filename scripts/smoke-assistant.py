"""On-device integration: fixture transcript → analysis → task → draft → QA → reopen."""
import argparse,json,tempfile,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meeting_os.store import Store
from meeting_os.types import Segment
from meeting_os.llm import LocalLLM
from meeting_os import assistant
from meeting_os.memory import Memory
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--demo',action='store_true',help='Save explicitly fictional demonstration in app library');args=p.parse_args()
from meeting_os.cli import DATA_DIR
with tempfile.TemporaryDirectory() as tmp:
 db=DATA_DIR/'meeting-os.sqlite' if args.demo else Path(tmp)/'db'
 s=Store(db);mid=s.create_meeting('Örnek · Kurgu sprint (ses kaydı değildir)',{'fixture':'analysis/sprint.json','text_only':True})
 case=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/analysis/sprint.json').read_text())
 for i,row in enumerate(case['segments']):s.add_segment(mid,Segment(i*10,i*10+9,row['text'],'system','S'+str(i),row['speaker']))
 s.status(mid,'complete');llm=LocalLLM();t=time.monotonic();analysis=assistant.analyze(s,mid,llm);mem=Memory(s);tasks=mem.actions(meeting=mid);boran=next(t for t in tasks if t['owner']=='Boran');draft=assistant.prepare(s,boran['id'],llm);answer=assistant.ask(s,'PRD taslağı',llm);mem.update_action(boran['id'],{'state':'in_progress'});handoff=assistant.handoff(s,boran['id'],Path(tmp)/'task.md')
 # Moving to in-progress preserves the draft; content edits would stale it.
 old_stale=assistant.draft(s,draft['id'])['stale'];s.close();s=Store(db);persisted=Memory(s).task(boran['id'])['state']=='in_progress';s.close()
 result={'meeting':mid,'model':llm.model_id,'actions':len(tasks),'boran_actions':sum(t['owner']=='Boran' for t in tasks),'draft_text':draft['text'],'answer':answer,'manual_state_persisted':persisted,'draft_stale_after_progress_change':old_stale,'handoff_sent':handoff['sent'],'elapsed_seconds':time.monotonic()-t,'scope':'Fictional text input; actual local model and SQLite, not audio/real meeting quality'}
 args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('draft_text','answer')},ensure_ascii=False))
 if not (persisted and not old_stale and len(tasks)==3 and not answer['abstained']):raise SystemExit(1)
