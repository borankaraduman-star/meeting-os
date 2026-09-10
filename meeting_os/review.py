"""Critical review queue: the few places a person should listen to instead of reading a whole transcript."""
import json
from .insights import first_evidence
from .intelligence import row_label
from .memory import Memory, RETIRED
from .reports import store_owner


MIN_NAMEABLE_SECONDS=4.0   # below this a diarization cluster is noise, not a voice the user should be asked to name

def review_queue(store, mid, data_dir=None):
    rows=store.segments(mid)
    owner=store_owner(store)   # the mic label is a person: read raw, every queue item about the user said "Ben"
    items=[]
    seen_clusters=set()
    for r in rows:
        metrics=r.get('metrics') or {};identity=metrics.get('identity') or {};cluster=metrics.get('cluster')
        excerpt=(r.get('text') or '')[:120]
        base={'segment_id':r['id'],'start':r['start'],'speaker':row_label(r,owner),'text':excerpt}
        if identity.get('suggested') and not r.get('speaker_name'):
            if (r['speaker'],'suggest') in seen_clusters: continue
            if sum(x['end']-x['start'] for x in rows if x['speaker']==r['speaker'] and x['source']==r['source'])<MIN_NAMEABLE_SECONDS: continue
            seen_clusters.add((r['speaker'],'suggest'))
            items.append({**base,'kind':'suggested_name','severity':1,'reason':f"Ses profili “{identity['suggested']}” kişisine benziyor (benzerlik {identity.get('similarity',0):.2f}); tek tıkla onaylayın veya düzeltin",'suggested':identity['suggested'],'speaker_key':r['speaker']})
            continue
        if 'speaker_ambiguous' in r['flags']:
            items.append({**base,'kind':'ambiguous','severity':1,'reason':'Çakışan konuşma; sağlayıcı iki kişiyi ayıramadı'});continue
        if 'cloud_diarization' in r['flags'] and not r.get('speaker_name') and cluster is not None and (r['speaker'],'unnamed') not in seen_clusters:
            total=sum(x['end']-x['start'] for x in rows if x['speaker']==r['speaker'] and x['source']==r['source'])   # linked clusters share one label
            seen_clusters.add((r['speaker'],'unnamed'))
            # A cluster with a second or two of sound is a cough, a door, a word cut off by the diarizer — not a
            # person to name (Boran, 10 Sep 2026: "1-2 saniyelik noise'lara isim verilemez"). It stays in the
            # transcript under its label; nobody is asked about it.
            if total<MIN_NAMEABLE_SECONDS: continue
            sim=identity.get('similarity')
            why=f"Kayıtlı profillere yeterince benzemedi (en yakın {identity.get('candidate')} {sim:.2f})" if sim else 'Bu ses için kayıtlı profil yok'
            items.append({**base,'kind':'unnamed_speaker','severity':2,'reason':f'İsimsiz konuşmacı, toplam {total:.0f} sn · {why}','speaker_key':r['speaker']})
            continue
        if metrics.get('cluster_embedding') and r.get('speaker_name') and (cluster,'short') not in seen_clusters:
            seen_clusters.add((cluster,'short'))
            items.append({**base,'kind':'short_match','severity':3,'reason':f"Yalnız {metrics['cluster_embedding']:.1f} sn sesle tanındı; ismi bir kez kontrol edin",'speaker_key':r['speaker']})
            continue
        if 'low_asr_confidence' in r['flags'] or 'possible_non_speech' in r['flags'] or 'repetition' in r['flags']:
            items.append({**base,'kind':'asr','severity':3,'reason':'Model bu bölümde emin değil; dinleyerek kontrol edin'})
    meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0] or '{}')
    labels={'important':'Önemli an','decision':'Karar anı','task':'Bana görev','later':'Sonra bak'}
    for marker in meta.get('markers') or []:
        secs=marker.get('seconds',0);near=min(rows,key=lambda r:abs((r['start'] or 0)-secs)) if rows else None
        items.append({'segment_id':near['id'] if near else None,'start':secs,'speaker':row_label(near or {},owner),'text':(near or {}).get('text','')[:120],
                      'kind':'marker','severity':0,'reason':f"Kayıt sırasında ⌘M ile işaretledin: {labels.get(marker.get('kind'),'Önemli an')}",'marker':marker.get('kind')})
    by_id={r['id']:r for r in rows}
    from .correction_memory import taught_rules, dismissed_words, global_dismissals, _fold as _fold_word
    settled={_fold_word(r['original']) for r in taught_rules(store)} | {_fold_word(w) for w in global_dismissals(store)} | {_fold_word(w) for w in dismissed_words(store, mid)[1]}
    for sg in (meta.get('glossary_suggestions') or [])[:40]:
        row=by_id.get(sg.get('segment_id'))
        if not row or sg.get('original') not in (row.get('text') or ''): continue
        if _fold_word(sg.get('original') or '') in settled: continue   # taught or "bu doğru" once → never asked again
        items.append({'segment_id':row['id'],'start':row['start'],'speaker':row_label(row,owner),'text':row['text'][:120],'kind':'glossary','severity':2,
                      'reason':f"Sözlük: “{sg['original']}” muhtemelen “{sg['replacement']}”"+(f" · {sg['reason']}" if sg.get('reason') else (' · yerel eşleme, model doğrulamadı' if sg.get('source')=='local' else '')),
                      'original':sg['original'],'replacement':sg['replacement'],'verified':sg.get('source')=='llm'})
    from .correction_memory import word_candidates
    # A wrong word the model wrote confidently reads like a right one. The only thing that can tell them apart
    # is the list of words this team actually uses: what the user has taught, and the vocabulary.
    for word in word_candidates(store,mid,data_dir):
        row=by_id.get(word['segment_id'])
        if not row: continue
        items.append({'segment_id':row['id'],'start':row['start'],'speaker':row_label(row,owner),'text':(row.get('text') or '')[:120],'kind':'word','severity':2,
                      'reason':f"Kelime: “{word['original']}” muhtemelen “{word['replacement']}” · "+({'taught':'öğretilen kelime','team':'ekipten gelen kelime'}.get(word['source'],'sözlük terimi')),
                      'original':word['original'],'replacement':word['replacement'],'count':word['count']})
    memory=Memory(store)
    for task in memory.actions(meeting=mid):
        if task.get('state') in ('done',)+RETIRED: continue
        if not task.get('owner'):
            seg=(first_evidence(task.get('payload') or {}) or {}).get('segment_id')
            items.append({'segment_id':seg,'start':None,'speaker':None,'text':task['title'][:120],'kind':'task_owner','severity':2,'reason':'Görev sahibi belirsiz; kaynağı dinleyip sahibini yazın','task':task['id']})
    items.sort(key=lambda i:(i['severity'],i['start'] if i['start'] is not None else 1e9))
    return {'items':items,'count':len(items)}


def review_debt(store, days=7, data_dir=None):
    """Haftalık gözden geçirme borcu: pencerede kaydedilen tamamlanmış toplantıların Kontrol kuyrukları tek listede,
    önce en ağır madde, sonra en yeni toplantı. Read-only.

    The window is `days` local CALENDAR days ending today — the same seven days the karne means by "Son 7 gün".
    A rolling 168 hours put this morning's meeting and last Wednesday's in different weeks depending on the hour
    the user happened to open the tab, and the two screens disagreed about the same period."""
    from datetime import datetime,timedelta,timezone
    from .insights import local_day
    today=datetime.now(timezone.utc).astimezone().date()
    first=today-timedelta(days=max(1,int(days))-1)
    meetings=[]
    for row in store.meetings():
        if row['status']!='complete': continue
        day=local_day(row['created'])
        if day is None or not (first<=day<=today): continue
        meetings.append(row)
    items=[];counts={}
    for row in meetings:
        for item in review_queue(store,row['id'],data_dir)['items']:
            items.append({**item,'meeting':row['id'],'meeting_title':row['title'],'created':row['created']})
            counts[item['kind']]=counts.get(item['kind'],0)+1
    items.sort(key=lambda i:i['start'] if i['start'] is not None else 1e9)
    items.sort(key=lambda i:i['created'] or '',reverse=True)   # stable: newest meeting first within one severity
    items.sort(key=lambda i:i['severity'])
    return {'days':int(days),'meetings':len(meetings),'counts':counts,'items':items,'count':len(items)}
