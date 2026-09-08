"""One-request local stdio bridge. No listening socket and no external actions."""
import contextlib
import json
import sys
from pathlib import Path
from .cli import DATA_DIR, ROOT, parser, run_transcribe
from .store import Store


def timestamp(t, sep=','):
    ms=round(t*1000); hours,ms=divmod(ms,3600000); minutes,ms=divmod(ms,60000); seconds,ms=divmod(ms,1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}{sep}{ms:03}'


def export_text(rows, kind):
    if kind=='json':
        return json.dumps([{k:v for k,v in r.items() if k not in ('embedding','embedding_model')} for r in rows],ensure_ascii=False,indent=2)
    if kind=='srt':
        return '\n\n'.join(f"{i+1}\n{timestamp(r['start'])} --> {timestamp(r['end'])}\n{r['speaker_name'] or r['speaker']}: {r['text']}" for i,r in enumerate(rows))+'\n'
    return '\n\n'.join(f"**{timestamp(r['start'], '.')} · {r['speaker_name'] or r['speaker']}**\n\n{r['text']}" for r in rows)+'\n'


def capture_state(metadata):
    directory=metadata.get('capture_dir')
    if not directory: return None
    path=Path(directory)/'capture-native.jsonl'
    if not path.exists(): return {'state':'waiting','seconds':0,'sources':{}}
    with path.open('rb') as f:
        f.seek(max(0,path.stat().st_size-65536)); data=f.read().decode('utf-8',errors='replace')
    events=[]
    for line in data.splitlines():
        try: events.append(json.loads(line))
        except json.JSONDecodeError: pass
    sources={}
    for e in events:
        if e.get('event')=='chunk': sources[e['source']]=max(sources.get(e['source'],0),e['start']+e['duration'])
    state='waiting'
    for e in events:
        if e.get('event') in ('started','chunk'): state='capturing'
        elif e.get('event') in ('error','stopped'):state=e['event']
    return {'state':state,'seconds':max(sources.values(),default=0),'sources':sources}


def dispatch(request, db=None):
    if request.get('action')=='diagnostics':
        from .diagnostics import collect,export_report
        path=Path(request['path'])
        export_report(path,collect(path.parent,request.get('progress')))
        return {'diagnostics_saved':True}
    with contextlib.closing(Store(db or DATA_DIR/'meeting-os.sqlite')) as store:
        action=request['action']
        if action in ('label','edit_text','enroll'):
            row=store.db.execute('SELECT status FROM meetings WHERE id=?',(request['meeting'],)).fetchone()
            if not row or row['status']!='complete': raise ValueError('Önce nihai transkriptin tamamlanmasını bekleyin')
        from .memory import Memory
        from .assistant import drafts,handoff,route,edit_draft
        memory=Memory(store)
        if action=='intelligence':
            return {'analysis':memory.latest(request.get('meeting','')),'tasks':[{**t,'route':route(t['title'])} for t in memory.actions()], 'drafts':drafts(store)}
        if action=='draft_update':return edit_draft(store,request['draft'],request['text'])
        if action=='action_update':return memory.update_action(request['task'],request['changes'])
        if action=='search_memory':return {'hits':memory.search(request['query'],speaker=request.get('speaker'))}
        if action=='handoff':return handoff(store,request['task'],request['path'])
        if action=='snapshot':
            meetings=store.meetings()
            for m in meetings:
                from .recovery import metadata,classify
                m['metadata']=metadata(m); m['capture']=capture_state(m['metadata'])
                m['recovery_state']=classify(m['metadata'].get('worker_identity')) if m['status']=='processing' else m['status']
            return {'meetings':meetings,'profiles':store.profiles(),'segments':store.display_segments(request.get('meeting',''))}
        if action=='label':
            store.correct_segment(request['meeting'],int(request['segment']),request['name']); return {'saved':True}
        if action=='edit_text':
            store.correct_text(request['meeting'],int(request['segment']),request['text']); return {'saved':True}
        if action=='enroll':
            if request.get('confirmed_clean') is not True: raise ValueError('Listen and confirm a clean single-speaker sample first')
            store.enroll_segment(request['meeting'],int(request['segment']),request['name'])
            return {'saved':True}
        if action=='delete_profile': store.delete_profile(request['name']); return {'deleted':True}
        if action=='export_analysis':
            current=memory.latest(request['meeting'])
            if not current:raise ValueError('Önce toplantıyı analiz edin')
            lines=['# Toplantı özeti', 'Güncel değil; kaynak değişti.' if current['stale'] else 'Model çıkarımı; kaynaklarla kontrol edin.', 'Analiz sürümü: '+str(current['id'])]
            for key,label in [('summary','Özet'),('decisions','Kararlar'),('risks','Riskler'),('questions','Açık sorular')]:
                lines+=['\n## '+label]
                for item in current['payload'].get(key,[]):
                    lines+=['- '+item['text']]
                    lines+=['  - Kaynak #'+str(e['segment_id'])+' ('+timestamp(e['start'],'.')+'): '+e['quote'] for e in item['evidence']]
            lines+=['\n## Görevler']
            for t in memory.actions(meeting=request['meeting']):
                lines+=['- '+t['title']+' | '+(t['owner'] or 'Belirsiz')+' | '+(t['due_text'] or 'Tarih yok')+' | '+t['state']+(' | GÜNCEL DEĞİL' if t['stale'] else '')]
            Path(request['path']).write_text('\n'.join(lines),encoding='utf-8');return {'path':request['path']}
        if action=='export':
            rows=store.segments(request['meeting'])
            path=Path(request['path']); path.write_text(export_text(rows,request['format']))
            return {'path':str(path)}
        if action=='vocabulary':
            path=ROOT/'vocabulary.txt'
            if 'text' in request: path.write_text(request['text'])
            return {'text':path.read_text()}
        raise ValueError('Unknown desktop action')


def main():
    try:
        request=json.loads(sys.stdin.read())
        result=dispatch(request)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False)); sys.exit(1)

if __name__=='__main__': main()
