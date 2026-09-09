"""Q6/Q7 — correction memory. A word the user has fixed the same way in two different meetings is a
habit of the transcription model, not a slip: from then on it is fixed automatically, marked, and
reversible. Nothing here trains a model; the rules are plain substitutions learned from `text_edits`."""
import difflib
import json
import re
from datetime import datetime, timezone

TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")
MIN_MEETINGS = 2      # seen in two different meetings → a rule
MAX_SPAN = 3          # longer replacements are rewrites, not mishearings
AGREEMENT = 0.75      # the same original fixed two different ways is not a rule


def _fold(s): return s.replace('İ', 'i').replace('I', 'ı').casefold()
def _tokens(text): return TOKEN.findall(text or '')


def substitutions(previous, replacement):
    """Word-level replacements between a segment's text before and after a human edit."""
    a, b = _tokens(previous), _tokens(replacement)
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [_fold(t) for t in a], [_fold(t) for t in b], autojunk=False).get_opcodes():
        if tag == 'replace' and 0 < i2 - i1 <= MAX_SPAN and 0 < j2 - j1 <= MAX_SPAN:
            orig, rep = ' '.join(a[i1:i2]), ' '.join(b[j1:j2])
            if len(orig) >= 3 and _fold(orig) != _fold(rep): out.append((orig, rep))
    return out


def _ensure(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS rule_feedback(original TEXT PRIMARY KEY, verdict TEXT, created TEXT)')


def learned_rules(store, min_meetings=MIN_MEETINGS):
    """Substitutions the user made in at least `min_meetings` meetings, minus the ones they rejected."""
    _ensure(store)
    rejected = {r[0] for r in store.db.execute("SELECT original FROM rule_feedback WHERE verdict='rejected'")}
    seen = {}
    for r in store.db.execute('SELECT meeting,previous,replacement FROM text_edits ORDER BY id'):
        for orig, rep in substitutions(r['previous'], r['replacement']):
            key = _fold(orig)
            if key in rejected: continue
            e = seen.setdefault(key, {'original': orig, 'replacements': {}, 'meetings': set()})
            e['replacements'][rep] = e['replacements'].get(rep, 0) + 1; e['meetings'].add(r['meeting'])
    rules = []
    for e in seen.values():
        rep, count = max(e['replacements'].items(), key=lambda kv: kv[1])
        if len(e['meetings']) >= min_meetings and count >= AGREEMENT * sum(e['replacements'].values()):
            rules.append({'original': e['original'], 'replacement': rep, 'count': count, 'meetings': len(e['meetings'])})
    return sorted(rules, key=lambda x: (-x['meetings'], -x['count'], x['original']))


def reject_rule(store, original):
    """The user reverted an automatic fix: never apply that rule again (until they accept it back)."""
    _ensure(store)
    with store.db: store.db.execute('INSERT OR REPLACE INTO rule_feedback VALUES(?,?,?)', (_fold(original), 'rejected', datetime.now(timezone.utc).isoformat()))


def accept_rule(store, original):
    _ensure(store)
    with store.db: store.db.execute('DELETE FROM rule_feedback WHERE original=?', (_fold(original),))


def _pattern(original):
    return re.compile(r'(?<![^\W\d_])' + r'\s+'.join(re.escape(t) for t in original.split()) + r'(?![^\W\d_])', re.IGNORECASE)


def apply_rules(store, mid, rules=None):
    """Apply learned rules to every segment of a meeting. The original text stays in the payload, the
    segment is flagged `auto_corrected`, and the list of fixes is kept so the UI can undo each one."""
    rules = learned_rules(store) if rules is None else rules
    if not rules: return {'segments': 0, 'fixes': 0, 'rules': 0}
    compiled = [(_pattern(r['original']), r) for r in rules]
    segments = fixes = 0
    for row in store.db.execute('SELECT id,payload FROM segments WHERE meeting=?', (mid,)).fetchall():
        payload = json.loads(row['payload']); text = payload.get('text') or ''
        if 'auto_corrected' in (payload.get('flags') or []): continue   # never stack rules on a previous pass
        applied = []
        for pattern, rule in compiled:
            def swap(m):
                s = m.group(0); rep = rule['replacement']
                return rep[:1].upper() + rep[1:] if s[:1].isupper() and not rep[:1].isupper() else rep
            new, n = pattern.subn(swap, text)
            if n: applied.append({'original': rule['original'], 'replacement': rule['replacement'], 'count': n}); text = new
        if not applied: continue
        payload.setdefault('original_text', payload.get('text')); payload['text'] = text
        payload['flags'] = sorted(set(payload.get('flags') or []) | {'auto_corrected'})
        payload.setdefault('metrics', {})['auto_corrections'] = applied
        with store.db: store.db.execute('UPDATE segments SET payload=? WHERE id=?', (json.dumps(payload, ensure_ascii=False), row['id']))
        segments += 1; fixes += sum(a['count'] for a in applied)
    return {'segments': segments, 'fixes': fixes, 'rules': len(rules)}


def revert(store, mid, segment_id):
    """Undo every automatic fix in one segment and reject the rules behind it."""
    row = store.db.execute('SELECT payload FROM segments WHERE meeting=? AND id=?', (mid, segment_id)).fetchone()
    if not row: raise ValueError('Bölüm bulunamadı')
    payload = json.loads(row['payload']); applied = (payload.get('metrics') or {}).get('auto_corrections') or []
    if not applied: return {'reverted': 0}
    for a in applied: reject_rule(store, a['original'])
    payload['text'] = payload.get('original_text') or payload['text']
    payload['flags'] = [f for f in payload.get('flags') or [] if f != 'auto_corrected']
    payload['metrics'].pop('auto_corrections', None)
    with store.db: store.db.execute('UPDATE segments SET payload=? WHERE id=?', (json.dumps(payload, ensure_ascii=False), segment_id))
    return {'reverted': len(applied), 'rejected': [a['original'] for a in applied]}


def glossary_proposals(rules, entries):
    """Q7: a learned fix whose replacement is a glossary term (or alias) belongs in that term's mishearings."""
    by_name = {}
    for e in entries or []:
        for n in [e.get('term')] + list(e.get('aliases') or []):
            if n: by_name[_fold(n)] = e
    out = []
    for r in rules:
        e = by_name.get(_fold(r['replacement']))
        if e and _fold(r['original']) not in {_fold(m) for m in e.get('mishearings') or []}:
            out.append({'term': e['term'], 'mishearing': r['original'], 'meetings': r['meetings']})
    return out
