"""Personal quality set: what the user corrected becomes a local reference for measuring models.

Nothing here trains a model. Text edits (text_edits table) give word-error references; speaker
renames (corrections table) and automatic identity results give a recognition scorecard."""
import json
import re
from pathlib import Path


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


def reference_set(store):
    """Segments whose text the user corrected: the corrected text is the reference, the model text the hypothesis."""
    items=[]
    latest={}
    for row in store.db.execute('SELECT meeting,segment,previous,replacement,created FROM text_edits ORDER BY created'):
        latest[(row['meeting'],row['segment'])]=row
    for (mid,sid),edit in latest.items():
        seg=store.db.execute('SELECT start,end,source,payload FROM segments WHERE meeting=? AND id=?',(mid,sid)).fetchone()
        if not seg: continue
        payload=json.loads(seg['payload']);meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
        original=payload.get('original_text') or edit['previous']
        paths=meta.get('paths') or {}
        items.append({'meeting':mid,'segment':sid,'start':seg['start'],'end':seg['end'],'source':seg['source'],'audio':paths.get(seg['source']) or paths.get('system'),
                      'model':(payload.get('metrics') or {}).get('model') or meta.get('model'),'model_text':original,'reference':edit['replacement'],'wer':wer(edit['replacement'],original)})
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


def report(store):
    refs=reference_set(store)
    by_model={}
    for r in refs: by_model.setdefault(r['model'] or '?',[]).append(r['wer'])
    return {'text_edits':len(refs),'mean_wer_by_model':{m:round(sum(v)/len(v),3) for m,v in by_model.items()},'identity':identity_report(store)}


def compare(store, models, client, *, consent=False, limit=20, encode=None):
    """Re-transcribe corrected segments with the given models and score them against the user's text. Paid."""
    from .openrouter import _consent, validate_stt_model
    from .cloud_finalize import encode_piece
    _consent(consent)
    for m in models: validate_stt_model(m)
    encode=encode or encode_piece
    refs=[r for r in reference_set(store) if r['audio'] and Path(r['audio']).is_file()][:limit]
    if not refs: raise ValueError('Kalite seti boş: önce transkriptte metin düzeltmeleri yapın')
    scores={m:[] for m in models};cost={m:0.0 for m in models};baseline=[]
    for r in refs:
        audio=encode(r['audio'],r['start'],r['end'])
        baseline.append(r['wer'])
        for m in models:
            out=client.transcribe(audio,'ogg',model=m,consent=True)
            scores[m].append(wer(r['reference'],out['text']));cost[m]+=float((out.get('usage') or {}).get('cost') or 0)
    return {'segments':len(refs),'stored_model_mean_wer':round(sum(baseline)/len(baseline),3),
            'models':{m:{'mean_wer':round(sum(v)/len(v),3),'cost':round(cost[m],5)} for m,v in scores.items()}}
