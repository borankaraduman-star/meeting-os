"""Continuity across meetings: the same commitment or decision seen again is linked, not duplicated.

Deterministic text similarity only (normalized word overlap); no model call. The user accepts a link
explicitly — nothing is merged or closed on its own."""
import difflib
import json
import re
from collections import Counter
from .memory import Memory, normalize

STOP = {'ve', 'ile', 'için', 'bir', 'bu', 'şu', 'o', 'da', 'de', 'mi', 'mı', 'mu', 'mü', 'the', 'a', 'to', 'of', 'in', 'on', 'yapmak', 'etmek', 'olmak', 'hazırlamak', 'kontrol'}
_ROUND = 0.001   # scores are rounded to 3 digits before a caller compares them; keep the floor under that step


def prepare(text):
    """Everything a text contributes to a comparison, worked out once and reused for every pair it takes part in."""
    n = normalize(text or '')
    return n, {w for w in re.split(r'\W+', n) if len(w) > 2 and w not in STOP}, Counter(n)


def _jaccard(ta, tb):
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _reaches(pa, pb, floor):
    """False when no difflib ratio between these two can reach `floor`. Both bounds are difflib's own
    (real_quick_ratio, quick_ratio) and both are symmetric, so one screening settles a pair either way round."""
    la, lb = len(pa[0]), len(pb[0])
    if not (la and lb): return not (la or lb)   # two empty texts match; one empty never does
    bound = max(floor - _ROUND, _jaccard(pa[1], pb[1]))
    if 2 * min(la, lb) / (la + lb) < bound: return False
    ca, cb = (pa[2], pb[2]) if len(pa[2]) <= len(pb[2]) else (pb[2], pa[2])
    return 2 * sum(min(n, cb.get(ch, 0)) for ch, n in ca.items()) / (la + lb) >= bound


def score(pa, pb, floor=0.0, sm=None):
    """Word overlap or difflib ratio, whichever is larger — `similarity` on already prepared texts.
    Exact at or above `floor`; under it the number may be an underestimate, which every caller drops anyway.
    `sm` is one SequenceMatcher reused across a pass so its second sequence stays indexed."""
    jaccard = _jaccard(pa[1], pb[1])
    if not _reaches(pa, pb, floor): return round(jaccard, 3)
    if not pa[0]: return 1.0   # both empty
    sm = sm if sm is not None else difflib.SequenceMatcher(None)
    sm.set_seq2(pb[0]); sm.set_seq1(pa[0])
    return round(max(jaccard, sm.ratio()), 3)


def similarity(a, b, floor=0.0):
    return score(prepare(a), prepare(b), floor)


def similarity_index(texts, floor):
    """{(i, j): score} for every ordered pair reaching `floor`. Screening is symmetric, so each unordered
    pair is looked at once and difflib only runs for the few that get through."""
    prepared = [prepare(t) for t in texts]
    sm = difflib.SequenceMatcher(None)
    out = {}
    for i, pa in enumerate(prepared):
        for j in range(i + 1, len(prepared)):
            pb = prepared[j]
            if not _reaches(pa, pb, floor): continue
            s = score(pa, pb, floor, sm)
            if s >= floor: out[(i, j)] = s
            s = score(pb, pa, floor, sm)
            if s >= floor: out[(j, i)] = s
    return out


def related_tasks(store, mid, threshold=0.5):
    memory = Memory(store)
    mine = [t for t in memory.actions(meeting=mid)]
    others = [t for t in memory.actions() if t['meeting'] != mid]
    prepared = [prepare(o['title']) for o in others]
    sm = difflib.SequenceMatcher(None)
    out = []
    for t in mine:
        pt = prepare(t['title']); hits = []
        for o, po in zip(others, prepared):
            s = score(pt, po, threshold, sm)
            if s >= threshold:
                hits.append({'id': o['id'], 'title': o['title'], 'meeting': o['meeting'], 'meeting_title': o['meeting_title'], 'state': o['state'], 'owner': o['owner'], 'due_text': o['due_text'], 'created': o['created'], 'similarity': s,
                             'superseded_by': (o.get('payload') or {}).get('superseded_by')})
        hits.sort(key=lambda h: (-h['similarity'], h['created']))
        if hits: out.append({'task': t['id'], 'title': t['title'], 'related': hits[:5]})
    return out


def decision_history(store, mid, threshold=0.45):
    memory = Memory(store)
    latest = memory.latest(mid)
    if not latest: return []
    current = latest['payload'].get('decisions', [])
    if not current: return []
    previous = []
    for m in store.meetings():
        if m['id'] == mid: continue
        other = memory.latest(m['id'])
        if not other: continue
        for d in other['payload'].get('decisions', []):
            previous.append({'meeting': m['id'], 'meeting_title': m['title'], 'created': m['created'], 'text': d.get('text'), 'evidence': d.get('evidence', [])[:1]})
    prepared = [prepare(p['text']) for p in previous]
    sm = difflib.SequenceMatcher(None)
    out = []
    for d in current:
        pd = prepare(d.get('text'))
        hits = [{**p, 'similarity': score(pd, pp, threshold, sm)} for p, pp in zip(previous, prepared)]
        hits = sorted([h for h in hits if h['similarity'] >= threshold], key=lambda h: h['created'])
        if hits: out.append({'text': d.get('text'), 'evidence': d.get('evidence', [])[:1], 'previous': hits[:5]})
    return out


def supersede(store, old_id, new_id):
    """The user says: this is the same commitment. The older task is dismissed with a pointer to the new one."""
    memory = Memory(store)
    old = memory.task(old_id); new = memory.task(new_id)
    if old['meeting'] == new['meeting']: raise ValueError('Aynı toplantıdaki görevler birleştirilmez')
    with store.db:
        op = old['payload']; op['superseded_by'] = new_id
        np_ = new['payload']; np_['continues'] = old_id
        store.db.execute('UPDATE tasks SET state=?,payload=?,updated=? WHERE id=?', ('dismissed', json.dumps(op, ensure_ascii=False), __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), old_id))
        store.db.execute('UPDATE tasks SET payload=? WHERE id=?', (json.dumps(np_, ensure_ascii=False), new_id))
    return {'superseded': old_id, 'by': new_id}
