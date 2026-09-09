"""Critical review queue: the few places a person should listen to instead of reading a whole transcript."""
import json
from .memory import Memory


def review_queue(store, mid):
    rows=store.segments(mid)
    items=[]
    seen_clusters=set()
    for r in rows:
        metrics=r.get('metrics') or {};identity=metrics.get('identity') or {};cluster=metrics.get('cluster')
        excerpt=(r.get('text') or '')[:120]
        base={'segment_id':r['id'],'start':r['start'],'speaker':r.get('speaker_name') or r.get('speaker'),'text':excerpt}
        if identity.get('suggested') and not r.get('speaker_name'):
            if (r['speaker'],'suggest') in seen_clusters: continue
            seen_clusters.add((r['speaker'],'suggest'))
            items.append({**base,'kind':'suggested_name','severity':1,'reason':f"Ses profili “{identity['suggested']}” kişisine benziyor (benzerlik {identity.get('similarity',0):.2f}); tek tıkla onaylayın veya düzeltin",'suggested':identity['suggested'],'speaker_key':r['speaker']})
            continue
        if 'speaker_ambiguous' in r['flags']:
            items.append({**base,'kind':'ambiguous','severity':1,'reason':'Çakışan konuşma; sağlayıcı iki kişiyi ayıramadı'});continue
        if 'cloud_diarization' in r['flags'] and not r.get('speaker_name') and cluster is not None and (r['speaker'],'unnamed') not in seen_clusters:
            total=sum(x['end']-x['start'] for x in rows if x['speaker']==r['speaker'] and x['source']==r['source'])   # linked clusters share one label
            seen_clusters.add((r['speaker'],'unnamed'))
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
        items.append({'segment_id':near['id'] if near else None,'start':secs,'speaker':(near or {}).get('speaker_name') or (near or {}).get('speaker'),'text':(near or {}).get('text','')[:120],
                      'kind':'marker','severity':0,'reason':f"Kayıt sırasında ⌘M ile işaretledin: {labels.get(marker.get('kind'),'Önemli an')}",'marker':marker.get('kind')})
    by_id={r['id']:r for r in rows}
    for sg in (meta.get('glossary_suggestions') or [])[:40]:
        row=by_id.get(sg.get('segment_id'))
        if not row or sg.get('original') not in (row.get('text') or ''): continue
        items.append({'segment_id':row['id'],'start':row['start'],'speaker':row.get('speaker_name') or row.get('speaker'),'text':row['text'][:120],'kind':'glossary','severity':2,
                      'reason':f"Sözlük: “{sg['original']}” muhtemelen “{sg['replacement']}”"+(f" · {sg['reason']}" if sg.get('reason') else (' · yerel eşleme, model doğrulamadı' if sg.get('source')=='local' else '')),
                      'original':sg['original'],'replacement':sg['replacement'],'verified':sg.get('source')=='llm'})
    memory=Memory(store)
    for task in memory.actions(meeting=mid):
        if task.get('state') in ('done','dismissed'): continue
        if not task.get('owner'):
            evidence=(task.get('payload') or {}).get('evidence') or []
            seg=evidence[0].get('segment_id') if evidence and isinstance(evidence[0],dict) else None
            items.append({'segment_id':seg,'start':None,'speaker':None,'text':task['title'][:120],'kind':'task_owner','severity':2,'reason':'Görev sahibi belirsiz; kaynağı dinleyip sahibini yazın','task':task['id']})
    items.sort(key=lambda i:(i['severity'],i['start'] if i['start'] is not None else 1e9))
    return {'items':items,'count':len(items)}
