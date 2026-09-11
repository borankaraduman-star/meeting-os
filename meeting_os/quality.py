"""Personal quality set: what the user corrected becomes a local reference for measuring models.

Nothing here trains a model. Text edits (text_edits table) give word-error references; speaker
renames (corrections table) and automatic identity results give a recognition scorecard."""
import json
import re
from datetime import date, datetime, timedelta, timezone
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


def _reference_item(store, mid, sid, original, reference, via, _meta):
    """One (model said / user meant) pair, with the audio and the model behind it, or None when the pair is a
    no-op. Shared by the two ways a user corrects text: the Düzelt box and "Düzelt ve öğret"."""
    if reference is None or original is None: return None
    if reference.strip()==original.strip(): return None
    seg=store.db.execute('SELECT start,end,source,payload FROM segments WHERE meeting=? AND id=?',(mid,sid)).fetchone()
    if not seg: return None
    payload=json.loads(seg['payload'])
    if mid not in _meta: _meta[mid]=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
    paths=_meta[mid].get('paths') or {}
    return {'meeting':mid,'segment':sid,'start':seg['start'],'end':seg['end'],'source':seg['source'],'audio':paths.get(seg['source']) or paths.get('system'),
            'model':(payload.get('metrics') or {}).get('model') or _meta[mid].get('model'),'model_text':original,'reference':reference,'via':via,
            'wer':wer(reference,original),'wer_no_filler':wer_no_filler(reference,original)}


def reference_set(store):
    """Segments whose text the user corrected: the corrected text is the reference, the model text the hypothesis.
    An edit later reverted to the original (a no-op pair) is not a correction and is dropped.

    BOTH ways of correcting a word count. The Düzelt box writes `text_edits`; "Düzelt ve öğret" (the word the
    user teaches from the transcript) rewrites the segment itself and writes no edit row at all, so half of
    the user's text corrections were invisible to every measurement built on this set — the teaching path,
    which is the one the product pushes (Codex, 11 Sep 2026, P0 #1). A segment that has both is counted once:
    the hand-typed text is the user's last word on it."""
    items=[];meta={}
    first={};latest={}
    for row in store.db.execute('SELECT meeting,segment,previous,replacement,created FROM text_edits ORDER BY created,id'):
        first.setdefault((row['meeting'],row['segment']),row);latest[(row['meeting'],row['segment'])]=row
    for (mid,sid),edit in latest.items():
        seg=store.db.execute('SELECT payload FROM segments WHERE meeting=? AND id=?',(mid,sid)).fetchone()
        if not seg: continue
        original=json.loads(seg['payload']).get('original_text') or first[(mid,sid)]['previous']
        item=_reference_item(store,mid,sid,original,edit['replacement'],'text_edit',meta)
        if item: items.append(item)
    for row in store.db.execute("""SELECT meeting,id,payload FROM segments
            WHERE json_extract(payload,'$.metrics.word_corrections') IS NOT NULL AND json_extract(payload,'$.pre_word_text') IS NOT NULL"""):
        if (row['meeting'],row['id']) in latest: continue   # the user later retyped this segment; that is the reference
        payload=json.loads(row['payload'])
        item=_reference_item(store,row['meeting'],row['id'],payload.get('pre_word_text'),payload.get('word_text') or payload.get('text'),'word_teach',meta)
        if item: items.append(item)
    return sorted(items,key=lambda r:(r['meeting'],r['segment']))


def _pinned(store):
    """(meeting, segment id) of every piece the user moved to someone else with "Yalnız bu bölüm": the model was
    right about the cluster, so such a piece must not stand in for the cluster's verdict."""
    out=set()
    for r in store.db.execute("SELECT meeting,speaker FROM corrections WHERE speaker LIKE 'segment:%' AND json_extract(feedback,'$.pin')=1"):
        try: out.add((r['meeting'],int(r['speaker'].split(':',1)[1])))
        except ValueError: pass
    return out

def identity_report(store, meeting=None):
    """Per cluster: what the voiceprint said vs what the user finally called it.

    An automatic name the user NEVER TOUCHED is `unreviewed`, not a success. The transcript shows the
    automatic name in `speaker_name`, so comparing the final label with the guess used to agree with itself
    and every untouched cluster was counted as proof the model was right — twenty automatic names nobody
    looked at read as twenty human confirmations (Codex, 11 Sep 2026, P0 #1, the risk paragraph). Only a
    naming the user actually made judges the guess: it either confirms it (`verified`) or overrules it
    (`falsified`), compared folded, so retyping "Ayşe" as "Ayse" confirms the person.

    `auto_correct`/`auto_wrong` stay as the names the scorecard and the reports already read; what changed is
    that `auto_correct` now means verified, and `auto_precision` is measured over reviewed clusters only.

    `meeting` narrows the whole count to one meeting (1.2.82): a per-meeting report carrying the DB-wide
    scorecard made every meeting repeat the same totals, and adding two reports counted clusters twice."""
    from .store import fold_name
    corrected={(r['meeting'],r['speaker']):r['name'] for r in store.db.execute('SELECT meeting,speaker,name FROM corrections WHERE speaker NOT LIKE ? ORDER BY created',('segment:%',))}
    pinned=_pinned(store)
    seen=set();auto_ok=auto_wrong=auto_untouched=suggest_ok=suggest_wrong=missed=unnamed=0
    sql="SELECT id,meeting,speaker,speaker_name,payload FROM segments WHERE source='system'"+(' AND meeting=?' if meeting else '')
    for row in store.db.execute(sql,(meeting,) if meeting else ()):
        p=json.loads(row['payload']);m=p.get('metrics') or {};cl=m.get('cluster')
        if cl is None or (row['meeting'],cl) in seen or (row['meeting'],row['id']) in pinned: continue   # a pinned piece is not the cluster's verdict
        seen.add((row['meeting'],cl));ident=m.get('identity') or {}
        auto=ident.get('name');suggested=ident.get('suggested')
        # What the user decided, if anything: a naming row for this cluster, or the verdict a naming settled.
        decided=corrected.get((row['meeting'],row['speaker'])) or ident.get('settled')
        final=decided or row['speaker_name']
        if auto:
            if not decided: auto_untouched+=1
            elif fold_name(decided)==fold_name(auto): auto_ok+=1
            else: auto_wrong+=1
        elif suggested:
            if final==suggested: suggest_ok+=1
            elif final: suggest_wrong+=1
            else: unnamed+=1
        elif final: missed+=1
        else: unnamed+=1
    total=auto_ok+auto_wrong+auto_untouched+suggest_ok+suggest_wrong+missed+unnamed
    return {'clusters':total,'auto_verified':auto_ok,'auto_falsified':auto_wrong,'auto_unreviewed':auto_untouched,
            'auto_correct':auto_ok,'auto_wrong':auto_wrong,'suggestion_confirmed':suggest_ok,'suggestion_rejected':suggest_wrong,'missed_known':missed,'still_unnamed':unnamed,
            'auto_precision':round(auto_ok/(auto_ok+auto_wrong),3) if auto_ok+auto_wrong else None,
            # `meeting`: these numbers are this meeting's own and may be added up across meetings.
            # `snapshot`: the whole database as it stands, which may not — aggregation has to skip it.
            'scope':'meeting' if meeting else 'database','snapshot':not meeting}


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
            'transcript_words':words,'edits_per_1000_words':round(1000*len(refs)/words,2) if words else None,'identity':identity_report(store),'progress':learning_progress(store)}


def learning_progress(store, weeks=6):
    """Q10: is the tool getting better week by week? Per ISO week of the meeting date: how many voices it
    named by itself (and how many of those the user overruled), how much text the user still had to fix."""
    corrected={(r['meeting'],r['speaker']):(r['name'],r['previous_name'] if 'previous_name' in r.keys() else None) for r in store.db.execute('SELECT * FROM corrections WHERE speaker NOT LIKE ? ORDER BY created',('segment:%',))}
    week_of={};title_of={}
    for r in store.db.execute("SELECT id,created FROM meetings WHERE status='complete'"):
        try: d=datetime.fromisoformat(r['created']); week_of[r['id']]=f'{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}'
        except (TypeError,ValueError): continue
    rows={}
    def bucket(mid):
        w=week_of.get(mid)
        if w is None: return None
        return rows.setdefault(w,{'week':w,'meetings':set(),'clusters':0,'auto':0,'auto_wrong':0,'suggested':0,'suggested_ok':0,'named_by_user':0,'unnamed':0,'text_edits':0,'words':0})
    seen=set();pinned=_pinned(store)
    for row in store.db.execute("SELECT id,meeting,speaker,speaker_name,payload FROM segments WHERE source='system'"):
        b=bucket(row['meeting'])
        if b is None: continue
        p=json.loads(row['payload']);m=p.get('metrics') or {};cl=m.get('cluster')
        b['words']+=len(_words(p.get('text') or ''));b['meetings'].add(row['meeting'])
        if cl is None or (row['meeting'],cl) in seen or (row['meeting'],row['id']) in pinned: continue
        seen.add((row['meeting'],cl));ident=m.get('identity') or {};b['clusters']+=1
        final=(corrected.get((row['meeting'],row['speaker'])) or (row['speaker_name'],None))[0]
        if ident.get('name'):
            b['auto']+=1
            if final and final!=ident['name']: b['auto_wrong']+=1
        elif ident.get('suggested'):
            b['suggested']+=1
            if final==ident['suggested']: b['suggested_ok']+=1
            elif final: b['named_by_user']+=1
            else: b['unnamed']+=1
        elif final: b['named_by_user']+=1
        else: b['unnamed']+=1
    for r in store.db.execute('SELECT meeting FROM text_edits'):
        b=bucket(r['meeting'])
        if b is not None: b['text_edits']+=1
    out=[]
    for w in sorted(rows)[-weeks:]:
        b=rows[w];known=b['auto']+b['suggested_ok']+b['named_by_user']
        out.append({**b,'meetings':len(b['meetings']),'auto_share':round((b['auto']-b['auto_wrong'])/known,2) if known else None,
                    'edits_per_1000_words':round(1000*b['text_edits']/b['words'],1) if b['words'] else None})
    return out


def replay_identity(store, threshold=None, margin=None):
    """Leave-one-meeting-out replay: every named speaker cluster of every finished meeting is scored against the
    profiles WITHOUT the samples that meeting contributed. Says whether today's threshold would have named it."""
    from .cloud_finalize import IDENTITY_THRESHOLD, IDENTITY_MARGIN, source_labels, linked_centroid
    from .reports import settings_owner
    threshold=IDENTITY_THRESHOLD if threshold is None else threshold;margin=IDENTITY_MARGIN if margin is None else margin
    mic=source_labels(settings_owner(Path(store.path).parent))['mic']   # the user's own voice is not a profile to score
    clusters=[];people={}
    for m in store.meetings():
        if m['status']!='complete': continue
        groups={}
        for r in store.segments(m['id']):
            if r['source']=='mic' or not r.get('speaker_name') or r['speaker_name']==mic: continue
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
            bar=store.person_threshold(top[0]['name'],threshold,exclude=m['id']) if top else threshold   # this meeting's own corrections do not lower its own bar
            named=top[0]['name'] if top and score>=bar and gap>=margin else None
            if not any(s['name']==name for s in scores): outcome='no_profile'
            elif named==name: outcome='ok'
            elif named: outcome='wrong'
            elif score is not None and score>=bar: outcome='abstained'   # over the threshold but two profiles too close
            else: outcome='missed'
            clusters.append({'meeting':m['id'],'title':m['title'],'speaker':speaker,'name':name,'seconds':seconds,'segments':len(members),'outcome':outcome,'named':named,
                             'score':score,'margin':round(gap,3) if gap is not None else None,'threshold_used':round(bar,3),'nearest':top})
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


MAX_PAIRS=400


def rule_pairs(store, limit=MAX_PAIRS):
    """The (raw text, final text) pairs this Mac can re-run word rules over: segments where something changed
    the text and the copy from before it survives (`pre_auto_text`, `pre_word_text`, `original_text`). Newest
    last, capped — a replay is a regression check, not a full-table scan on every open.

    Both halves stay on this Mac. Nothing here is uploaded, shared or written into a report; it is the same
    local evidence `reference_set` already reads for word error rates."""
    out=[]
    for r in store.db.execute("""SELECT id,meeting,payload FROM segments WHERE payload LIKE '%pre_auto_text%'
                                 OR payload LIKE '%pre_word_text%' OR payload LIKE '%original_text%' ORDER BY id DESC LIMIT ?""",(int(limit),)):
        try: payload=json.loads(r['payload'])
        except (TypeError,ValueError): continue
        raw=_raw_text(payload);final=payload.get('text') or ''
        if not raw or raw==final: continue
        metrics=payload.get('metrics') or {}
        was=[a.get('original') or '' for a in (metrics.get('auto_corrections') or [])+(metrics.get('word_corrections') or []) if a.get('original')]
        out.append({'meeting':r['meeting'],'segment':r['id'],'raw':raw,'final':final,'was':was})
    return out[::-1]


def replay_rules(store, pairs=None, rules=None, data_dir=None):
    """Would TODAY's word rules produce the text the user ended up with? (Codex #7, "mevcut metin replay'i
    yeni kuralın etkisini yeniden uygulayarak sınamıyor".)

    `replay_text` scores what the model got wrong. It says nothing about the rules, because the pairs it reads
    were produced by whatever rule set was in force at the time. This one takes the same saved pairs and runs
    the CURRENT set over the raw half:

    * `matched` — today's rules turn the raw text into exactly what the user kept.
    * `mismatched` — they do not. That is not automatically a regression: the user may have edited the sentence
      for other reasons, which is why the mismatching pairs are listed rather than counted into a score.
    * `unchanged` — today's rules do nothing at all to that raw text.

    Per rule, `applied` is how many pairs it rewrites now and `was_applied` how many it rewrote then, so an old
    and a new rule set can be compared on one fixed set of local examples. A rule that only appears in the
    history is listed as `retired`. `version` fingerprints the rule set the numbers belong to.

    Pure with respect to the database: nothing is written, no segment is touched, no rule is changed."""
    from . import correction_memory as cm
    rules=cm.all_rules(store) if rules is None else list(rules)
    pairs=rule_pairs(store) if pairs is None else list(pairs)
    plan=cm.compile_rules(rules,data_dir)
    def row(original,replacement,source,state):
        return {'original':original,'replacement':replacement,'source':source,'state':state,
                'applied':0,'matched':0,'mismatched':0,'was_applied':0}
    by_rule={cm._fold(r['original']):row(r['original'],r['replacement'],r.get('source','learned'),'current') for r in rules}
    matched=mismatched=unchanged=0;misses=[]
    for pair in pairs:
        produced,applied=cm.apply_to_text(pair['raw'],plan)
        ok=produced==pair['final']
        if ok: matched+=1
        else:
            mismatched+=1
            if len(misses)<20: misses.append({'meeting':pair.get('meeting'),'segment':pair.get('segment'),
                                              'rules':[a['original'] for a in applied],'changed':produced!=pair['raw']})
        if produced==pair['raw']: unchanged+=1
        for a in applied:
            r=by_rule.setdefault(cm._fold(a['original']),row(a['original'],a['replacement'],'?','current'))
            r['applied']+=1;r['matched' if ok else 'mismatched']+=1
        for original in pair.get('was') or []:
            by_rule.setdefault(cm._fold(original),row(original,'','?','retired'))['was_applied']+=1
    return {'pairs':len(pairs),'matched':matched,'mismatched':mismatched,'unchanged':unchanged,'rules':len(rules),
            'version':cm.rules_version(rules),'mismatches':misses,
            'by_rule':sorted(by_rule.values(),key=lambda r:(-r['applied'],-r['was_applied'],r['original']))}


def replay(store, data_dir=None, *, identity=True, text=True, timeline=False, threshold=None, margin=None):
    """Run the replays, keep the full result under <data_dir>/quality/, return (summary, path).

    `identity` is the leave-one-meeting-out regression check and stays exactly what it was; `timeline` is the
    honest cold-start measurement, where a meeting may only use evidence older than itself."""
    result={'date':date.today().isoformat()}
    if identity: result['identity']=replay_identity(store,threshold,margin)
    if timeline: result['timeline']=replay_timeline(store,threshold,margin)
    if text:
        result['text']=replay_text(store)
        # The text replay scores the MODEL; this scores the RULES, on the same local pairs.
        result['text']['rules']=replay_rules(store,data_dir=data_dir)
    folder=Path(data_dir or Path(store.path).parent)/'quality';folder.mkdir(parents=True,exist_ok=True)
    path=folder/f"replay-{result['date']}.json";path.write_text(json.dumps(result,ensure_ascii=False,indent=1),encoding='utf-8')
    summary={'path':str(path)}
    if identity:
        i=result['identity'];summary['identity']={k:i[k] for k in ('clusters','ok','wrong','missed','abstained','no_profile','threshold','margin')}
        summary['identity']['misses']=[{k:c[k] for k in ('meeting','speaker','name','seconds','outcome','nearest')} for c in i['misses']]
    if timeline:
        t=result['timeline']
        summary['timeline']={k:t[k] for k in ('meetings','clusters','auto_correct','auto_wrong','abstained_wrong','abstained_ok','unknown_named',
                                              'auto_precision','known_recall','undated_samples','threshold','margin')}
    if text:
        summary['text']={k:result['text'][k] for k in ('edits','mean_wer','mean_wer_no_filler')}
        summary['text']['rules']={k:result['text']['rules'][k] for k in ('pairs','matched','mismatched','unchanged','rules','version')}
    return summary,result


# ---------------------------------------------------------------- time-ordered identity replay

def _sample_rows(store):
    """Every live voice sample with the date it came into existence. `created` is stamped at insert since
    1.2.82 and backfilled from the meeting a sample's provenance names; a sample that is still undated (a
    hand enrolment from an older install, a team import) has no place on a timeline and is counted apart."""
    rows=[];undated=0
    for r in store.db.execute('SELECT id,name,model,vector,provenance,created FROM samples WHERE deleted_by IS NULL'):
        created=r['created']
        if not created: undated+=1;continue
        try: vector=json.loads(r['vector'])
        except (TypeError,ValueError): continue
        rows.append({'id':r['id'],'name':r['name'],'model':r['model'],'vector':vector,'provenance':r['provenance'] or '','created':created})
    return rows,undated


def _rejection_rows(store):
    rows=[];undated=0
    for r in store.db.execute('SELECT name,model,vector,created FROM rejections'):
        if not r['created']: undated+=1;continue
        try: vector=json.loads(r['vector'])
        except (TypeError,ValueError): continue
        rows.append({'name':r['name'],'model':r['model'],'vector':vector,'created':r['created']})
    return rows,undated


def _scores_before(store, vector, model, cutoff, samples, rejections):
    """store._scores for one moment in time: only the samples and rejections that existed before `cutoff`.
    Same arithmetic as the live path (centroid + best single sample, a rejection vetoes the person), so the
    only difference between this and the regression replay is WHICH evidence is allowed to answer."""
    from .store import cosine, unit, Store
    v=unit(vector);groups={}
    for s in samples:
        if s['model']!=model or s['created']>=cutoff or len(s['vector'])!=len(v): continue
        groups.setdefault(s['name'],[]).append(s['vector'])
    vetoed=set()
    for r in rejections:
        if r['model']!=model or r['created']>=cutoff or r['name'] not in groups or len(r['vector'])!=len(v): continue
        if cosine(v,unit(r['vector']))>=Store.REJECT_SIMILARITY: vetoed.add(r['name'])
    out=[]
    for name,xs in groups.items():
        if name in vetoed: continue
        try: centroid=unit([sum(col)/len(xs) for col in zip(*xs)])
        except ValueError: continue
        best=max(cosine(v,unit(x)) for x in xs)
        out.append({'name':name,'score':(cosine(v,centroid)+best)/2,'samples':len(xs)})
    return sorted(out,key=lambda s:-s['score'])


def _bar_before(store, name, base, cutoff):
    """The personal bar as it stood before `cutoff`: the same ±0.01/±0.02 arithmetic as the live path, counted
    from the corrections that had actually happened by then instead of from today's profile_stats totals."""
    confirmed=wrong=0
    for r in store.db.execute('SELECT feedback,created FROM corrections WHERE feedback IS NOT NULL'):
        if not r['created'] or r['created']>=cutoff: continue
        try: f=json.loads(r['feedback'] or '{}')
        except ValueError: continue
        if f.get('confirmed')==name: confirmed+=1
        if f.get('wrong')==name: wrong+=1
    return store.personal_bar(base,confirmed,wrong)


def replay_timeline(store, threshold=None, margin=None):
    """Cold-start replay: each meeting is judged with ONLY the evidence that existed before it started.

    `replay_identity` leaves one meeting out of the profiles and keeps everything else, including samples from
    meetings that had not happened yet — a useful regression check, but it cannot say what the app would have
    done on the day. Here the cutoff is the meeting's own `created`, so a person is “known” only if an earlier
    meeting had already produced a sample for them. That makes the unknown-person case measurable, which is the
    case the review asked for: a cluster whose true person has no earlier sample must be ABSTAINED, never named.

    Five outcomes, per meeting and in total:
      `auto_correct`     the right person was named by themselves,
      `auto_wrong`       a known person was named as somebody else,
      `abstained_wrong`  a known person was left unnamed (the evidence was there and did not carry),
      `abstained_ok`     an unknown person was left unnamed — the correct answer, counted as such,
      `unknown_named`    an unknown person was given a name; the worst outcome, and invisible to `replay_identity`.
    """
    from .cloud_finalize import IDENTITY_THRESHOLD, IDENTITY_MARGIN, source_labels, linked_centroid
    from .reports import settings_owner
    threshold=IDENTITY_THRESHOLD if threshold is None else threshold;margin=IDENTITY_MARGIN if margin is None else margin
    mic=source_labels(settings_owner(Path(store.path).parent))['mic']
    samples,undated_samples=_sample_rows(store);rejections,undated_rejections=_rejection_rows(store)
    OUTCOMES=('auto_correct','auto_wrong','abstained_wrong','abstained_ok','unknown_named')
    meetings=[m for m in store.meetings() if m['status']=='complete' and m['created']]
    meetings.sort(key=lambda m:m['created'])   # store.meetings() is newest first; a timeline is not
    per_meeting=[];items=[];people={}
    for m in meetings:
        cutoff=m['created'];groups={}
        for r in store.segments(m['id']):
            if r['source']=='mic' or not r.get('speaker_name') or r['speaker_name']==mic: continue
            groups.setdefault((r['source'],r['speaker'],r['speaker_name']),[]).append(r)
        counts={k:0 for k in OUTCOMES};clusters=0
        for (source,speaker,name),members in groups.items():
            models={r.get('embedding_model') for r in members if r.get('embedding') and r.get('embedding_model')}
            if not models: continue
            model=max(models,key=lambda k:sum(1 for r in members if r.get('embedding_model')==k))
            centroid=linked_centroid(members,model)
            scores=_scores_before(store,centroid,model,cutoff,samples,rejections)
            known=any(s['name']==name for s in scores)   # this person had a sample BEFORE this meeting
            top=[{'name':s['name'],'score':round(s['score'],3)} for s in scores[:2]]
            score=top[0]['score'] if top else None
            gap=(scores[0]['score']-scores[1]['score']) if len(scores)>1 else (scores[0]['score']+1 if scores else None)
            bar=_bar_before(store,top[0]['name'],threshold,cutoff) if top else threshold
            named=top[0]['name'] if top and score>=bar and gap>=margin else None
            if named==name: outcome='auto_correct'
            elif named and known: outcome='auto_wrong'
            elif named: outcome='unknown_named'
            elif known: outcome='abstained_wrong'
            else: outcome='abstained_ok'
            counts[outcome]+=1;clusters+=1
            items.append({'meeting':m['id'],'created':m['created'],'speaker':speaker,'name':name,'known_before':known,'outcome':outcome,'named':named,
                          'seconds':round(sum(r['end']-r['start'] for r in members),1),'score':score,'margin':round(gap,3) if gap is not None else None,
                          'threshold_used':round(bar,3),'nearest':top})
            p=people.setdefault(name,{k:0 for k in OUTCOMES});p[outcome]+=1
        if clusters: per_meeting.append({'meeting':m['id'],'title':m['title'],'created':m['created'],'clusters':clusters,**counts})
    totals={k:sum(r[k] for r in per_meeting) for k in OUTCOMES}
    clusters=sum(r['clusters'] for r in per_meeting)
    named_total=totals['auto_correct']+totals['auto_wrong']+totals['unknown_named']
    return {'threshold':threshold,'margin':margin,'meetings':len(per_meeting),'clusters':clusters,**totals,
            'auto_precision':round(totals['auto_correct']/named_total,3) if named_total else None,
            'known_recall':round(totals['auto_correct']/(totals['auto_correct']+totals['auto_wrong']+totals['abstained_wrong']),3) if (totals['auto_correct']+totals['auto_wrong']+totals['abstained_wrong']) else None,
            'undated_samples':undated_samples,'undated_rejections':undated_rejections,
            'per_meeting':per_meeting,'people':people,'items':items}


# ---------------------------------------------------------------- daily numeric quality summary (Codex #10)

DAILY_DIR='quality'
DAILY_FILE='daily.json'
DAILY_KEEP=45            # days kept locally; the heartbeat carries the newest DAILY_SHARE of them
DAILY_SHARE=14
# What the trend alert calls an error: every metric here is a number of times the user had to put
# something right. Each is a rate over its own denominator; the trend pools numerators and denominators.
ERROR_METRICS=('names_falsified','word_repeat_errors','summary_edits','task_edits')
TREND_MIN_OBSERVATIONS=20   # below this the rate is noise; the review asks for no alert at all
TREND_RISE=0.30             # a rise of 30 % or more in the pooled error rate


def ratio(n, d):
    """A measured number with the scope it was measured in. An empty denominator is `null`, never 0 % and
    never 100 %: nothing was observed, so nothing is claimed."""
    n=int(n or 0);d=int(d or 0)
    return {'n':n,'d':d,'rate':round(n/d,4) if d else None}


def _table(store, name):
    return bool(store.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())


def _columns(store, name):
    return {r[1] for r in store.db.execute(f'PRAGMA table_info({name})')} if _table(store,name) else set()


def _day_of(created):
    from .insights import local_day
    return local_day(created)


def _bounds(day):
    """A UTC window that certainly contains the local day, for the SQL prefilter. The exact answer is still
    `local_day`; this only keeps an hourly heartbeat from reading every analysis this Mac has ever saved."""
    return (day-timedelta(days=2)).isoformat(),(day+timedelta(days=2)).isoformat()


def _raw_text(payload):
    """What the transcript said before the app rewrote anything: the pre-pass copies an automatic word fix
    leaves behind, then the user's own `original_text`, then today's text."""
    return payload.get('pre_auto_text') or payload.get('pre_word_text') or payload.get('original_text') or payload.get('text') or ''


def _names_metrics(store, meeting_ids):
    """Automatic speaker names of the day's meetings, and what a human did about them. An untouched automatic
    name is NOT a confirmation (Codex #1): it is counted as unreviewed and nothing else."""
    if not meeting_ids: return {k:ratio(0,0) for k in ('names_reviewed','names_falsified','names_unreviewed')}
    corrected={(r['meeting'],r['speaker']):r['name'] for r in store.db.execute('SELECT meeting,speaker,name FROM corrections WHERE speaker NOT LIKE ? ORDER BY created',('segment:%',))}
    pinned=_pinned(store);seen=set();auto=reviewed=falsified=0
    # By meeting, never over the whole segments table: this runs on every heartbeat and a year of transcripts
    # is a lot of rows to read for one day's numbers.
    rows=[r for mid in sorted(meeting_ids) for r in store.db.execute("SELECT id,meeting,speaker,payload FROM segments WHERE source='system' AND meeting=?",(mid,))]
    for row in rows:
        p=json.loads(row['payload']);m=p.get('metrics') or {};cl=m.get('cluster')
        if cl is None or (row['meeting'],cl) in seen or (row['meeting'],row['id']) in pinned: continue
        seen.add((row['meeting'],cl))
        name=(m.get('identity') or {}).get('name')
        if not name: continue
        auto+=1
        verdict=corrected.get((row['meeting'],row['speaker']))
        if verdict is None: continue
        reviewed+=1
        if verdict!=name: falsified+=1
    return {'names_reviewed':ratio(reviewed,auto),'names_falsified':ratio(falsified,reviewed),'names_unreviewed':ratio(auto-reviewed,auto)}


REPEAT_DAYS=90   # how far back `word_repeat_errors` reads when nobody says


def word_repeat_errors(store, since_days=None, meetings=None, now=None):
    """A word the user taught, and what LATER meetings did with it (Codex #7, the measurement half).

    For every taught word and every meeting recorded after it was taught, one check: did the RAW transcript —
    what the model wrote, before this app rewrote anything — contain the old spelling again? If it did, the
    hint did not work for that word, and the second question is whether the automatic rule caught it: the same
    exact-spelling pattern is run over the text the user actually read.

    * `checks` / `repeats` per word are the (word, meeting) pairs: one meeting counts once however many times
      the word appears in it, so a single unlucky transcript cannot look like ten errors.
    * `fixed` / `unfixed` split the repeats by what the final text says. "3 kez tekrar etti, hepsi düzeltildi"
      is a very different sentence from "3 kez tekrar etti, 2'si düzeltilmedi", and only this tells them apart.
    * Per-word numbers are **local only**: Ayarlar → Sesler ve sözlük shows them, the daily summary carries the
      pooled rate and nothing else, and no word ever leaves this Mac through either.

    Only words taught BEFORE the meeting started are counted — a rule cannot be blamed for a transcript that
    predates it — and only the exact spelling, the same bar `apply_rules` uses before it rewrites anything."""
    from .correction_memory import taught_rules, _pattern, _fold
    try: rules=[r for r in taught_rules(store) if r.get('created')]
    except Exception: rules=[]
    if meetings is None:
        meetings=[m for m in store.meetings() if m['status']=='complete']
        days=REPEAT_DAYS if since_days is None else since_days
        if days:
            horizon=((now or datetime.now(timezone.utc))-timedelta(days=max(1,int(days)))).isoformat()
            meetings=[m for m in meetings if (m['created'] or '')>=horizon]
    meetings=list(meetings)
    if not rules: return {'words':[],'checks':0,'hits':0,'rate':ratio(0,0),'meetings':len(meetings)}
    words={}
    for r in rules:
        words.setdefault(_fold(r['original']),{'original':r['original'],'replacement':r['replacement'],'folded':_fold(r['original']),
                                               'created':r['created'],'checks':0,'repeats':0,'fixed':0,'unfixed':0,'last':None,
                                               '_pattern':_pattern(r['original'])})
    checks=hits=0
    for m in sorted(meetings,key=lambda m:m['created'] or ''):
        # json_extract, not json.loads: this walks every segment of every meeting in the window and the
        # payload carries the word timings too. The four keys are `_raw_text`'s, in `_raw_text`'s order.
        rows=store.db.execute('''SELECT json_extract(payload,'$.pre_auto_text'),json_extract(payload,'$.pre_word_text'),
                                        json_extract(payload,'$.original_text'),json_extract(payload,'$.text')
                                 FROM segments WHERE meeting=?''',(m['id'],)).fetchall()
        if not rows: continue
        raw=[r[0] or r[1] or r[2] or r[3] or '' for r in rows];final=[r[3] or '' for r in rows]
        for w in words.values():
            if w['created']>=(m['created'] or ''): continue   # taught after this meeting: it was never asked to help here
            w['checks']+=1;checks+=1
            seen=[i for i,text in enumerate(raw) if w['_pattern'].search(text)]
            if not seen: continue
            w['repeats']+=1;hits+=1;w['last']=m['created']
            if any(w['_pattern'].search(final[i]) for i in seen): w['unfixed']+=1
            else: w['fixed']+=1
    out=[{k:v for k,v in w.items() if k!='_pattern'} for w in words.values()]
    out.sort(key=lambda w:(-w['repeats'],-w['checks'],w['original']))
    return {'words':out,'checks':checks,'hits':hits,'rate':ratio(hits,checks),'meetings':len(meetings)}


def _word_repeat_metric(store, meetings):
    """The day's pooled repeat rate, from the one function that measures it (`word_repeat_errors`). One
    (word, meeting) pair is one check; the numerator is the pairs where the old spelling was written again."""
    try: return word_repeat_errors(store,meetings=meetings)['rate']
    except Exception: return ratio(0,0)


def _analysis_metrics(store, meeting_ids, day):
    """Summary bullets and tasks the day produced, what the user had to change about them, how long the
    analysis took. `elapsed_seconds` is written by assistant.analyze; analyses from before 1.2.82 have none
    and are simply not in the sample."""
    bullets=tasks=0;seconds=[];analysed=set();window=_bounds(day)
    if _table(store,'analyses'):
        # json_extract rather than json.loads: the payload is the whole analysis and this runs on every heartbeat.
        for r in store.db.execute("SELECT meeting,created,json_array_length(payload,'$.summary') AS bullets,"
                                  "json_extract(payload,'$.elapsed_seconds') AS seconds FROM analyses WHERE created BETWEEN ? AND ?",window):
            if _day_of(r['created'])!=day: continue
            analysed.add(r['meeting']);bullets+=int(r['bullets'] or 0)
            if isinstance(r['seconds'],(int,float)) and not isinstance(r['seconds'],bool): seconds.append(float(r['seconds']))
    if _table(store,'tasks'):
        tasks=sum(1 for r in store.db.execute('SELECT created FROM tasks WHERE created BETWEEN ? AND ?',window) if _day_of(r['created'])==day)
    summary_edits=_summary_edit_count(store,day)
    task_edits=sum(1 for r in store.db.execute('SELECT created FROM task_edits WHERE created BETWEEN ? AND ?',window) if _day_of(r['created'])==day) if _table(store,'task_edits') else 0
    return ({'summary_edits':ratio(summary_edits,bullets) if summary_edits is not None else ratio(0,0),
             'task_edits':ratio(task_edits,tasks),
             'meetings_analysed':ratio(len(analysed&meeting_ids),len(meeting_ids))},
            {'p50':_percentile(seconds,50),'p95':_percentile(seconds,95),'n':len(seconds)})


def _summary_edit_count(store, day):
    """Summary-item corrections, once the release that records them (Codex #2) is on this Mac. Until then
    there is no denominator and no claim: `None` here becomes an empty n/d, not a measured zero."""
    for name in ('summary_edits','insight_edits'):
        if _table(store,name) and 'created' in _columns(store,name):
            return sum(1 for r in store.db.execute(f'SELECT created FROM {name} WHERE created BETWEEN ? AND ?',_bounds(day)) if _day_of(r['created'])==day)
    return None


def _percentile(values, pct):
    if not values: return None
    ordered=sorted(values);k=(len(ordered)-1)*pct/100.0
    low=int(k);high=min(low+1,len(ordered)-1)
    return round(ordered[low]+(ordered[high]-ordered[low])*(k-low),2)


def _review_metrics(store, day):
    """Kontrol items the user closed, by result. `review_results` (Codex #4) is the table that records this
    properly; until it exists the two decisions that ARE recorded stand in — teaching a word (fixed) and
    saying a word is already right (correct) — and “geçildi” has no source, so it stays at zero."""
    correct=fixed=skipped=0;window=_bounds(day)
    if _table(store,'review_results') and {'created','result'}<=_columns(store,'review_results'):
        for r in store.db.execute('SELECT created,result FROM review_results WHERE created BETWEEN ? AND ?',window):
            if _day_of(r['created'])!=day: continue
            result=(r['result'] or '').lower()
            if result in ('correct','dogru','doğru'): correct+=1
            elif result in ('fixed','corrected','duzeltildi','düzeltildi'): fixed+=1
            else: skipped+=1
    else:
        if _table(store,'taught_words'):
            fixed+=sum(1 for r in store.db.execute('SELECT created FROM taught_words WHERE created BETWEEN ? AND ?',window) if _day_of(r['created'])==day)
        if _table(store,'word_dismissals'):
            correct+=sum(1 for r in store.db.execute('SELECT created FROM word_dismissals WHERE created BETWEEN ? AND ?',window) if _day_of(r['created'])==day)
        if _table(store,'rule_feedback'):
            correct+=sum(1 for r in store.db.execute("SELECT created FROM rule_feedback WHERE verdict='accepted' AND created BETWEEN ? AND ?",window) if _day_of(r['created'])==day)
    total=correct+fixed+skipped
    return {'review_correct':ratio(correct,total),'review_fixed':ratio(fixed,total),'review_skipped':ratio(skipped,total)}


def _export_metric(store, day):
    """Successful exports over attempted ones, from the local learning log when this Mac has one. The log is
    another release's table (Codex #1); read defensively by column name so the two merge without a rewrite."""
    name='learning_events'
    columns=_columns(store,name)
    if not columns or 'created' not in columns: return ratio(0,0)
    action=next((c for c in ('action','kind','event') if c in columns),None)
    result=next((c for c in ('result','outcome','state') if c in columns),None)
    if not action or not result: return ratio(0,0)
    attempts=ok=0
    for r in store.db.execute(f'SELECT {action} AS action,{result} AS result,created FROM {name} WHERE created BETWEEN ? AND ?',_bounds(day)):
        if _day_of(r['created'])!=day or not str(r['action'] or '').startswith('export'): continue
        attempts+=1
        if str(r['result'] or '').lower() in ('ok','success','done'): ok+=1
    return ratio(ok,attempts)


def daily_summary(store, data_dir, day=None, *, version=None, device=None, save=True):
    """One day of this Mac, in numbers only (Codex #10). No text, no person, no meeting name ever enters it.

    Every rate carries its own numerator and denominator so a good day with two observations cannot look like
    a trend, and an empty denominator is `null`. The record is keyed by (device, day, app_version) and stored
    under <data_dir>/quality/daily.json; the heartbeat carries the newest of them and a re-uploaded heartbeat
    REPLACES the record with the same key instead of adding to it."""
    from .insights import local_day
    if day is None: day=datetime.now().astimezone().date()
    elif isinstance(day,str): day=date.fromisoformat(day[:10])
    meetings=[m for m in store.meetings() if m['status']=='complete' and local_day(m['created'])==day]
    ids={m['id'] for m in meetings}
    metrics={}
    metrics.update(_names_metrics(store,ids))
    metrics['word_repeat_errors']=_word_repeat_metric(store,meetings)
    analysis,seconds=_analysis_metrics(store,ids,day)
    metrics.update(analysis)
    metrics.update(_review_metrics(store,day))
    metrics['exports_ok']=_export_metric(store,day)
    if device is None: device=_device(data_dir)
    record={'day':day.isoformat(),'device':device or '','app_version':version or '','written':datetime.now(timezone.utc).isoformat(),
            'meetings':len(meetings),'metrics':metrics,'analysis_seconds':seconds}
    if save and data_dir: _save_daily(data_dir,record)
    return record


def _device(data_dir):
    try:
        from . import team_cloud
        return (team_cloud.status(data_dir) or {}).get('device') or ''
    except Exception: return ''


def daily_key(record):
    """(device, day, app_version) — the identity of one measurement. Two heartbeats carrying the same key are
    the same day measured twice, not two days."""
    return f"{record.get('device') or ''}|{record.get('day') or ''}|{record.get('app_version') or ''}"


def _daily_path(data_dir):
    return Path(data_dir)/DAILY_DIR/DAILY_FILE


def load_daily(data_dir):
    try: raw=json.loads(_daily_path(data_dir).read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}
    records=raw.get('records') if isinstance(raw,dict) else None
    return {k:v for k,v in (records or {}).items() if isinstance(v,dict)}


def _save_daily(data_dir, record):
    """Replace this key's record, keep the newest DAILY_KEEP days, write through the same atomic publish the
    reports use so a half-written file can never be read back."""
    from .reports import publish
    records=load_daily(data_dir);records[daily_key(record)]=record
    keep=sorted(records.values(),key=lambda r:(r.get('day') or '',r.get('written') or ''),reverse=True)[:DAILY_KEEP]
    records={daily_key(r):r for r in keep}
    path=_daily_path(data_dir);path.parent.mkdir(parents=True,exist_ok=True)
    try: publish(path,json.dumps({'records':records},ensure_ascii=False,indent=1))
    except OSError: pass   # a measurement is never worth failing a job for
    return records


def daily_for_heartbeat(store, data_dir, *, version=None, days=DAILY_SHARE):
    """Today's numbers plus the recent days already measured, newest first — what the heartbeat carries under
    `quality_daily`. Each entry is a REPLACE-by-key record, so re-uploading a heartbeat cannot double a count."""
    try: daily_summary(store,data_dir,version=version)
    except Exception: pass   # observability never breaks a job
    records=sorted(load_daily(data_dir).values(),key=lambda r:(r.get('day') or '',r.get('written') or ''),reverse=True)
    return records[:days]


# ---------------------------------------------------------------- fleet trend (one alert, never a ranking)

def daily_records(hosts):
    """Every daily record the fleet has, de-duplicated by (device, day, version): the newest upload of a key
    wins. Merging by key is what keeps a host that re-uploaded its heartbeat from counting twice."""
    merged={}
    for host in (hosts or {}).values():
        if not isinstance(host,dict): continue
        beat=host.get('heartbeat') if isinstance(host.get('heartbeat'),dict) else {}
        for record in (beat.get('quality_daily') or host.get('quality_daily') or []):
            if not isinstance(record,dict) or not record.get('day'): continue
            key=daily_key(record);current=merged.get(key)
            if current is None or (record.get('written') or '')>=(current.get('written') or ''): merged[key]=record
    return merged


def _pool(records, metrics=ERROR_METRICS):
    n=d=0;by_metric={}
    for record in records:
        for key in metrics:
            value=(record.get('metrics') or {}).get(key)
            if not isinstance(value,dict): continue
            slot=by_metric.setdefault(key,{'n':0,'d':0})
            slot['n']+=int(value.get('n') or 0);slot['d']+=int(value.get('d') or 0)
            n+=int(value.get('n') or 0);d+=int(value.get('d') or 0)
    return {'n':n,'d':d,'rate':round(n/d,4) if d else None,'days':len(records),
            'by_metric':{k:{**v,'rate':round(v['n']/v['d'],4) if v['d'] else None} for k,v in by_metric.items()}}


def quality_trend(hosts, *, period_days=7, today=None):
    """Two consecutive periods of the fleet's own numbers, and at most ONE alert.

    The alert fires only when the pooled error rate rose by at least 30 % AND both periods carry at least 20
    eligible observations. Fewer than 20 means the rate is noise and the review says explicitly not to raise
    anything; a period with no errors at all gives a rise no percentage can describe, so it is reported as a
    number and not as an alert. Nothing here is per person: the breakdown is by error TYPE."""
    records=daily_records(hosts)
    if not records: return {'current':None,'previous':None,'alerts':[],'period_days':period_days}
    days=sorted({r['day'] for r in records.values()})
    last=days[-1] if today is None else (today.isoformat() if hasattr(today,'isoformat') else str(today)[:10])
    end=date.fromisoformat(last)
    cur_start=end-timedelta(days=period_days-1);prev_start=cur_start-timedelta(days=period_days)
    def window(first,final):
        return [r for r in records.values() if first.isoformat()<=r['day']<=final.isoformat()]
    current=_pool(window(cur_start,end));previous=_pool(window(prev_start,cur_start-timedelta(days=1)))
    out={'period_days':period_days,'from':prev_start.isoformat(),'to':end.isoformat(),
         'current':{**current,'from':cur_start.isoformat(),'to':end.isoformat()},
         'previous':{**previous,'from':prev_start.isoformat(),'to':(cur_start-timedelta(days=1)).isoformat()},
         'eligible':current['d']>=TREND_MIN_OBSERVATIONS and previous['d']>=TREND_MIN_OBSERVATIONS,'alerts':[]}
    out['change']=round(current['rate']/previous['rate']-1,4) if current['rate'] is not None and previous['rate'] else None
    worst=sorted(((k,v) for k,v in current['by_metric'].items() if v['d']),key=lambda kv:-(kv[1]['n']))
    out['top_errors']=[{'metric':k,**v} for k,v in worst[:3]]
    if out['eligible'] and out['change'] is not None and out['change']>=TREND_RISE:
        worst_line=f" · en çok düzeltilen: {LABELS.get(out['top_errors'][0]['metric'],out['top_errors'][0]['metric'])}" if out['top_errors'] else ''
        out['alerts'].append({'host':'', 'level':'warning','key':'quality_trend',
                              'line':f"Ekip kalitesi: hata oranı %{previous['rate']*100:.1f} → %{current['rate']*100:.1f} "
                                     f"(+%{out['change']*100:.0f}, {current['n']}/{current['d']} · önceki {previous['n']}/{previous['d']}){worst_line}"})
    return out


LABELS={'names_falsified':'yanlış otomatik isim','word_repeat_errors':'öğretilen kelime yine yanlış',
        'summary_edits':'özet düzeltmesi','task_edits':'görev düzeltmesi'}


def trend_line(trend):
    """One Turkish line for the setup card: what the two periods measured, or why there is no answer yet."""
    if not trend or not trend.get('current'): return ''
    current,previous=trend['current'],trend['previous']
    if current['rate'] is None: return 'Kalite ölçümü: bu dönemde sayılacak gözlem yok'
    now=f"%{current['rate']*100:.1f} ({current['n']}/{current['d']})"
    if not trend.get('eligible') or previous['rate'] is None:
        return f'Kalite ölçümü: son {trend["period_days"]} günde düzeltme oranı {now} · karşılaştırma için en az {TREND_MIN_OBSERVATIONS} gözlem gerek'
    direction='↑' if (trend.get('change') or 0)>0 else ('↓' if (trend.get('change') or 0)<0 else '→')
    return f'Kalite ölçümü: düzeltme oranı %{previous["rate"]*100:.1f} {direction} {now}'
