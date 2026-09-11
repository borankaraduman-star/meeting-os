"""Critical review queue: the few places a person should listen to instead of reading a whole transcript."""
import json
from .insights import first_evidence
from .intelligence import row_label
from .memory import Memory, RETIRED
from .reports import store_owner


MIN_NAMEABLE_SECONDS=4.0   # below this a diarization cluster is noise, not a voice the user should be asked to name
CONFLICT_LIMIT=5           # team spelling disagreements shown at once; the queue is not a settings screen

# ---------------------------------------------------------------------------
# Resolution
#
# A Kontrol item used to be a suggestion the queue recomputed from scratch every time: answering it changed
# nothing, so the same item came back at every visit and the only way to shrink the queue was to hide things.
# Every item now carries the version of the source it was derived from, and an answer is stored against that
# version. Answered for this version → never asked again. Source changes (the transcript was corrected, a new
# analysis ran) → the item is genuinely new and is asked again.
#
# "Geç" is not an answer about the content: it hides the item for this version and is counted on its own.
# Nothing here treats silence, a skip or an export as confirmation.
# ---------------------------------------------------------------------------
RESULTS=('correct','corrected','skipped')

try:   # the metrics half of the learning loop lands on its own branch; the merge must not need this file changed
    from .learning import record_event
except ImportError:   # pragma: no cover - exercised only before that branch merges
    record_event=None

def _event(store,action,**fields):
    """A metrics hook must never be able to fail a user action. The recorder lands on its own branch, so a
    keyword it does not know costs the detail, never the event."""
    if record_event is None:return None
    try:return record_event(store,action,**fields)
    except TypeError:
        try:return record_event(store,action)
        except Exception:return None
    except Exception:return None

def ensure_results(store):
    store.db.executescript('''
    CREATE TABLE IF NOT EXISTS review_results(id INTEGER PRIMARY KEY,meeting TEXT,item_key TEXT,kind TEXT,source_version TEXT,result TEXT,created TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS review_results_item ON review_results(meeting,item_key,source_version);
    ''')

def queue_key(item):
    """What makes a Kontrol item the same item on the next visit. Deliberately not its wording or its
    severity: a reason line that gains a decimal must not turn one answered question into a new one."""
    kind=item.get('kind') or ''
    if kind in ('suggested_name','unnamed_speaker','short_match'):tail=item.get('speaker_key') or str(item.get('segment_id'))
    elif kind in ('task_owner','task_review'):tail=item.get('task') or ''
    elif kind in ('glossary','word'):
        from .correction_memory import _fold
        tail=f"{item.get('segment_id')}:{_fold(item.get('original') or '')}"
    elif kind=='word_conflict':
        # A team disagreement is about a WORD, not a spot in this transcript: the same question anchored to a
        # different segment is the same question, and answering it once has to be enough.
        from .correction_memory import _fold
        tail=_fold(item.get('original') or '')
    elif kind=='marker':tail=f"{item.get('start')}"
    else:tail=str(item.get('segment_id'))
    return f'{kind}:{tail}'

def transcript_version(store,mid,memory=None):
    """The transcript this queue was read from. Correcting a word or naming a speaker changes it, and every
    answer given against the old text is re-asked — which is exactly right: the text is not what it was.

    `memory` is passed in by the queue, which has already paid for this meeting's fingerprint; the weekly
    debt walks every meeting, and computing it twice per meeting is a whole second transcript read each."""
    return 't:'+(memory or Memory(store)).current_hash(mid)[:16]

def task_version(task):
    """A task item's source is the analysis that produced it, not the whole transcript."""
    return 'a:'+str(task.get('analysis'))

def resolutions(store,mid):
    """(item key, source version) → result, for one meeting."""
    import sqlite3
    try:rows=list(store.db.execute('SELECT item_key,source_version,result FROM review_results WHERE meeting=?',(mid,)))
    except sqlite3.OperationalError:return {}
    return {(r['item_key'],r['source_version']):r['result'] for r in rows}

def resolve_review(store,mid,key,kind,source_version,result):
    """Answer one Kontrol item: doğru · düzeltildi · geçildi. The answer belongs to the source version it was
    given about, so a later correction to the same spot brings the item back rather than burying it."""
    key=(key or '').strip()
    if not key:raise ValueError('Kontrol maddesi gerekli')
    if result not in RESULTS:raise ValueError('Geçersiz kontrol sonucu')
    source_version=(source_version or '').strip() or transcript_version(store,mid)
    ensure_results(store)
    from .memory import now
    with store.db:
        store.db.execute('''INSERT INTO review_results(meeting,item_key,kind,source_version,result,created) VALUES(?,?,?,?,?,?)
                            ON CONFLICT(meeting,item_key,source_version) DO UPDATE SET result=excluded.result,kind=excluded.kind,created=excluded.created''',
                         (mid,key,kind or key.split(':')[0],source_version,result,now()))
    _event(store,'review_resolve',object=key,outcome=result,scope=kind or '',meeting=mid)
    return {'resolved':True,'key':key,'result':result,'source_version':source_version}

def reopen_review(store,mid,key,source_version=None):
    """Take an answer back — the item returns to the queue for the version it was answered on."""
    ensure_results(store)
    with store.db:
        if source_version:cur=store.db.execute('DELETE FROM review_results WHERE meeting=? AND item_key=? AND source_version=?',(mid,key,source_version))
        else:cur=store.db.execute('DELETE FROM review_results WHERE meeting=? AND item_key=?',(mid,key))
    return {'reopened':bool(cur.rowcount),'key':key}


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
    # Two teammates spell the same word differently and this Mac has no rule of its own: neither spelling is
    # applied (team_knowledge.team_rules) and the choice is asked here instead of being decided by whose Mac
    # published last. Answering teaches a local rule, which then wins silently everywhere (Codex #7).
    try:
        from .team_knowledge import team_conflicts
        from .correction_memory import _pattern as _word_pattern
        for conflict in team_conflicts(store)[:CONFLICT_LIMIT]:
            spellings=[conflict['original']]+[o['replacement'] for o in conflict['options']]
            patterns=[_word_pattern(w) for w in spellings]
            row=next((r for r in rows if any(p.search(r.get('text') or '') for p in patterns)),None)
            hosts=', '.join(sorted({o['host'] for o in conflict['options']}))
            items.append({'segment_id':row['id'] if row else None,'start':row['start'] if row else None,
                          'speaker':row_label(row,owner) if row else None,'text':(row.get('text') or '')[:120] if row else '',
                          'kind':'word_conflict','severity':2,
                          'reason':f"Ekipte iki yazım: {' / '.join(o['replacement'] for o in conflict['options'])} — hangisi? · {hosts}",
                          'original':conflict['original'],'options':conflict['options'],'source_version':conflict['version']})
    except Exception: pass   # a team question must never cost the user the rest of their queue

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
        seg=(first_evidence(task.get('payload') or {}) or {}).get('segment_id')
        if not task.get('owner'):
            items.append({'segment_id':seg,'start':None,'speaker':None,'text':task['title'][:120],'kind':'task_owner','severity':2,'reason':'Görev sahibi belirsiz; kaynağı dinleyip sahibini yazın','task':task['id'],'source_version':task_version(task)})
        elif (task.get('payload') or {}).get('needs_review'):
            # A task the analysis itself flagged — a doubtful owner, an ambiguous source, two readings of one
            # promise — used to be a badge on the task and nothing else. It is a question with an answer, so it
            # belongs in the queue with the same three buttons and the same resolution as everything else.
            items.append({'segment_id':seg,'start':None,'speaker':task.get('owner'),'text':task['title'][:120],'kind':'task_review','severity':2,
                          'reason':f"Görev kontrol bekliyor · sahibi “{task['owner']}”; kaynağı dinleyip doğrulayın",'task':task['id'],'source_version':task_version(task)})
    version=transcript_version(store,mid,memory)
    answered=resolutions(store,mid)
    kept=[];settled_items=0;skipped=0
    for item in items:
        item.setdefault('source_version',version)
        item['key']=queue_key(item)
        result=answered.get((item['key'],item['source_version']))
        if result is None:kept.append(item);continue
        if result=='skipped':skipped+=1
        else:settled_items+=1
    kept.sort(key=lambda i:(i['severity'],i['start'] if i['start'] is not None else 1e9))
    # `resolved` is what the person actually judged; `skipped` is counted apart because passing on an item is
    # not a statement that it was right. A queue made shorter by skipping is not a queue that got better.
    return {'items':kept,'count':len(kept),'resolved':settled_items,'skipped':skipped,'source_version':version}


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
    items=[];counts={};resolved=0;skipped=0
    for row in meetings:
        queue=review_queue(store,row['id'],data_dir)
        resolved+=queue.get('resolved',0);skipped+=queue.get('skipped',0)
        for item in queue['items']:
            items.append({**item,'meeting':row['id'],'meeting_title':row['title'],'created':row['created']})
            counts[item['kind']]=counts.get(item['kind'],0)+1
    items.sort(key=lambda i:i['start'] if i['start'] is not None else 1e9)
    items.sort(key=lambda i:i['created'] or '',reverse=True)   # stable: newest meeting first within one severity
    items.sort(key=lambda i:i['severity'])
    return {'days':int(days),'meetings':len(meetings),'counts':counts,'items':items,'count':len(items),'resolved':resolved,'skipped':skipped}
