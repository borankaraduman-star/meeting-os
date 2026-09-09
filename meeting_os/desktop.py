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
        if any(r['start'] is None or r['end'] is None for r in rows):raise ValueError('SRT için başlangıç ve bitiş zamanları gerekir; metin veya JSON olarak dışa aktarın.')
        return '\n\n'.join(f"{i+1}\n{timestamp(r['start'])} --> {timestamp(r['end'])}\n{r['speaker_name'] or r['speaker']}: {r['text']}" for i,r in enumerate(rows))+'\n'
    return '\n\n'.join(f"**{timestamp(r['start'], '.') if r['start'] is not None else 'Zaman belirtilmemiş'} · {r['speaker_name'] or r['speaker']}**\n\n{r['text']}" for r in rows)+'\n'


def capture_state(metadata, include_signal=False):
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
    result={'state':state,'seconds':max(sources.values(),default=0),'sources':sources}
    if include_signal:
        from .source_signal import inspect_signal
        latest={e.get('source'):e for e in events if e.get('event')=='chunk'}
        result['signals']={source:inspect_signal(latest[source].get('path',''),directory) if source in latest else {'state':'unavailable'} for source in ('mic','system')}
    return result


def capture_presentation(status, owner, capture, metadata=None):
    if status not in ('processing','provisional','incomplete','failed') or capture is None:
        return status
    live_processing = status=='processing' and (metadata or {}).get('provisional') is True and not (metadata or {}).get('retry_attempt')
    if live_processing:
        if owner=='active':return 'capturing' if capture.get('state')=='capturing' else status
        if owner=='unknown':return 'capture_unknown'
        return 'pending_finalization' if capture.get('sources') else 'not_started'
    if status=='provisional':
        if owner=='active':return 'capturing'
        if owner=='unknown':return 'capture_unknown'
        return 'pending_finalization' if capture.get('sources') else 'not_started'
    if status in ('incomplete','failed') and owner!='active' and not capture.get('sources'):
        return 'not_started'
    return status


def meeting_files(metadata, data_dir):
    """Audio/capture folders owned by this meeting, only when they live inside the app data directory."""
    data_dir=Path(data_dir).resolve()
    candidates=[metadata.get('capture_dir')]+[v for v in (metadata.get('paths') or {}).values() if isinstance(v,str)]
    folders=set()
    for value in candidates:
        if not isinstance(value,str) or not value: continue
        path=Path(value)
        try: resolved=path.resolve()
        except OSError: continue
        if path.suffix: resolved=resolved.parent  # a file inside its own import/capture folder
        try: relative=resolved.relative_to(data_dir)
        except ValueError: continue
        if len(relative.parts)==2 and relative.parts[0] in ('recordings','imports'): folders.add(resolved)
    return sorted(folders)


def delete_meeting(store, mid, data_dir):
    import shutil
    from .recovery import classify, metadata as read_metadata
    row=store.db.execute('SELECT * FROM meetings WHERE id=?',(mid,)).fetchone()
    if not row: raise ValueError('Toplantı bulunamadı')
    meta=read_metadata(row)
    if row['status'] in ('processing','provisional') and classify(meta.get('worker_identity'))=='active':
        raise ValueError('Bu toplantı üzerinde iş sürüyor; önce işlemi durdurun')
    folders=meeting_files(meta,data_dir)
    store.delete_meeting(mid)
    removed=[]
    for folder in folders:
        if folder.is_dir() and not folder.is_symlink():
            shutil.rmtree(folder,ignore_errors=True); removed.append(str(folder))
    return {'deleted':True,'removed_folders':removed}


def dispatch(request, db=None):
    if request.get('action')=='diagnostics':
        from .diagnostics import collect,export_report
        path=Path(request['path'])
        export_report(path,collect(path.parent,request.get('progress')))
        return {'diagnostics_saved':True}
    with contextlib.closing(Store(db or DATA_DIR/'meeting-os.sqlite')) as store:
        action=request['action']
        if action=='openrouter_models':
            from .openrouter import STT_MODELS,STT_MODEL,DIARIZATION_DEFAULT_MODEL
            return {'models':[{**m,'diarization':m['diarization'] is not None} for m in STT_MODELS],'default':STT_MODEL,'diarization_default':DIARIZATION_DEFAULT_MODEL,'verified_at':'2026-09-09'}
        if action in ('transcript_preview','transcript_import'):
            from .transcript_import import preview,save
            return preview(request.get('text')) if action=='transcript_preview' else save(store,request.get('title'),request.get('text'))
        if action in ('label','edit_text','enroll','label_speaker'):
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
                m['metadata']=metadata(m)
                m['metadata'].pop('raw_source_text',None)
                m['recovery_state']=classify(m['metadata'].get('worker_identity')) if m['status'] in ('processing','provisional','incomplete','failed') else m['status']
                live=m['recovery_state']=='active' and m['metadata'].get('provisional') is True and not m['metadata'].get('retry_attempt')
                m['capture']=capture_state(m['metadata'],include_signal=live)
                if live and m['capture'] is not None:
                    from .preview_failures import summarize
                    m['capture']['preview']=summarize(m['metadata']['capture_dir'],DATA_DIR/'last-job.log' if db is None else None)
                m['display_status']=capture_presentation(m['status'],m['recovery_state'],m['capture'],m['metadata'])
            return {'meetings':meetings,'profiles':store.profiles(),'segments':store.display_segments(request.get('meeting',''))}
        if action=='label_speaker':
            if request.get('enroll'): return store.enroll_speaker(request['meeting'],request['speaker'],request['name'])
            store.correct(request['meeting'],request['speaker'],request['name']); return {'labeled':True,'profile_saved':False}
        if action=='label':
            store.correct_segment(request['meeting'],int(request['segment']),request['name']); return {'saved':True}
        if action=='edit_text':
            store.correct_text(request['meeting'],int(request['segment']),request['text']); return {'saved':True}
        if action=='enroll':
            if request.get('confirmed_clean') is not True: raise ValueError('Listen and confirm a clean single-speaker sample first')
            store.enroll_segment(request['meeting'],int(request['segment']),request['name'])
            return {'saved':True}
        if action=='delete_profile': store.delete_profile(request['name']); return {'deleted':True}
        if action=='quality_report':
            from .quality import report
            return report(store)
        if action=='review_queue':
            from .review import review_queue
            return review_queue(store,request['meeting'])
        if action=='delete_meeting':
            return delete_meeting(store,request['meeting'],DATA_DIR if db is None else Path(db).parent)
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
