"""Human-adjudicated semantic evaluation: no model grades its own output."""
from .metrics import normalize

def score_analysis(analysis,reference):
    payload=analysis.get('payload',analysis);predicted=payload.get('actions',[]);expected=reference['actions'];matches=reference['matches']
    by_id={a['id']:a for a in expected}
    if len(by_id)!=len(expected):raise ValueError('Duplicate reference action id')
    seen_p=set();seen_r=set();owner=due=0
    for match in matches:
        p=match['predicted'];r=match['reference']
        if type(p)!=int or not 0<=p<len(predicted) or r not in by_id or p in seen_p or r in seen_r:raise ValueError('Invalid or duplicated human match')
        seen_p.add(p);seen_r.add(r);actual=predicted[p];gold=by_id[r]
        owner+=normalize(actual.get('owner') or '')==normalize(gold.get('owner') or '')
        due+=normalize(actual.get('due_text') or '')==normalize(gold.get('due_text') or '')
    tp=len(matches);fp=len(predicted)-tp;fn=len(expected)-tp
    unsupported=reference.get('unsupported_summary_indices',[]);summary=payload.get('summary',[])
    if len(set(unsupported))!=len(unsupported) or any(type(i)!=int or not 0<=i<len(summary) for i in unsupported):raise ValueError('Invalid unsupported summary indices')
    return {'true_positive':tp,'false_positive':fp,'false_negative':fn,'action_precision':tp/len(predicted) if predicted else None,'action_recall':tp/len(expected) if expected else None,'action_f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,'owner_accuracy_on_matched':owner/tp if tp else None,'due_text_accuracy_on_matched':due/tp if tp else None,'unsupported_summary_fraction':len(unsupported)/len(summary) if summary else None,'human_adjudicated':True,'notes':'Match semantically equivalent tasks by human review. Null means no denominator; never interpret as 100%.'}
