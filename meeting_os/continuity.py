"""Continuity across meetings: the same commitment or decision seen again is linked, not duplicated.

Deterministic text similarity only (normalized word overlap); no model call. The user accepts a link
explicitly — nothing is merged or closed on its own."""
import difflib
import json
import re
from .memory import Memory, normalize

STOP = {'ve', 'ile', 'için', 'bir', 'bu', 'şu', 'o', 'da', 'de', 'mi', 'mı', 'mu', 'mü', 'the', 'a', 'to', 'of', 'in', 'on', 'yapmak', 'etmek', 'olmak', 'hazırlamak', 'kontrol'}


def _tokens(text):
    return {w for w in re.split(r'\W+', normalize(text or '')) if len(w) > 2 and w not in STOP}


def similarity(a, b):
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    ratio = difflib.SequenceMatcher(None, normalize(a or ''), normalize(b or '')).ratio()
    return round(max(jaccard, ratio), 3)


def related_tasks(store, mid, threshold=0.5):
    memory = Memory(store)
    mine = [t for t in memory.actions(meeting=mid)]
    others = [t for t in memory.actions() if t['meeting'] != mid]
    out = []
    for t in mine:
        hits = []
        for o in others:
            s = similarity(t['title'], o['title'])
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
    out = []
    for d in current:
        hits = [{**p, 'similarity': similarity(d.get('text'), p['text'])} for p in previous]
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
