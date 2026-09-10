"""Transparent evaluation; rates are fractions, never percentages."""
import re
import unicodedata

def normalize(text):
    text = unicodedata.normalize('NFC', text).translate(str.maketrans({'I':'ı', 'İ':'i'})).lower()
    return ' '.join(re.findall(r'[^\W_]+', text, re.UNICODE))

def edit_distance(a, b):
    prev = list(range(len(b)+1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1): cur.append(min(cur[-1]+1, prev[j]+1, prev[j-1]+(x != y)))
        prev = cur
    return prev[-1]

def text_metrics(reference, hypothesis, entities=(), *, entity_universe=None):
    r, h = normalize(reference), normalize(hypothesis)
    rw, hw = r.split(), h.split()
    present = [normalize(e) for e in entities if normalize(e) and (' '+normalize(e)+' ') in (' '+r+' ')]
    found = sum((' '+e+' ') in (' '+h+' ') for e in present)
    precision = entity_precision_metrics(r, h, entity_universe)
    return {**precision, 'wer': edit_distance(rw, hw)/len(rw) if rw else (None if hw else 0),
            'raw_wer': edit_distance(reference.split(), hypothesis.split())/len(reference.split()) if reference.split() else None,
            'cer': edit_distance(r, h)/len(r) if r else (None if h else 0),
            'reference_words': len(rw), 'word_errors': edit_distance(rw, hw),
            'insertions': len(hw) if not rw else None,
            'entity_recall': found/len(present) if present else None,
            'entity_found': found, 'entity_total': len(present)}

def entity_precision_metrics(reference, hypothesis, universe):
    """Unique normalized phrase types in a predeclared closed universe.

    This is not open-world NER, mention counting or contextual correctness.
    The universe must include possible wrong additions, not only gold entities.
    """
    empty={'entity_precision':None, 'entity_universe_recall':None,
           'entity_true_positive':None, 'entity_false_positive':None,
           'entity_false_negative':None, 'entity_universe_size':None}
    if universe is None:return empty
    if not isinstance(universe,(list,tuple)) or any(not isinstance(e,str) or not normalize(e) for e in universe):
        raise ValueError('entity_universe must contain nonempty phrase strings')
    terms={normalize(e) for e in universe}
    gold={e for e in terms if (' '+e+' ') in (' '+reference+' ')}
    predicted={e for e in terms if (' '+e+' ') in (' '+hypothesis+' ')}
    tp=len(gold & predicted)
    return {'entity_precision':tp/len(predicted) if predicted else None,
            'entity_universe_recall':tp/len(gold) if gold else None,
            'entity_true_positive':tp,'entity_false_positive':len(predicted-gold),
            'entity_false_negative':len(gold-predicted),'entity_universe_size':len(terms)}

def diarization_error(reference, hypothesis):
    """Exact interval DER, optimal global mapping, 0 collar, overlap included."""
    from scipy.optimize import linear_sum_assignment
    import numpy as np
    refs = sorted({s for _,_,s in reference}); hyps = sorted({s for _,_,s in hypothesis})
    points = sorted({t for a,b,_ in reference+hypothesis for t in (a,b)})
    intervals = []
    weights = np.zeros((len(refs), len(hyps)))
    for a,b in zip(points, points[1:]):
        mid = (a+b)/2
        r = {s for x,y,s in reference if x <= mid < y}
        h = {s for x,y,s in hypothesis if x <= mid < y}
        intervals.append((b-a,r,h))
        for rs in r:
            for hs in h: weights[refs.index(rs),hyps.index(hs)] += b-a
    ri, hi = linear_sum_assignment(-weights)
    mapping = {hyps[j]: refs[i] for i,j in zip(ri,hi)}
    total = miss = false = confusion = 0.0
    for dur,r,h in intervals:
        correct = len(r & {mapping.get(s) for s in h})
        total += dur*len(r)
        miss += dur*max(0,len(r)-len(h))
        false += dur*max(0,len(h)-len(r))
        confusion += dur*(min(len(r),len(h))-correct)
    return {'der': (miss+false+confusion)/total if total else (None if false else 0),
            'miss_seconds': miss, 'false_alarm_seconds': false, 'confusion_seconds': confusion,
            'reference_speaker_seconds': total, 'mapping': mapping, 'collar': 0, 'overlap_scored': True}
