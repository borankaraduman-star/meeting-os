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


def folder_bytes(path):
    """Total size of regular files under a directory (symlinks skipped, nothing modified)."""
    path=Path(path)
    if not path.is_dir(): return 0
    total=0
    for p in path.rglob('*'):
        try:
            if p.is_file() and not p.is_symlink(): total+=p.stat().st_size
        except OSError: continue
    return total


def storage_report(store, data_dir, db_path):
    """Disk usage of recordings/, imports/ and the database, plus audio owned by each meeting (largest first)."""
    from .recovery import classify, metadata as read_metadata
    data_dir=Path(data_dir); db_path=Path(db_path)
    database=sum(p.stat().st_size for p in (db_path,Path(str(db_path)+'-wal'),Path(str(db_path)+'-shm')) if p.is_file())
    totals={'recordings':folder_bytes(data_dir/'recordings'),'imports':folder_bytes(data_dir/'imports'),'database':database}
    meetings=[]
    for row in store.meetings():
        meta=read_metadata(row)
        folders=meeting_files(meta,data_dir)
        if not folders: continue
        size=sum(folder_bytes(f) for f in folders)
        active=row['status'] in ('processing','provisional') and classify(meta.get('worker_identity'))=='active'
        meetings.append({'meeting':row['id'],'title':row['title'],'bytes':size,'active':active})
    meetings.sort(key=lambda m:m['bytes'],reverse=True)
    return {'totals':totals,'total':sum(totals.values()),'meetings':meetings}


def storage_cleanup(store, data_dir, days=30, dry_run=True):
    """Free disk by removing the audio of completed meetings older than `days` while keeping their transcript,
    analysis and profiles. Meetings marked metadata.keep=true, incomplete ones and active jobs are never touched.
    dry_run lists what would go; only an explicit dry_run=False deletes."""
    import shutil
    from datetime import datetime, timedelta, timezone
    from .recovery import classify, metadata as read_metadata
    data_dir=Path(data_dir); cutoff=datetime.now(timezone.utc)-timedelta(days=int(days))
    candidates=[]; freed=0
    for row in store.meetings():
        meta=read_metadata(row)
        if row['status']!='complete' or meta.get('keep') is True: continue
        if classify(meta.get('worker_identity'))=='active': continue
        try: created=datetime.fromisoformat(row['created'])
        except ValueError: continue
        if created.tzinfo is None: created=created.replace(tzinfo=timezone.utc)
        if created>cutoff: continue
        folders=[f for f in meeting_files(meta,data_dir) if f.is_dir()]
        if not folders: continue
        size=sum(folder_bytes(f) for f in folders)
        candidates.append({'meeting':row['id'],'title':row['title'],'created':row['created'],'bytes':size,'folders':[str(f) for f in folders]})
        freed+=size
        if not dry_run:
            for f in folders: shutil.rmtree(f,ignore_errors=True)
            meta['audio_removed']=datetime.now(timezone.utc).isoformat(); meta.pop('paths',None)
            with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta),row['id']))
    return {'dry_run':dry_run,'days':int(days),'meetings':candidates,'bytes':freed}


def register_import_digest(store, mid, digest, size=None):
    """Merge original_digest (and original_size) into a meeting's metadata so later imports of the same file are recognized."""
    import re
    from .recovery import metadata as read_metadata
    if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest): raise ValueError('Geçersiz dosya özeti')
    row=store.db.execute('SELECT * FROM meetings WHERE id=?',(mid,)).fetchone()
    if not row: raise ValueError('Toplantı bulunamadı')
    meta=read_metadata(row); meta['original_digest']=digest
    if isinstance(size,int) and not isinstance(size,bool) and size>=0: meta['original_size']=size
    with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta,ensure_ascii=False),mid))
    return {'registered':True}


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
    from .reports import remove_meeting_report
    return {'deleted':True,'removed_folders':removed,'removed_reports':remove_meeting_report(mid,data_dir)}


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
            stats={r[0]:{'segments':r[1],'seconds':float(r[2] or 0),'speakers':r[3]} for r in store.db.execute(
                "SELECT meeting,count(*),max(end),count(DISTINCT coalesce(nullif(speaker_name,''),speaker)) FROM segments WHERE source='system' OR speaker_name<>'' GROUP BY meeting")}
            for m in meetings:
                from .recovery import metadata,classify
                m['stats']=stats.get(m['id'],{'segments':0,'seconds':0.0,'speakers':0})
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
        if action=='profile_samples': return {'name':request['name'],'samples':store.profile_samples(request['name'])}
        if action=='delete_sample': store.delete_sample(request['sample']); return {'deleted':True}
        if action=='rename_profile': return store.rename_profile(request['name'],request['new_name'])
        if action=='explain_identity':
            rows=[r for r in store.segments(request['meeting']) if r['speaker']==request['speaker'] and r.get('embedding')]
            if not rows: return {'candidates':[],'reason':'Bu konuşmacı için ses vektörü yok (3 saniyeden kısa veya henüz işlenmedi)'}
            model=rows[0]['embedding_model'];vs=[r['embedding'] for r in rows if r.get('embedding_model')==model]
            centroid=[sum(col)/len(vs) for col in zip(*vs)]
            from .cloud_finalize import IDENTITY_THRESHOLD, IDENTITY_MARGIN, SUGGEST_THRESHOLD
            return {'candidates':store.explain_identity(centroid,model),'threshold':IDENTITY_THRESHOLD,'margin':IDENTITY_MARGIN,'suggest':SUGGEST_THRESHOLD,'seconds':round(sum(r['end']-r['start'] for r in rows),1)}
        if action in ('update_check','update_start','update_status'):
            from . import updater
            if action=='update_check': return updater.check(ROOT)
            if action=='update_start': return updater.start(ROOT,DATA_DIR)
            return updater.status(DATA_DIR)
        if action in ('report_settings','report_settings_set','report_write','reports_summary'):
            from . import reports
            base=DATA_DIR if db is None else Path(db).parent
            if action=='report_settings': return reports.load_settings(base)
            if action=='report_settings_set': return reports.save_settings(base,request.get('changes') or {})
            if action=='reports_summary': return reports.summarize(reports.load_settings(base)['report_dir'])
            from . import __version__
            return {'path':reports.write_meeting_report(store,request['meeting'],base,version=__version__,commit=None)}
        if action in ('glossary_import','glossary_summary','glossary_suggest','glossary_apply','glossary_apply_all','glossary_dismiss'):
            from . import glossary as G
            if action=='glossary_apply_all': return G.apply_all(store,request['meeting'],verified_only=request.get('verified_only',True) is not False)
            if action=='glossary_dismiss': return G.dismiss_suggestion(store,request['meeting'],int(request['segment']),request['original'])
            if action=='glossary_import': return G.import_file(request['path'],DATA_DIR if db is None else Path(db).parent,shared=db is None)   # tests and private copies stay local
            entries=G.load(DATA_DIR if db is None else Path(db).parent,ROOT)
            if action=='glossary_summary':
                paths=[p for p in G.sources(DATA_DIR if db is None else Path(db).parent) if p.is_file()]
                from_file=sum(1 for p in paths for l in p.read_text(encoding='utf-8').splitlines() if G.parse_line(l))
                return {'count':len(entries),'from_file':from_file,'from_vocabulary':max(0,len(entries)-from_file),'sample':[e['term'] for e in entries[:8]],'path':str(paths[0]) if paths else str(G.shared_path() or (DATA_DIR/G.FILENAME)),'shared':any(G.shared_path() and p==G.shared_path() for p in paths)}
            if action=='glossary_apply': return G.apply_suggestion(store,request['meeting'],int(request['segment']),request['original'],request['replacement'])
            llm=None
            if request.get('openrouter_model'):
                from .openrouter import OpenRouterClient,validate_analysis_model
                llm=OpenRouterClient().analysis(validate_analysis_model(request['openrouter_model']),consent=True)
            return {'suggestions':G.suggest_for_meeting(store,request['meeting'],entries,llm)}
        if action=='document':
            from .documents import build_document
            from .openrouter import OpenRouterClient,validate_analysis_model
            from .glossary import load as load_glossary, analysis_context
            if not request.get('openrouter_model'): raise ValueError('Belge hazırlama bulut modu gerektirir (Yazıya çevirme: OpenRouter)')
            llm=OpenRouterClient().analysis(validate_analysis_model(request['openrouter_model']),consent=True)
            doc=build_document(store,request['meeting'],request.get('kind','prd'),llm,segment_ids=request.get('segments'),glossary=analysis_context(load_glossary(DATA_DIR,ROOT)))
            if request.get('path'): Path(request['path']).write_text(doc['text'],encoding='utf-8')
            return {**doc,'path':request.get('path')}
        if action=='continuity':
            from .continuity import related_tasks,decision_history
            return {'related_tasks':related_tasks(store,request['meeting']),'decision_history':decision_history(store,request['meeting'])}
        if action=='supersede_task':
            from .continuity import supersede
            return supersede(store,request['old'],request['new'])
        if action=='agenda':
            from .agenda import build_agenda,render_agenda
            agenda=build_agenda(store,int(request.get('limit',5)));text=render_agenda(agenda)
            if request.get('path'): Path(request['path']).write_text(text,encoding='utf-8')
            return {'path':request.get('path'),'open_tasks':len(agenda['open_tasks']),'questions':len(agenda['questions']),'decisions':len(agenda['decisions']),'meetings':len(agenda['meetings'])}
        if action=='digest':
            from .digest import build_digest,render_digest
            digest=build_digest(store,request.get('day'),request.get('owner') or 'Boran');text=render_digest(digest)
            if request.get('path'): Path(request['path']).write_text(text,encoding='utf-8')
            return {'path':request.get('path'),'day':digest['day'],'tasks':len(digest['tasks']),'questions':len(digest['questions']),'decisions':len(digest['decisions']),'meetings':len(digest['meetings'])}
        if action in ('share_preview','share_export'):
            from .share import prepare_share
            from . import glossary as G
            kinds=request.get('kinds') if isinstance(request.get('kinds'),list) else ['transcript','summary']
            result=prepare_share(store,request['meeting'],include_segments=request.get('include_segments'),exclude_segments=request.get('exclude_segments'),
                mask_names=request.get('mask_names') is True,only_decisions=request.get('only_decisions') is True,kinds=kinds,glossary=G.load(DATA_DIR if db is None else Path(db).parent,ROOT))
            if action=='share_export':
                Path(request['path']).write_text(result['text'],encoding='utf-8')
                return {'path':request['path'],'masked_names':result['masked_names'],'segments':result['segments']}
            return {'text':result['text'],'masked_names':result['masked_names'],'segments':result['segments']}
        if action=='quality_report':
            from .quality import report
            return report(store)
        if action=='review_queue':
            from .review import review_queue
            return review_queue(store,request['meeting'])
        if action=='delete_meeting':
            return delete_meeting(store,request['meeting'],DATA_DIR if db is None else Path(db).parent)
        if action=='storage_report':
            return storage_report(store,DATA_DIR if db is None else Path(db).parent,db or DATA_DIR/'meeting-os.sqlite')
        if action=='storage_compact':
            from .cloud_finalize import compact_capture
            freed=0;count=0
            for m in store.meetings():
                b=compact_capture(store,m['id'])
                if b: freed+=b;count+=1
            return {'meetings':count,'bytes':freed}
        if action=='storage_cleanup':
            return storage_cleanup(store,DATA_DIR if db is None else Path(db).parent,days=request.get('days',30),dry_run=request.get('dry_run',True) is not False)
        if action=='cost_report':
            # Real OpenRouter transcription charges per piece (analysis calls are not metered by the provider response).
            from datetime import datetime,timezone
            rows=store.db.execute("SELECT m.id,m.title,m.created,sum(json_extract(c.usage,'$.cost')),sum(json_extract(c.usage,'$.seconds')),count(json_extract(c.usage,'$.cost')) FROM meetings m JOIN cloud_chunks c ON c.meeting=m.id GROUP BY m.id ORDER BY m.created DESC").fetchall()
            month=datetime.now(timezone.utc).strftime('%Y-%m')
            def bucket(rs): return {'usd':round(sum(float(r[3] or 0) for r in rs),4),'meetings':len(rs),'minutes':round(sum(float(r[4] or 0) for r in rs)/60,1)}
            this=[r for r in rows if (r[2] or '').startswith(month)]
            return {'month':{'label':month,**bucket(this)},'all':bucket(rows),'recent':[{'meeting':r[0],'title':r[1],'usd':round(float(r[3] or 0),4),'minutes':round(float(r[4] or 0)/60,1)} for r in rows[:5]]}
        if action=='meeting_context':
            # Calendar event that was live when the recording started: title + attendee names (read-only hints).
            cal=request.get('calendar') or {}
            names=[str(n).strip()[:80] for n in (cal.get('attendees') or []) if str(n).strip()][:30]
            row=store.db.execute('SELECT metadata FROM meetings WHERE id=?',(request['meeting'],)).fetchone()
            if not row: raise ValueError('Toplantı bulunamadı')
            meta=json.loads(row[0] or '{}')
            meta['calendar']={'title':str(cal.get('title') or '')[:120],'attendees':names,'start':cal.get('start'),'end':cal.get('end')}
            with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta,ensure_ascii=False),request['meeting']))
            return {'attendees':names}
        if action=='rename_meeting':
            title=(request.get('title') or '').strip()
            if not title or len(title)>200: raise ValueError('Başlık 1–200 karakter olmalı')
            with store.db:
                if not store.db.execute('UPDATE meetings SET title=? WHERE id=?',(title,request['meeting'])).rowcount: raise ValueError('Toplantı bulunamadı')
            return {'title':title}
        if action=='keep_meeting':
            from .recovery import metadata as read_metadata
            row=store.db.execute('SELECT metadata FROM meetings WHERE id=?',(request['meeting'],)).fetchone()
            if not row: raise ValueError('Toplantı bulunamadı')
            meta=json.loads(row[0] or '{}'); meta['keep']=bool(request.get('keep',True))
            with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta),request['meeting']))
            return {'keep':meta['keep']}
        if action=='check_duplicate':
            from .import_registry import digest_path,find_duplicate
            source=Path(request['path'])
            if not source.is_file(): raise ValueError('Ses dosyası bulunamadı')
            digest=digest_path(source); size=source.stat().st_size
            return {'duplicate':find_duplicate(store,digest,source.name,size),'digest':digest,'size':size}
        if action=='register_import_digest':
            return register_import_digest(store,request['meeting'],request.get('digest'),request.get('size'))
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
