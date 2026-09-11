"""Cloud analysis benchmark on explicitly fictional transcripts. Never uses private meeting data.

Same fixtures and same lexical gates as scripts/benchmark-analysis.py, but the LLM is the
OpenRouter adapter instead of the local model. Every call costs money, so consent is explicit
(--allow-upload) and a hard call budget (--max-calls) stops a runaway loop.

Beyond check_fixture_analysis this records mechanically detectable quality signals a reviewer
would otherwise have to read for: how many model quotes were verbatim, how many had to be
repaired by locate_quote, how many were unusable, which forbidden terms leaked into any
category, which expected tasks are missing (and why), duplicate items surviving the chunk
merge, and English section names / untranslated labels in Turkish output.

The case list is every fixture in tests/fixtures/analysis (--case narrows it). Three of them exist for
the 2026-09-10 independent review and cost a call each like any other: `negation` and `conditional`
(Codex #10 — a real quote that negates, conditions or delegates the task it is cited for) and
`due_conflict` (Codex #5 — one owner, one wording, two different deadlines, which must stay two tasks).
Adding cases only spends more of the same --max-calls budget; nothing here sends a request without
--allow-upload.
"""
import argparse,json,re,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meeting_os import intelligence
from meeting_os.intelligence import analyze_rows,locate_quote,CATEGORIES
from meeting_os.evaluation import check_fixture_analysis,fixture_rows
from meeting_os.metrics import normalize
from meeting_os.openrouter import OpenRouterClient,validate_analysis_model,ANALYSIS_DEFAULT_MODEL

FIXTURES=Path(__file__).resolve().parents[1]/'tests/fixtures/analysis'
PRICING={   # USD per million tokens, from openrouter.ANALYSIS_MODELS; only for an estimate in the scorecard
 'openai/gpt-4.1-mini':(0.40,1.60),
 'openai/gpt-4o-mini':(0.15,0.60),
 'google/gemini-2.5-flash':(0.30,2.50)}

# Labels a Turkish summary should never contain: English section names and untranslated placeholders.
LABEL=re.compile(r'(?i)(?<![\wğüşıöçĞÜŞİÖÇ])(summary|decisions?|risks?|questions?|action items?|actions?|owner|assignee|due date|deadline|unassigned|not specified|not assigned|no owner|unknown owner|to be determined|tbd|follow[- ]ups?)\s*[::]')
PLACEHOLDER=re.compile(r'(?i)(?<![\wğüşıöçĞÜŞİÖÇ])(unassigned|not specified|not assigned|no owner|unknown owner|to be determined|tbd|n/a)(?![\wğüşıöçĞÜŞİÖÇ])')
# English function words that do not collide with Turkish vocabulary; two or more means an English clause.
ENGLISH=re.compile(r'(?i)(?<![\wğüşıöçĞÜŞİÖÇ])(the|and|will|that|this|they|there|should|would|could|with|from|because|however|therefore|which|been|have|has|was|were|are|about|during|after|before)(?![\wğüşıöçĞÜŞİÖÇ])')
ISO_DATE=re.compile(r'\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b')


def item_text(key,item):return item.get('title') if key=='actions' else item.get('text')


def turkish_issues(result):
    """English section names, untranslated placeholders and English clauses in Turkish output."""
    out=[]
    for key in CATEGORIES:
        for item in result.get(key,[]):
            text=item_text(key,item) or ''
            for name,pattern in (('english_label',LABEL),('untranslated_placeholder',PLACEHOLDER)):
                for m in pattern.finditer(text):out.append({'category':key,'issue':name,'match':m.group(0),'text':text[:160]})
            words=ENGLISH.findall(text)
            if len(words)>=2:out.append({'category':key,'issue':'english_clause','match':' '.join(sorted(set(w.lower() for w in words))),'text':text[:160]})
            if key=='actions':
                for field in ('owner','due_text'):
                    value=item.get(field)
                    if isinstance(value,str) and PLACEHOLDER.search(value):out.append({'category':'actions','issue':'placeholder_'+field,'match':value,'text':text[:160]})
                if isinstance(item.get('due_text'),str) and ISO_DATE.search(item['due_text']):out.append({'category':'actions','issue':'numeric_due_date','match':item['due_text'],'text':text[:160]})
    return out


def duplicates(result,threshold=0.6):
    """Exact normalized repeats (merge_records should leave none) and near-repeats that survive it."""
    exact=[];near=[]
    for key in CATEGORIES:
        texts=[normalize(item_text(key,i) or '') for i in result.get(key,[])]
        for a in range(len(texts)):
            for b in range(a+1,len(texts)):
                if not texts[a] or not texts[b]:continue
                if texts[a]==texts[b]:exact.append({'category':key,'a':a,'b':b,'text':texts[a][:120]});continue
                x,y=set(texts[a].split()),set(texts[b].split())
                ratio=len(x&y)/len(x|y) if x|y else 0.
                if ratio>=threshold:near.append({'category':key,'a':a,'b':b,'jaccard':round(ratio,2),'a_text':texts[a][:120],'b_text':texts[b][:120]})
    return {'exact':exact,'near':near}


def forbidden_leaks(result,terms):
    """A forbidden term under actions is an invented commitment. The same term under summary or
    decisions is usually correct reporting ("migration iptal edildi"), so it is counted apart."""
    out=[];elsewhere=[]
    for key in CATEGORIES:
        for item in result.get(key,[]):
            text=normalize(item_text(key,item) or '')
            for term in terms:
                if normalize(term) in text:
                    (out if key=='actions' else elsewhere).append({'category':key,'term':term,'text':(item_text(key,item) or '')[:160]})
    return out,elsewhere


def missing_decisions(result,case):
    """Optional per-fixture gate: each term group must be covered by one decision item.

    A reversed decision only counts as reported when the same bullet carries both the subject and
    the cancellation, so a stale "we will do X" plus a separate "X is cancelled" does not pass.
    """
    groups=case.get('required_decision_terms') or []
    texts=[normalize(i.get('text') or '') for i in result.get('decisions',[])]
    return [{'terms':g} for g in groups if not any(all(normalize(t) in text for t in g) for text in texts)]


def missing_topics(result,case):
    """Optional per-fixture coverage gate (1.2.82): each term group must be carried by ONE summary bullet.

    A real-size chunk is where the summary quietly collapses to three bullets and loses whole topics — the
    failure the 41-minute meeting showed and the short fixtures never could. `section_summaries` (what each
    chunk said before the merge compacted it) is checked too, so the report can tell "the chunk never saw
    this topic" from "the compaction dropped it"."""
    groups=case.get('expected_topic_terms') or []
    if not groups: return []
    def uncovered(items):
        texts=[normalize(i.get('text') or '') for i in items]
        return [g for g in groups if not any(all(normalize(t) in text for t in g) for text in texts)]
    final=uncovered(result.get('summary',[]))
    sections=uncovered(result.get('section_summaries') or result.get('summary',[]))
    lost={tuple(g) for g in final}-{tuple(g) for g in sections}
    return [{'terms':g,'lost_in_compaction':tuple(g) in lost} for g in final]


def missing_expected(result,case):
    """Which reference tasks are absent, and whether the loss is the task, its owner or its date."""
    actions=result.get('actions',[])
    out=[]
    for gold in case['expected_action_fields']:
        loose=[a for a in actions if all(normalize(t) in normalize(a.get('title','')) for t in gold['title_terms'])]
        if not loose:out.append({**gold,'reason':'task_absent'});continue
        if not any(normalize(a.get('owner') or '')==normalize(gold.get('owner') or '') for a in loose):
            out.append({**gold,'reason':'owner_mismatch','got':[a.get('owner') for a in loose]});continue
        if not any(normalize(a.get('owner') or '')==normalize(gold.get('owner') or '') and normalize(a.get('due_text') or '')==normalize(gold.get('due_text') or '') for a in loose):
            out.append({**gold,'reason':'due_mismatch','got':[a.get('due_text') for a in loose]})
    return out


def evidence_stats(result,rows):
    """Every stored quote must still be a literal substring of its segment; a miss is a harness bug."""
    by_id={r['id']:r['text'] for r in rows};total=bad=0
    for key in CATEGORIES:
        for item in result.get(key,[]):
            for ref in item.get('evidence',[]):
                total+=1
                if ref['quote'] not in by_id.get(ref['segment_id'],''):bad+=1
    return {'stored_quotes':total,'stored_not_verbatim':bad}


class Recorder:
    """Wraps validate_record to see the model's raw claims before verification discards them."""
    def __init__(self):self.reset()
    def reset(self):self.raw_quotes=self.exact=self.repaired=self.unusable=0;self.raw_actions=self.raw_owners=self.raw_dues=0;self.kept_owners=self.kept_dues=0;self.batches=0
    def wrap(self,original):
        def wrapper(record,rows,*args,**kwargs):   # validate_record grew keyword arguments (mic_owner); pass everything through
            self.batches+=1;by_id={r['id']:r['text'] for r in rows}
            for key in CATEGORIES:
                for item in (record.get(key) or []):
                    if not isinstance(item,dict):continue
                    if key=='actions':
                        self.raw_actions+=1
                        self.raw_owners+=isinstance(item.get('owner'),str) and bool(item['owner'].strip())
                        self.raw_dues+=isinstance(item.get('due_text'),str) and bool(item['due_text'].strip())
                    for ref in (item.get('evidence') or []):
                        if not isinstance(ref,dict):continue
                        sid,quote=ref.get('segment_id'),ref.get('quote')
                        self.raw_quotes+=1
                        source=by_id.get(sid) if type(sid)==int else None
                        if source is None or not isinstance(quote,str) or not quote.strip():self.unusable+=1
                        elif quote in source:self.exact+=1
                        elif locate_quote(quote,source) is not None:self.repaired+=1
                        else:self.unusable+=1
            verified=original(record,rows,*args,**kwargs)
            # counted here, not on the final record: de-duplication also removes actions, and that is not an abstention
            self.kept_owners+=sum(1 for a in verified['actions'] if a.get('owner'))
            self.kept_dues+=sum(1 for a in verified['actions'] if a.get('due_text'))
            return verified
        return wrapper
    def report(self,result):
        return {'raw_quotes':self.raw_quotes,'verbatim':self.exact,'repaired':self.repaired,'unusable':self.unusable,
                'verbatim_ratio':round(self.exact/self.raw_quotes,3) if self.raw_quotes else None,
                'verified_ratio':round((self.exact+self.repaired)/self.raw_quotes,3) if self.raw_quotes else None,
                'validate_calls':self.batches,'model_actions':self.raw_actions,
                'model_owners':self.raw_owners,'verified_owners':self.kept_owners,'abstained_owners':self.raw_owners-self.kept_owners,
                'model_dues':self.raw_dues,'verified_dues':self.kept_dues,'abstained_dues':self.raw_dues-self.kept_dues,
                'final_actions':len(result.get('actions',[]))}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--case',action='append',help='fixture stem; repeatable, default all')
    p.add_argument('--model',default=ANALYSIS_DEFAULT_MODEL)
    p.add_argument('--allow-upload',action='store_true',help='explicit consent to send fixture text to OpenRouter')
    p.add_argument('--max-calls',type=int,default=60,help='hard cloud request budget for the whole run')
    p.add_argument('--fixtures',type=Path,default=FIXTURES)
    # One run of one fixture is an anecdote: the 10 Sep table already carried a case that passed in one run
    # and failed in the next. Three repeats is what the review asks of every candidate.
    p.add_argument('--repeat',type=int,default=1,help='run the whole case list N times (the budget still applies)')
    args=p.parse_args(argv)
    if not args.allow_upload:p.error('Bulut analizi için --allow-upload ile açık onay gerekir.')
    paths=[path for path in sorted(args.fixtures.glob('*.json')) if not args.case or path.stem in set(args.case)]
    if not paths:p.error('Eşleşen analiz fixture bulunamadı; hiçbir istek gönderilmedi.')
    model=validate_analysis_model(args.model)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    raw_log=args.output.with_suffix('.raw.txt')
    client=OpenRouterClient();llm=client.analysis(model,consent=True)
    spend={'calls':0,'failed_calls':0,'prompt_tokens':0,'completion_tokens':0}
    post=client._post
    def counted(endpoint,payload,timeout=90):
        if spend['calls']>=args.max_calls:raise SystemExit(f'Çağrı bütçesi doldu ({args.max_calls}); istek gönderilmedi.')
        spend['calls']+=1
        try:
            result=post(endpoint,payload,timeout=timeout)
        except Exception:
            # A request that never came back is the measurement: a model that answers correctly nine times out
            # of ten is not the same product as one that answers ten times, and a retry hides exactly that.
            spend['failed_calls']+=1;raise
        usage=result.get('usage') or {}
        for key,field in (('prompt_tokens','prompt_tokens'),('completion_tokens','completion_tokens')):
            value=usage.get(field)
            if isinstance(value,(int,float)) and not isinstance(value,bool):spend[key]+=value
        return result
    client._post=counted
    complete=llm.complete
    def logged(system,user,**kw):
        raw=complete(system,user,**kw)
        with raw_log.open('a') as f:f.write(raw+'\nEND\n')
        return raw
    llm.complete=logged

    recorder=Recorder();original_validate=intelligence.validate_record
    intelligence.validate_record=recorder.wrap(original_validate)
    results=[]
    try:
      for run in range(1,max(1,args.repeat)+1):
        for path in paths:
            case=json.loads(path.read_text())
            rows=fixture_rows(case)   # a fixture segment marked "source":"mic" becomes an owner row with no speaker_name
            recorder.reset();before=dict(spend);started=time.monotonic()
            asked=llm.model_id;llm.fell_back=False   # per case: which model was ASKED, and which one answered
            try:
                result=analyze_rows(rows,llm,glossary=case.get('glossary'),owner=case.get('owner'))   # a fixture may carry a (possibly poisoned) glossary, like a team folder would
                checks={'valid_evidence_schema':True,**check_fixture_analysis(result,case)}
                leaks,elsewhere=forbidden_leaks(result,case['forbidden_action_terms'])
                item={'case':path.stem,'run':run,'checks':checks,'passed':all(checks.values()),
                      'counts':{key:len(result.get(key,[])) for key in CATEGORIES},
                      'coverage':result.get('coverage'),
                      'evidence':{**recorder.report(result),**evidence_stats(result,rows)},
                      'forbidden_leaks':leaks,'forbidden_mentions_elsewhere':elsewhere,
                      'missing_expected':missing_expected(result,case),
                      'missing_decisions':missing_decisions(result,case),
                      'missing_topics':missing_topics(result,case),
                      'duplicates':duplicates(result),
                      'turkish_issues':turkish_issues(result),
                      'result':result}
            except Exception as exc:
                item={'case':path.stem,'run':run,'passed':False,'error':f'{type(exc).__name__}: {exc}','evidence':recorder.report({})}
            item['elapsed_seconds']=round(time.monotonic()-started,2)
            item['calls']=spend['calls']-before['calls']
            item['failed_calls']=spend['failed_calls']-before['failed_calls']
            # The model that ANSWERED. When the asked model fails after its own retries the client tries
            # ANALYSIS_FALLBACK_MODEL once and keeps it — so a table row saying "deepseek" may be gpt-4.1-mini's
            # score. That is the single most misleading thing a benchmark can hide, so it is a column.
            item['model_asked']=asked;item['model_answered']=llm.model_id;item['fell_back']=bool(llm.fell_back) or llm.model_id!=asked
            item['tokens']={'prompt':spend['prompt_tokens']-before['prompt_tokens'],'completion':spend['completion_tokens']-before['completion_tokens']}
            results.append(item);print(scorecard_line(item),flush=True)
    finally:
        intelligence.validate_record=original_validate
        rate=PRICING.get(model)
        cost=round(spend['prompt_tokens']/1e6*rate[0]+spend['completion_tokens']/1e6*rate[1],5) if rate else None
        timing=seconds_report(results)
        payload={'model':model,'repeat':args.repeat,'cases':results,'timing':timing,
                 'models_that_answered':sorted({r.get('model_answered') or model for r in results}),
                 'fell_back_cases':[r['case'] for r in results if r.get('fell_back')],
                 'spend':{**spend,'estimated_cost_usd':cost},
                 'requires_independent_semantic_review':True,
                 'scope':'Kurgu fixture + sözlüksel kapılar; gerçek toplantı veya bağımsız anlam doğruluğu değildir.'}
        args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2))
        print('\n'+table(results))
        print(f"\ncalls={spend['calls']} failed_calls={spend['failed_calls']} "
              f"seconds p50={timing['p50']} p95={timing['p95']} max={timing['max']} "
              f"prompt_tokens={spend['prompt_tokens']} completion_tokens={spend['completion_tokens']} estimated_cost_usd={cost}")
        answered=payload['models_that_answered']
        if len(answered)>1 or (answered and answered[0]!=model):
            print(f"! yanıtı veren model(ler): {', '.join(answered)} · yedeğe düşen vaka: {', '.join(payload['fell_back_cases']) or '-'}")
    return 0 if results and all(r['passed'] for r in results) else 1


def percentile(values,pct):
    if not values:return None
    ordered=sorted(values);k=(len(ordered)-1)*pct/100.0;low=int(k);high=min(low+1,len(ordered)-1)
    return round(ordered[low]+(ordered[high]-ordered[low])*(k-low),2)


def seconds_report(results):
    """Wall-clock seconds per case (every chunk of it, plus the merge calls). p95 is the number that decides
    whether a model is usable on a two-hour meeting; a mean hides the one case that took four minutes."""
    values=[r['elapsed_seconds'] for r in results if isinstance(r.get('elapsed_seconds'),(int,float))]
    per_case={}
    for r in results:
        if isinstance(r.get('elapsed_seconds'),(int,float)):per_case.setdefault(r['case'],[]).append(r['elapsed_seconds'])
    return {'cases':len(values),'p50':percentile(values,50),'p95':percentile(values,95),'max':max(values) if values else None,
            'mean':round(sum(values)/len(values),2) if values else None,
            'per_case':{case:{'runs':len(v),'p50':percentile(v,50),'p95':percentile(v,95),'max':max(v)} for case,v in per_case.items()}}


def scorecard_line(item):
    tail=f" model={item['model_answered']}" if item.get('fell_back') else ''
    if 'error' in item:return f"{item['case']:<20} run{item.get('run',1)} FAIL  {item['error'][:120]}{tail}"
    e=item['evidence'];checks=item['checks']
    return (f"{item['case']:<20} run{item.get('run',1)} {'PASS' if item['passed'] else 'FAIL'}  "
            f"checks={sum(1 for v in checks.values() if v)}/{len(checks)} "
            f"verbatim={e['verbatim_ratio']} verified={e['verified_ratio']} "
            f"leaks={len(item['forbidden_leaks'])} missing={len(item['missing_expected'])} "
            f"misdec={len(item['missing_decisions'])} topics={len(item.get('missing_topics') or [])} "
            f"dupe={len(item['duplicates']['exact'])}/{len(item['duplicates']['near'])} "
            f"tr={len(item['turkish_issues'])} chunks={(item.get('coverage') or {}).get('chunks')} "
            f"{item['elapsed_seconds']}s{tail}")


COLUMNS=('case','run','checks','verbatim','verified','leaks','missing','misdec','topics','dup','near','tr_issue','chunks','calls','failed','seconds','answered')

def table(results):
    rows=[]
    for item in results:
        common=(str(item.get('calls','-')),str(item.get('failed_calls',0)),str(item.get('elapsed_seconds','-')),
                (item.get('model_answered') or '-') if item.get('fell_back') else '=')
        if 'error' in item:rows.append((item['case'],str(item.get('run',1)),'error')+('-',)*10+common);continue
        e=item['evidence'];checks=item['checks']
        rows.append((item['case'],str(item.get('run',1)),f"{sum(1 for v in checks.values() if v)}/{len(checks)}",
            str(e['verbatim_ratio']),str(e['verified_ratio']),str(len(item['forbidden_leaks'])),
            str(len(item['missing_expected'])),str(len(item['missing_decisions'])),str(len(item.get('missing_topics') or [])),
            str(len(item['duplicates']['exact'])),
            str(len(item['duplicates']['near'])),str(len(item['turkish_issues'])),
            str((item.get('coverage') or {}).get('chunks')))+common)
    widths=[max(len(str(r[i])) for r in ((COLUMNS,)+tuple(rows))) for i in range(len(COLUMNS))]
    line=lambda r:'  '.join(str(v).ljust(w) for v,w in zip(r,widths))
    return '\n'.join([line(COLUMNS),'  '.join('-'*w for w in widths)]+[line(r) for r in rows])


if __name__=='__main__':raise SystemExit(main())
