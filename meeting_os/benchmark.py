"""Each case/config is a fresh process: isolates model memory and profile state."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from .metrics import text_metrics,diarization_error
from .store import Store

def validate_manifest(manifest):
    if manifest.get('kind') not in ('real','synthetic'): raise ValueError('kind must explicitly be real or synthetic')
    cases=manifest.get('cases',[])
    if not cases: raise ValueError('At least one case is required')
    sessions={c['session'] for c in cases}
    enrollment_sessions={s['session'] for s in manifest.get('enrollment',[])}
    if sessions & enrollment_sessions: raise ValueError('Enrollment/evaluation session leakage')
    for c in cases:
        if not c.get('reference'): raise ValueError('Every case needs a manual reference')
    return manifest

def identity_metrics(reference,segments,known):
    total=accepted=wrong=rejected=unknown_seconds=false_accept=0.0
    for a,b,name in reference:
        for seg in segments:
            duration=max(0,min(b,seg['end'])-max(a,seg['start']))
            if not duration: continue
            predicted=seg.get('speaker_name')
            if name in known:
                total+=duration
                if predicted==name: accepted+=duration
                elif predicted is None: rejected+=duration
                else: wrong+=duration
            else:
                unknown_seconds+=duration
                if predicted is not None: false_accept+=duration
    return {'known_scored_seconds':total,'correct_identification_rate':accepted/total if total else None,
        'false_reject_rate':rejected/total if total else None,'wrong_identity_rate':wrong/total if total else None,
        'unknown_scored_seconds':unknown_seconds,'unknown_false_accept_rate':false_accept/unknown_seconds if unknown_seconds else None,
        'scope':'speech covered by ASR segments; missing speech is evaluated by DER'}

def benchmark(manifest_path,output_dir):
    manifest_path=Path(manifest_path).resolve(); root=manifest_path.parent
    manifest=validate_manifest(json.loads(manifest_path.read_text()))
    output_dir=Path(output_dir).resolve()
    output_dir.mkdir(parents=True,exist_ok=True)
    results=[]
    resource_stopped=False
    for ci,config in enumerate(manifest['configs']):
        for ni,case in enumerate(manifest['cases']):
            if resource_stopped:
                results.append({'config':config['name'],'case':case['id'],'session':case['session'],
                    'kind':manifest['kind'],'tags':case.get('tags',[]),'status':'deferred',
                    'exit_code':None,'reason':'prior_resource_failure'})
                continue
            ident=f'{ci:02}-{ni:02}'
            run_dir=output_dir/ident
            run_dir.mkdir(exist_ok=False) # protect prior results
            db=run_dir/'meeting.sqlite'; result_path=run_dir/'result.json'
            store=Store(db)
            for sample in manifest.get('enrollment',[]):
                store.enroll(sample['name'],sample['vector'],sample['model'],sample['duration'],sample['session'])
            store.close()
            audio=(root/case['audio']).resolve(); reference=json.loads((root/case['reference']).read_text())
            options=config.get('options',[])
            forbidden={'--db','--output'}
            if forbidden.intersection(options): raise ValueError('Benchmark owns output and DB paths')
            cmd=[sys.executable,'-m','meeting_os','--db',str(db),'transcribe',str(audio),'--output',str(result_path),*options]
            begin=time.monotonic()
            with (run_dir/'stdout.log').open('w') as stdout,(run_dir/'stderr.log').open('w') as stderr:
                try:
                    proc=subprocess.run(cmd,cwd=root,stdout=stdout,stderr=stderr,timeout=manifest.get('timeout_seconds',3600))
                    code=proc.returncode
                except subprocess.TimeoutExpired: code=124
            entry={'config':config['name'],'case':case['id'],'session':case['session'],'kind':manifest['kind'],
                   'tags':case.get('tags',[]),'exit_code':code,'status':'ok' if code==0 else 'failed','wall_seconds':time.monotonic()-begin,'command':cmd}
            if code==0:
                result=json.loads(result_path.read_text())
                hyp=' '.join(s['text'] for s in result['segments'])
                entry.update(text_metrics(reference['text'],hyp,reference.get('entities',[])))
                entry['hypothesis']=hyp
                entry['rtf']=entry['wall_seconds']/result['duration'] if result['duration'] else None
                entry['peak_rss_bytes']=result['peak_rss_bytes']
                entry['embedding_model']=result['embedding_model']
                if 'turns' in reference: entry['diarization']=diarization_error([tuple(t) for t in reference['turns']],[tuple(t) for t in result['turns']])
                known={s['name'] for s in manifest.get('enrollment',[]) if s['model']==result['embedding_model']}
                entry['identity']=identity_metrics(reference.get('identity_turns',[]),result['segments'],known) if 'identity_turns' in reference else None
                entry['silence_hallucination_words']=len(hyp.split()) if not reference['text'].strip() else None
            else:
                entry['error_log']=str(run_dir/'stderr.log')
                if code==75:
                    entry['reason']='resource_failure'
                    resource_stopped=True
            results.append(entry)
            (output_dir/'report.json').write_text(json.dumps({'kind':manifest['kind'],'results':results},ensure_ascii=False,indent=2,allow_nan=False))
    (output_dir/'report.json').write_text(json.dumps({'kind':manifest['kind'],'results':results},ensure_ascii=False,indent=2,allow_nan=False))
    lines=[f'# Meeting OS benchmark — {manifest["kind"]}', '', 'Synthetic runs only validate plumbing; they do not establish meeting accuracy.' if manifest['kind']=='synthetic' else 'Real human audio evaluation (see manifest tags: read speech is not a meeting). Rates are fractions.', '', '| Config | Case | WER | Entity recall | RTF incl. startup | Peak RSS GB | Status |','|---|---|---:|---:|---:|---:|---|']
    def number(value): return '—' if value is None else f'{value:.3f}'
    for r in results:
        lines.append(f'| {r["config"]} | {r["case"]} | {number(r.get("wer"))} | {number(r.get("entity_recall"))} | {number(r.get("rtf"))} | {number(r["peak_rss_bytes"]/1e9) if r.get("peak_rss_bytes") is not None else "—"} | {r["status"]} |')
    (output_dir/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return {'report':str(output_dir/'REPORT.md'),'runs':sum(r['status']!='deferred' for r in results),'failed':sum(r['status']=='failed' for r in results),'deferred':sum(r['status']=='deferred' for r in results)}
