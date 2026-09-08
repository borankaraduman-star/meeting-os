"""Offline diagnostic of existing paired public FLEURS results; no inference.
Canonical scores stay unchanged. Bootstrap treats the12 utterances as units;
these are first12 cases, not a random meeting population sample.
"""
import hashlib,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from meeting_os.metrics import text_metrics,normalize

def main():
 reports={
  'on':['results-cpp-tr-current','results-cpp-tr-deferred'],
  'off':['results-cpp-tr-no-vocabulary','results-cpp-tr-no-vocabulary-deferred']}
 sources={};selected={}
 for condition,folders in reports.items():
  selected[condition]={}
  for folder in folders:
   p=ROOT/'benchmarks'/folder/'report.json';sources[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
   for row in json.loads(p.read_text())['results']:
    if row.get('exit_code')==0 and 'hypothesis' in row:selected[condition].setdefault(row['case'],row)
 manifest=json.loads((ROOT/'benchmarks/fleurs-tr/cpp-current.manifest.json').read_text());rows=[]
 for case in manifest['cases']:
  p=ROOT/'benchmarks/fleurs-tr'/case['reference'];sources[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest();ref=json.loads(p.read_text())['text']
  row={'case':case['id'],'reference_words':len(normalize(ref).split()),'reference_combining_dot_count':ref.count('\u0307'),'reference_digit_tokens':sum(any(c.isdigit() for c in word) for word in ref.split()),'reference_apostrophes':sum(ref.count(c) for c in "'’")}
  for condition in reports:
   original=selected[condition][case['id']];hyp=original['hypothesis'];metrics=text_metrics(ref,hyp)
   assert metrics['word_errors']==original['word_errors'] and metrics['reference_words']==original['reference_words']
   stripped=lambda text:text.translate(str.maketrans('', '', "'’"))
   sensitivity=text_metrics(stripped(ref),stripped(hyp))
   row[condition]={'word_errors':metrics['word_errors'],'hypothesis_combining_dot_count':hyp.count('\u0307'),'hypothesis_digit_tokens':sum(any(c.isdigit() for c in word) for word in hyp.split()),'hypothesis_apostrophes':sum(hyp.count(c) for c in "'’"),'apostrophe_stripped_errors':sensitivity['word_errors'],'apostrophe_stripped_reference_words':sensitivity['reference_words']}
  row['off_minus_on_errors']=row['off']['word_errors']-row['on']['word_errors'];rows.append(row)
 assert len(rows)==12
 totals={c:sum(r[c]['word_errors'] for r in rows) for c in reports};words=sum(r['reference_words'] for r in rows);assert (words,totals['on'],totals['off'])==(244,14,17)
 rng=np.random.default_rng(20260909);indices=rng.integers(0,len(rows),size=(20000,len(rows)))
 deltas=np.array([r['off_minus_on_errors'] for r in rows]);denoms=np.array([r['reference_words'] for r in rows]);boot=deltas[indices].sum(axis=1)/denoms[indices].sum(axis=1)
 report={'source_sha256':sources,'selection':'first successful stored result per case; no new decoding','canonical_reference_words':words,'canonical_errors':totals,'paired_case_deltas':rows,'bootstrap':{'unit':'utterance','draws':20000,'seed':20260909,'estimate_off_minus_on_wer':(totals['off']-totals['on'])/words,'percentile95':np.quantile(boot,[.025,.975]).tolist(),'limitation':'Descriptive resampling of first12 inspected read-speech cases; not a generalization interval for meetings or independent confirmation.'},'normalization':'Canonical unchanged; apostrophe removal is sensitivity diagnostic only. No number normalization or foreign-letter code-switch labels.','scope':'No model promotion, held-out meeting precision, determinism or resource availability acceptance.'}
 out=ROOT/'benchmarks/results/fleurs-paired-audit-2026-09-09.json';out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'words':words,'errors':totals,'bootstrap':report['bootstrap'],'changed_cases':[r['case'] for r in rows if r['off_minus_on_errors']],'combining_dot_total':sum(r['reference_combining_dot_count']+r['on']['hypothesis_combining_dot_count']+r['off']['hypothesis_combining_dot_count'] for r in rows),'apostrophe_sensitivity':{c:{'errors':sum(r[c]['apostrophe_stripped_errors'] for r in rows),'words':sum(r[c]['apostrophe_stripped_reference_words'] for r in rows)} for c in reports}},indent=2))
if __name__=='__main__':main()
