"""Personal quality set: what the user corrected becomes a local reference for measuring models.

Nothing here trains a model. Text edits (text_edits table) give word-error references; speaker
renames (corrections table) and automatic identity results give a recognition scorecard."""
import json
import re
from datetime import date
from pathlib import Path

# Python twin of desktop Fillers.pattern (TranscriptBlocks.swift): “eee”, “ııı”, “hı hı”, stutters like “Bi-”.
FILLER=re.compile(r'(?<!\w)(?:[eEaAıIiİuUoOöÖüÜ]{2,}|[hH][ıiI]+(?:\s?[hH][ıiI]+)?|[^\W\d_]{1,3}-)(?=[\s.,;!?…]|$)[.,]?\s*')

def strip_fillers(text):
    return re.sub(r'\s{2,}',' ',FILLER.sub('',text or '')).strip()


def _words(text):
    return [w for w in re.split(r'[^\wçğıöşüÇĞİÖŞÜ]+',(text or '').casefold()) if w]


def wer(reference, hypothesis):
    """Word error rate with case/punctuation folded; 0.0 when identical, may exceed 1.0."""
    r=_words(reference);h=_words(hypothesis)
    if not r: return 0.0 if not h else 1.0
    prev=list(range(len(h)+1))
    for i,rw in enumerate(r,1):
        cur=[i]+[0]*len(h)
        for j,hw in enumerate(h,1):
            cur[j]=min(prev[j]+1,cur[j-1]+1,prev[j-1]+(rw!=hw))
        prev=cur
    return prev[-1]/len(r)


def wer_no_filler(reference, hypothesis):
    """WER after both sides drop fillers: a model that keeps “eee” verbatim is not wrong about the words."""
    return wer(strip_fillers(reference),strip_fillers(hypothesis))


def reference_set(store):
    """Segments whose text the user corrected: the corrected text is the reference, the model text the hypothesis.
    An edit later reverted to the original (a no-op pair) is not a correction and is dropped."""
    items=[]
    first={};latest={}
    for row in store.db.execute('SELECT meeting,segment,previous,replacement,created FROM text_edits ORDER BY created,id'):
        first.setdefault((row['meeting'],row['segment']),row);latest[(row['meeting'],row['segment'])]=row
    for (mid,sid),edit in latest.items():
        seg=store.db.execute('SELECT start,end,source,payload FROM segments WHERE meeting=? AND id=?',(mid,sid)).fetchone()
        if not seg: continue
        payload=json.loads(seg['payload']);meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
        original=payload.get('original_text') or first[(mid,sid)]['previous']
        if edit['replacement'].strip()==(original or '').strip(): continue
        paths=meta.get('paths') or {}
        items.append({'meeting':mid,'segment':sid,'start':seg['start'],'end':seg['end'],'source':seg['source'],'audio':paths.get(seg['source']) or paths.get('system'),
                      'model':(payload.get('metrics') or {}).get('model') or meta.get('model'),'model_text':original,'reference':edit['replacement'],
                      'wer':wer(edit['replacement'],original),'wer_no_filler':wer_no_filler(edit['replacement'],original)})
    return items


def identity_report(store):
    """Per cluster: what the voiceprint said vs what the user finally called it."""
    corrected={(r['meeting'],r['speaker']):r['name'] for r in store.db.execute('SELECT meeting,speaker,name FROM corrections WHERE speaker NOT LIKE ? ORDER BY created',('segment:%',))}
    seen=set();auto_ok=auto_wrong=suggest_ok=suggest_wrong=missed=unnamed=0
    for row in store.db.execute("SELECT meeting,speaker,speaker_name,payload FROM segments WHERE source='system'"):
        p=json.loads(row['payload']);m=p.get('metrics') or {};cl=m.get('cluster')
        if cl is None or (row['meeting'],cl) in seen: continue
        seen.add((row['meeting'],cl));ident=m.get('identity') or {}
        auto=ident.get('name');suggested=ident.get('suggested');final=corrected.get((row['meeting'],row['speaker'])) or row['speaker_name']
        if auto:
            if final==auto: auto_ok+=1
            else: auto_wrong+=1
        elif suggested:
            if final==suggested: suggest_ok+=1
            elif final: suggest_wrong+=1
            else: unnamed+=1
        elif final: missed+=1
        else: unnamed+=1
    total=auto_ok+auto_wrong+suggest_ok+suggest_wrong+missed+unnamed
    return {'clusters':total,'auto_correct':auto_ok,'auto_wrong':auto_wrong,'suggestion_confirmed':suggest_ok,'suggestion_rejected':suggest_wrong,'missed_known':missed,'still_unnamed':unnamed,
            'auto_precision':round(auto_ok/(auto_ok+auto_wrong),3) if auto_ok+auto_wrong else None}


def compare(store, models, client, *, consent=False, limit=20, encode=None, hint=None):
    """Re-transcribe corrected segments with the given models and score them against the user's text. Paid.
    `hint` is the glossary spelling hint (glossary.stt_hint), passed exactly as the real job passes it."""
    from .openrouter import _consent, validate_stt_model
    from .cloud_finalize import encode_piece
    _consent(consent)
    for m in models: validate_stt_model(m)
    encode=encode or encode_piece
    refs=[r for r in reference_set(store) if r['audio'] and Path(r['audio']).is_file()][:limit]
    if not refs: raise ValueError('Kalite seti boş: önce transkriptte metin düzeltmeleri yapın')
    scores={m:[] for m in models};clean={m:[] for m in models};cost={m:0.0 for m in models}
    for r in refs:
        audio=encode(r['audio'],r['start'],r['end'])
        for m in models:
            out=client.transcribe(audio,'ogg',model=m,consent=True,hint=hint)
            scores[m].append(wer(r['reference'],out['text']));clean[m].append(wer_no_filler(r['reference'],out['text']));cost[m]+=float((out.get('usage') or {}).get('cost') or 0)
    return {'segments':len(refs),'hint':bool(hint),'stored_model_mean_wer':_mean([r['wer'] for r in refs]),'stored_model_mean_wer_no_filler':_mean([r['wer_no_filler'] for r in refs]),
            'models':{m:{'mean_wer':_mean(v),'mean_wer_no_filler':_mean(clean[m]),'cost':round(cost[m],5)} for m,v in scores.items()}}


def _mean(values, digits=3): return round(sum(values)/len(values),digits) if values else None


def report(store):
    refs=reference_set(store)
    by_model={}
    for r in refs: by_model.setdefault(r['model'] or '?',[]).append(r)
    words=sum(len(_words(t)) for (t,) in store.db.execute("SELECT json_extract(payload,'$.text') FROM segments WHERE meeting IN (SELECT id FROM meetings WHERE status='complete')"))
    return {'text_edits':len(refs),'mean_wer_by_model':{m:_mean([r['wer'] for r in v]) for m,v in by_model.items()},
            'mean_wer_no_filler_by_model':{m:_mean([r['wer_no_filler'] for r in v]) for m,v in by_model.items()},
            'wer':_mean([r['wer'] for r in refs]),'wer_no_filler':_mean([r['wer_no_filler'] for r in refs]),
            'transcript_words':words,'edits_per_1000_words':round(1000*len(refs)/words,2) if words else None,'identity':identity_report(store)}


def replay_identity(store, threshold=None, margin=None):
    """Leave-one-meeting-out replay: every named speaker cluster of every finished meeting is scored against the
    profiles WITHOUT the samples that meeting contributed. Says whether today's threshold would have named it."""
    from .cloud_finalize import IDENTITY_THRESHOLD, IDENTITY_MARGIN, SOURCE_LABELS, linked_centroid
    threshold=IDENTITY_THRESHOLD if threshold is None else threshold;margin=IDENTITY_MARGIN if margin is None else margin
    clusters=[];people={}
    for m in store.meetings():
        if m['status']!='complete': continue
        groups={}
        for r in store.segments(m['id']):
            if r['source']=='mic' or not r.get('speaker_name') or r['speaker_name']==SOURCE_LABELS['mic']: continue
            groups.setdefault((r['source'],r['speaker'],r['speaker_name']),[]).append(r)
        for (source,speaker,name),members in groups.items():
            models={r.get('embedding_model') for r in members if r.get('embedding') and r.get('embedding_model')}
            if not models: continue
            model=max(models,key=lambda k:sum(1 for r in members if r.get('embedding_model')==k))
            centroid=linked_centroid(members,model)
            scores=store._scores(centroid,model,exclude=m['id'])
            seconds=round(sum(r['end']-r['start'] for r in members),1)
            top=[{'name':s['name'],'score':round(s['score'],3)} for s in scores[:2]]
            score=top[0]['score'] if top else None;gap=(scores[0]['score']-scores[1]['score']) if len(scores)>1 else (scores[0]['score']+1 if scores else None)
            named=top[0]['name'] if top and score>=threshold and gap>=margin else None
            if not any(s['name']==name for s in scores): outcome='no_profile'
            elif named==name: outcome='ok'
            elif named: outcome='wrong'
            elif score is not None and score>=threshold: outcome='abstained'   # over the threshold but two profiles too close
            else: outcome='missed'
            clusters.append({'meeting':m['id'],'title':m['title'],'speaker':speaker,'name':name,'seconds':seconds,'segments':len(members),'outcome':outcome,'named':named,
                             'score':score,'margin':round(gap,3) if gap is not None else None,'nearest':top})
            p=people.setdefault(name,{'ok':0,'wrong':0,'missed':0,'abstained':0,'no_profile':0});p[outcome]+=1
    counts={k:sum(c['outcome']==k for c in clusters) for k in ('ok','wrong','missed','abstained','no_profile')}
    return {'threshold':threshold,'margin':margin,'clusters':len(clusters),**counts,'people':people,'misses':[c for c in clusters if c['outcome'] in ('wrong','missed','abstained')],'items':clusters}


def replay_text(store):
    """The user's real corrections re-scored: no-op pairs dropped, fillers ignored (the reading view hides them too)."""
    refs=reference_set(store)
    by_model={}
    for r in refs: by_model.setdefault(r['model'] or '?',[]).append(r)
    return {'edits':len(refs),'mean_wer':_mean([r['wer'] for r in refs]),'mean_wer_no_filler':_mean([r['wer_no_filler'] for r in refs]),
            'by_model':{m:{'edits':len(v),'mean_wer':_mean([r['wer'] for r in v]),'mean_wer_no_filler':_mean([r['wer_no_filler'] for r in v])} for m,v in by_model.items()},
            'items':[{k:r[k] for k in ('meeting','segment','model','wer','wer_no_filler')} for r in refs]}


def replay(store, data_dir=None, *, identity=True, text=True, threshold=None, margin=None):
    """Run the replays, keep the full result under <data_dir>/quality/, return (summary, path)."""
    result={'date':date.today().isoformat()}
    if identity: result['identity']=replay_identity(store,threshold,margin)
    if text: result['text']=replay_text(store)
    folder=Path(data_dir or Path(store.path).parent)/'quality';folder.mkdir(parents=True,exist_ok=True)
    path=folder/f"replay-{result['date']}.json";path.write_text(json.dumps(result,ensure_ascii=False,indent=1),encoding='utf-8')
    summary={'path':str(path)}
    if identity:
        i=result['identity'];summary['identity']={k:i[k] for k in ('clusters','ok','wrong','missed','abstained','no_profile','threshold','margin')}
        summary['identity']['misses']=[{k:c[k] for k in ('meeting','speaker','name','seconds','outcome','nearest')} for c in i['misses']]
    if text: summary['text']={k:result['text'][k] for k in ('edits','mean_wer','mean_wer_no_filler')}
    return summary,result
