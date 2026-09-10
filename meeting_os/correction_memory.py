"""Q6/Q7 — correction memory. A word the user has fixed the same way in two different meetings is a
habit of the transcription model, not a slip: from then on it is fixed automatically, marked, and
reversible. Nothing here trains a model; the rules are plain substitutions learned from `text_edits`.

"Teach a word once" sits on the same machinery. `teach` turns a single correction into a rule at once —
the user said so, waiting for a second meeting would be pedantry — and a taught rule matches near-misses
as well as the exact spelling, because a model that wrote "Trendyoll" once will write "Trendiyol" next
time. Everything a taught rule touches keeps the sentence it replaced (`pre_word_text`) and is listed in
`metrics.word_corrections`, so `forget_word` can put every one of them back.
"""
import difflib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")
MIN_MEETINGS = 2      # seen in two different meetings → a rule
MAX_SPAN = 3          # longer replacements are rewrites, not mishearings
AGREEMENT = 0.75      # the same original fixed two different ways is not a rule


def _fold(s): return s.replace('İ', 'i').replace('I', 'ı').casefold()
def _tokens(text): return TOKEN.findall(text or '')


def _upper_first(word):
    """Turkish capitalization: 'i'→'İ' and 'ı'→'I'. str.upper() turns 'istanbul' into 'Istanbul', which is
    a different word here and the kind of wrongness a user notices in every automatic fix."""
    if not word: return word
    first = 'İ' if word[0] == 'i' else ('I' if word[0] == 'ı' else word[0].upper())
    return first + word[1:]


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


ROOT = Path(__file__).resolve().parents[1]
MIN_FUZZY = 4         # shorter than this, a one-letter distance is a different word, not a misspelling
LONG_TOKEN = 8        # from here on a second error in the same word is still the same word
STEM = re.compile(r"^([^\W\d_]+)(['’][^\W\d_]+)?$")

# Turkish endings a correct word grows. "Trendyol" + "a" is an inflection, not a misspelling, so a taught
# rule must leave it alone; "Trendyol" + "l" is not an ending, so "Trendyoll" is fair game.
SUFFIXES = frozenset("""a e ı i u ü ya ye da de ta te dan den tan ten la le ile yla yle lar ler ın in un ün nın nin nun nün
sı si su sü ları leri yı yi yu yü nı ni nu nü ca ce ça çe daki deki taki teki lı li lu lü sız siz suz süz cı ci cu cü çı çi çu çü
m n mız miz muz müz nız niz nuz nüz dı di tı ti ydı ydi mış miş ymış ymiş sa se ysa yse ken yken ıp ip up üp arak erek
nda nde nta nte ndan nden sını sini sinin nın nin""".split())


def common_words():
    """The ordinary Turkish words a fuzzy rule must never rewrite. Reuses the three stoplists this codebase
    already keeps rather than inventing a fourth."""
    global _COMMON
    if _COMMON is None:
        from .memory import STOPWORDS as A
        from .intelligence import STOPWORDS as B
        from .continuity import STOP as C
        _COMMON = {_fold(w) for w in set(A) | set(B) | set(C) | {
            'evet', 'hayır', 'tamam', 'lütfen', 'sonra', 'önce', 'şimdi', 'bugün', 'yarın', 'dün', 'hafta', 'ay', 'yıl',
            'toplantı', 'konu', 'sorun', 'çözüm', 'zaten', 'belki', 'sadece', 'yalnız', 'bence', 'tabii', 'aslında',
            'birlikte', 'başka', 'kadar', 'sanırım', 'olarak', 'diğer', 'yeni', 'eski', 'büyük', 'küçük', 'iyi', 'kötü'}}
    return _COMMON


_COMMON = None


def _distance(a, b, limit):
    """Damerau-Levenshtein (optimal string alignment) with an early exit at `limit`."""
    la, lb = len(a), len(b)
    if abs(la - lb) > limit: return limit + 1
    previous2 = None
    previous = list(range(lb + 1))
    for i in range(1, la + 1):
        current = [i] + [0] * lb
        best = i
        ai = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ai == b[j - 1] else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            if previous2 is not None and j > 1 and ai == b[j - 2] and a[i - 2] == b[j - 1]:
                value = min(value, previous2[j - 2] + cost)
            current[j] = value
            if value < best: best = value
        if best > limit: return limit + 1
        previous2, previous = previous, current
    return previous[lb]


def near_miss(token, target, allow_suffix=False):
    """Is `token` (folded, already a stem) a misspelling of `target` (folded)? Cheap tests first: the length
    has to be within ±2 and the first or the last letter has to survive — a mis-transcription rarely loses both."""
    if len(token) < MIN_FUZZY or len(target) < MIN_FUZZY: return False
    if abs(len(token) - len(target)) > 2: return False
    if token[0] != target[0] and token[-1] != target[-1]: return False
    if not allow_suffix and len(token) > len(target) and token.startswith(target) and token[len(target):] in SUFFIXES:
        return False   # an inflected correct word, not a misspelling
    limit = 1 if len(token) < LONG_TOKEN else 2
    distance = _distance(token, target, limit)
    return 0 < distance <= limit


def _split(token):
    m = STEM.match(token)
    return (m.group(1), m.group(2) or '') if m else (token, '')


def vocabulary_terms(data_dir):
    """The terms in the ASR hint list (`vocabulary.txt`), or none when there is no data folder to read."""
    if not data_dir: return []
    from .glossary import vocabulary_path, _clean
    path = vocabulary_path(data_dir)
    if not path.is_file(): return []
    out = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        term = _clean(line.split('#')[0])
        if term: out.append(term)
    return out


def _protected(rules, data_dir, allow=()):
    """Tokens a fuzzy rule may never rewrite: what the rules produce, and the words the user already told the
    system are spelled right. `allow` lets `teach` correct a word that happens to sit in the vocabulary itself."""
    keep = {_fold(a) for a in allow}
    out = {_fold(r['replacement']) for r in rules} | {_fold(t) for t in vocabulary_terms(data_dir)}
    return out - keep


def _targets(rules):
    """Folded (original, replacement) for every taught single-word rule; multi-word rules stay exact."""
    out = []
    for r in rules:
        if not r.get('fuzzy') or ' ' in r['original'].strip(): continue
        out.append({'rule': r, 'original': _fold(r['original']), 'replacement': _fold(r['replacement'])})
    return out


def _inflected(folded, target):
    """`folded` is `target` plus a Turkish ending — a correct word doing its job, not a misspelling."""
    return len(folded) > len(target) and folded.startswith(target) and folded[len(target):] in SUFFIXES


def _pick(folded, targets, protected, has_suffix):
    """The taught rule that best explains a folded token, or None."""
    if len(folded) < MIN_FUZZY or folded in protected: return None
    for t in targets:
        if folded == t['original'] and folded != t['replacement']: return t['rule']   # the exact taught spelling always wins
    if folded in common_words(): return None
    best = None
    for t in targets:
        # "Trendyola" is one letter from "Trendyoll" and would be rewritten on distance alone. An ending on
        # either spelling of the rule means the word is inflected, and this rule has nothing to say about it.
        if not has_suffix and (_inflected(folded, t['original']) or _inflected(folded, t['replacement'])): continue
        for target in (t['original'], t['replacement']):
            if not near_miss(folded, target, allow_suffix=True): continue
            limit = 1 if len(folded) < LONG_TOKEN else 2
            distance = _distance(folded, target, limit)
            if best is None or distance < best[0]: best = (distance, t['rule'])
    return best[1] if best else None


def apply_taught(text, targets, protected):
    """Rewrite every token of `text` that a taught rule explains. A Turkish apostrophe suffix is left where it
    was — "Trendyoll'a" becomes "Trendyol'a", never "Trendyol"."""
    hits = {}
    if not targets: return text, hits
    def swap(m):
        token = m.group(0)
        stem, suffix = _split(token)
        rule = _pick(_fold(stem), targets, protected, bool(suffix))
        if rule is None: return token
        replacement = rule['replacement']
        if stem[:1].isupper() and not replacement[:1].isupper(): replacement = _upper_first(replacement)
        hits[rule['original']] = hits.get(rule['original'], 0) + 1
        return replacement + suffix
    return TOKEN.sub(swap, text), hits


def _ensure_taught(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS taught_words(original TEXT PRIMARY KEY, display TEXT, replacement TEXT,'
                     ' count INTEGER, meetings TEXT, created TEXT, vocabulary_added INTEGER)')


def taught_rules(store):
    """Words the user taught by hand. One correction is enough; a rejected one stays off until it is accepted back."""
    _ensure(store); _ensure_taught(store)
    rejected = {r[0] for r in store.db.execute("SELECT original FROM rule_feedback WHERE verdict='rejected'")}
    out = []
    for r in store.db.execute('SELECT * FROM taught_words ORDER BY created,original'):
        if r['original'] in rejected: continue
        try: meetings = json.loads(r['meetings'] or '[]')
        except ValueError: meetings = []
        out.append({'original': r['display'] or r['original'], 'replacement': r['replacement'], 'count': r['count'] or 1,
                    'meetings': len(meetings), 'created': r['created'], 'source': 'taught', 'fuzzy': True,
                    'vocabulary_added': bool(r['vocabulary_added'])})
    return out


def all_rules(store):
    """Taught rules first; a learned rule for a word the user has already taught is redundant and dropped."""
    taught = taught_rules(store)
    keys = {_fold(r['original']) for r in taught}
    learned = [{**r, 'source': 'learned', 'fuzzy': False} for r in learned_rules(store) if _fold(r['original']) not in keys]
    return taught + learned


def _pattern(original):
    return re.compile(r'(?<![^\W\d_])' + r'\s+'.join(re.escape(t) for t in original.split()) + r'(?![^\W\d_])', re.IGNORECASE)


def apply_rules(store, mid, rules=None, data_dir=None):
    """Apply learned and taught rules to every segment of a meeting. What the segment said before this pass is
    kept in `pre_auto_text` — its own key, never the user's `original_text`, so reverting an automatic fix
    cannot throw away a manual edit — the segment is flagged `auto_corrected`, and every fix is listed for undo.
    Taught single-word rules also catch near-misses (see `apply_taught`); `data_dir` is only needed for the
    vocabulary list those fuzzy matches must never rewrite."""
    rules = all_rules(store) if rules is None else rules
    if not rules: return {'segments': 0, 'fixes': 0, 'rules': 0}
    fuzzy = _targets(rules)
    compiled = [(_pattern(r['original']), r) for r in rules if not any(t['rule'] is r for t in fuzzy)]
    protected = _protected(rules, data_dir) if fuzzy else set()
    segments = fixes = 0
    for row in store.db.execute('SELECT id,payload FROM segments WHERE meeting=?', (mid,)).fetchall():
        payload = json.loads(row['payload']); text = payload.get('text') or ''
        if 'auto_corrected' in (payload.get('flags') or []): continue   # never stack rules on a previous pass
        applied = []
        for pattern, rule in compiled:
            def swap(m):
                s = m.group(0); rep = rule['replacement']
                return _upper_first(rep) if s[:1].isupper() and not rep[:1].isupper() else rep
            new, n = pattern.subn(swap, text)
            if n: applied.append({'original': rule['original'], 'replacement': rule['replacement'], 'count': n}); text = new
        if fuzzy:
            text, hits = apply_taught(text, fuzzy, protected)
            by_original = {t['rule']['original']: t['rule'] for t in fuzzy}
            for original, n in hits.items():
                applied.append({'original': original, 'replacement': by_original[original]['replacement'], 'count': n})
        if not applied: continue
        payload['pre_auto_text'] = payload.get('text'); payload['text'] = text
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
    # pre_auto_text is what this segment said before the automatic pass — the user's manual edit, when there
    # was one. original_text is the fallback for segments corrected by a version that shared the two keys.
    payload['text'] = payload.pop('pre_auto_text', None) or payload.get('original_text') or payload['text']
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


def _vocabulary_add(data_dir, term):
    """Append a taught spelling to `vocabulary.txt` — the list the cloud model gets as a spelling hint, so the
    next meeting has a chance of writing it right in the first place. Returns whether it was actually added."""
    if not data_dir: return False
    from .glossary import vocabulary_path
    path = vocabulary_path(data_dir, ROOT)   # copies the shipped seed first: teaching a word must not eat the starter list
    try: path.relative_to(Path(data_dir))
    except ValueError: return False          # unwritable data folder; vocabulary_path fell back to the repo seed, never write there
    if _fold(term) in {_fold(t) for t in vocabulary_terms(data_dir)}: return False
    text = path.read_text(encoding='utf-8', errors='replace') if path.is_file() else ''
    if text and not text.endswith('\n'): text += '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + term + '\n', encoding='utf-8')
    return True


def _vocabulary_remove(data_dir, term):
    """Take one line back out of `vocabulary.txt`. Only ever called for a term `teach` itself put there."""
    if not data_dir: return False
    from .glossary import vocabulary_path, _clean
    path = vocabulary_path(data_dir)
    if not path.is_file(): return False
    try: path.relative_to(Path(data_dir))
    except ValueError: return False
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    kept = [l for l in lines if _fold(_clean(l.split('#')[0]) or '') != _fold(term)]
    if len(kept) == len(lines): return False
    path.write_text(('\n'.join(kept) + '\n') if kept else '', encoding='utf-8')
    return True


def _apply_now(store, mid, rule, protected):
    """Fix every occurrence of a just-taught word in the meeting the user is looking at. The sentence each
    segment had is kept twice: in `original_text` (what the Düzelt box shows as the untouched transcript, when
    nothing was there yet) and in `pre_word_text`, which is what `forget_word` puts back — a manual edit made
    before the word was taught must survive being forgotten."""
    single = ' ' not in rule['original'].strip()
    targets = _targets([rule]) if single else []
    pattern = None if single else _pattern(rule['original'])
    segments = fixes = 0
    for row in store.db.execute('SELECT id,payload FROM segments WHERE meeting=?', (mid,)).fetchall():
        payload = json.loads(row['payload']); text = payload.get('text') or ''
        if single:
            new, hits = apply_taught(text, targets, protected); count = sum(hits.values())
        else:
            def swap(m):
                s = m.group(0); rep = rule['replacement']
                return _upper_first(rep) if s[:1].isupper() and not rep[:1].isupper() else rep
            new, count = pattern.subn(swap, text)
        if not count or new == text: continue
        metrics = payload.setdefault('metrics', {})
        if 'original_text' not in payload:
            payload['original_text'] = text; metrics['word_original_set'] = True
        payload.setdefault('pre_word_text', text)
        payload['text'] = new
        payload['flags'] = sorted(set(payload.get('flags') or []) | {'word_corrected'})
        entries = list(metrics.get('word_corrections') or [])
        entries.append({'rule': _fold(rule['original']), 'original': rule['original'], 'replacement': rule['replacement'], 'count': count})
        metrics['word_corrections'] = entries
        with store.db: store.db.execute('UPDATE segments SET payload=? WHERE id=?', (json.dumps(payload, ensure_ascii=False), row['id']))
        segments += 1; fixes += count
    return {'segments': segments, 'fixes': fixes}


def teach(store, mid, original, replacement, data_dir=None):
    """One correction is a rule. Speaker naming works this way — you say who it is once — and a misheard word
    deserves the same: the rule is stored immediately, every occurrence in this meeting is fixed now, and the
    right spelling joins the vocabulary hint list so the next meeting has a better chance of not needing it.
    The meeting's analysis goes stale by itself when the text changes; the fingerprint covers the transcript."""
    original = (original or '').strip(); replacement = (replacement or '').strip()
    if not original or not replacement: raise ValueError('Düzeltilecek kelime ve doğru yazımı gerekli')
    if _fold(original) == _fold(replacement): raise ValueError('Kelime zaten bu şekilde yazılıyor')
    if len(original.split()) > MAX_SPAN or len(replacement.split()) > MAX_SPAN: raise ValueError(f'En çok {MAX_SPAN} kelime öğretilebilir')
    if len(original) > 120 or len(replacement) > 120: raise ValueError('Kelime düzeltmesi için fazla uzun')
    _ensure(store); _ensure_taught(store)
    accept_rule(store, original)   # teaching a word overrules an earlier rejection of the same word
    key = _fold(original)
    row = store.db.execute('SELECT * FROM taught_words WHERE original=?', (key,)).fetchone()
    try: meetings = json.loads(row['meetings']) if row and row['meetings'] else []
    except ValueError: meetings = []
    if mid and mid not in meetings: meetings.append(mid)
    count = (row['count'] or 0 if row else 0) + 1
    created = (row['created'] if row else None) or datetime.now(timezone.utc).isoformat()
    added = _vocabulary_add(data_dir, replacement)
    vocabulary_added = bool(row['vocabulary_added']) if row else False
    with store.db:
        store.db.execute('INSERT OR REPLACE INTO taught_words VALUES(?,?,?,?,?,?,?)',
                         (key, original, replacement, count, json.dumps(meetings), created, int(vocabulary_added or added)))
    rule = {'original': original, 'replacement': replacement, 'count': count, 'meetings': len(meetings), 'created': created,
            'source': 'taught', 'fuzzy': True, 'vocabulary_added': bool(vocabulary_added or added)}
    protected = _protected(all_rules(store), data_dir, allow=[original])
    result = _apply_now(store, mid, rule, protected) if mid else {'segments': 0, 'fixes': 0}
    return {'rule': rule, 'segments': result['segments'], 'fixes': result['fixes'], 'vocabulary_added': added}


def unteach(store, original, data_dir=None):
    """Forget a taught word: the rule goes, and the vocabulary line goes only if teaching it is what put it there."""
    _ensure_taught(store)
    key = _fold(original)
    row = store.db.execute('SELECT * FROM taught_words WHERE original=?', (key,)).fetchone()
    if not row: return {'forgotten': False, 'vocabulary_removed': False}
    removed = bool(row['vocabulary_added']) and _vocabulary_remove(data_dir, row['replacement'])
    with store.db: store.db.execute('DELETE FROM taught_words WHERE original=?', (key,))
    return {'forgotten': True, 'replacement': row['replacement'], 'vocabulary_removed': bool(removed)}


def untaught_revert(store, mid, original):
    """Put back the sentences one taught word rewrote. A segment that a second taught word also touched is left
    alone — undoing half of two overlapping rewrites would produce a sentence nobody ever wrote."""
    key = _fold(original)
    reverted = skipped = 0
    for row in store.db.execute('SELECT id,payload FROM segments WHERE meeting=?', (mid,)).fetchall():
        payload = json.loads(row['payload']); metrics = payload.get('metrics') or {}
        entries = metrics.get('word_corrections') or []
        if not entries: continue
        if any(e.get('rule') != key for e in entries): skipped += 1; continue
        previous = payload.pop('pre_word_text', None) or payload.get('original_text')
        if previous: payload['text'] = previous
        if metrics.pop('word_original_set', None): payload.pop('original_text', None)
        metrics.pop('word_corrections', None)
        payload['flags'] = [f for f in payload.get('flags') or [] if f != 'word_corrected']
        with store.db: store.db.execute('UPDATE segments SET payload=? WHERE id=?', (json.dumps(payload, ensure_ascii=False), row['id']))
        reverted += 1
    return {'reverted': reverted, 'skipped': skipped}


def forget(store, original, data_dir=None):
    """`unteach` plus the undo: every meeting this word rewrote gets its sentences back."""
    result = unteach(store, original, data_dir)
    key = _fold(original)
    meetings = set()
    for row in store.db.execute("SELECT meeting,payload FROM segments WHERE payload LIKE '%word_corrected%'").fetchall():
        try: entries = (json.loads(row['payload']).get('metrics') or {}).get('word_corrections') or []
        except ValueError: continue
        if any(e.get('rule') == key for e in entries): meetings.add(row['meeting'])
    reverted = skipped = 0
    for mid in sorted(meetings):
        r = untaught_revert(store, mid, original)
        reverted += r['reverted']; skipped += r['skipped']
    return {**result, 'meetings': len(meetings), 'segments': reverted, 'kept': skipped}


def word_rules(store):
    """Every word rule behind the automatic fixes, taught ones first — what Ayarlar → Sesler ve sözlük lists."""
    out = []
    for r in all_rules(store):
        out.append({'original': r['original'], 'replacement': r['replacement'], 'source': r.get('source', 'learned'),
                    'count': r.get('count', 1), 'meetings': r.get('meetings', 0), 'created': r.get('created'),
                    'vocabulary_added': bool(r.get('vocabulary_added'))})
    return out


def dismissed_words(store, mid):
    meta = json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?', (mid,)).fetchone()[0] or '{}')
    return meta, [w for w in (meta.get('word_dismissed') or []) if isinstance(w, str)]


def dismiss_word(store, mid, original):
    """"That is the word I meant": this spelling stops being flagged in this meeting."""
    original = (original or '').strip()
    if not original: raise ValueError('Kelime gerekli')
    meta, current = dismissed_words(store, mid)
    if _fold(original) not in {_fold(w) for w in current}: current = current + [original]
    meta['word_dismissed'] = current[:200]
    with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?', (json.dumps(meta, ensure_ascii=False), mid))
    return {'dismissed': True, 'words': len(meta['word_dismissed'])}


REVIEW_LIMIT = 40


def word_candidates(store, mid, data_dir=None, limit=REVIEW_LIMIT):
    """Words in this meeting that are one slip away from a word the user taught or wrote in the vocabulary, and
    are not that word. This is what Kontrol was blind to: a wrong word the model was confident about looks
    exactly like a right one until you compare it with the list of words this team actually uses."""
    targets = []
    seen = set()
    for r in taught_rules(store):
        folded = _fold(r['replacement'])
        if len(folded) >= MIN_FUZZY and folded not in seen: seen.add(folded); targets.append((folded, r['replacement'], 'taught'))
    for term in vocabulary_terms(data_dir):
        folded = _fold(term)
        if ' ' in folded or len(folded) < MIN_FUZZY or folded in seen: continue
        seen.add(folded); targets.append((folded, term, 'vocabulary'))
    if not targets: return []
    _, dismissed = dismissed_words(store, mid)
    skip = seen | {_fold(w) for w in dismissed} | common_words()
    found = {}
    for row in store.segments(mid):
        for token in _tokens(row.get('text') or ''):
            stem, suffix = _split(token)
            folded = _fold(stem)
            if len(folded) < MIN_FUZZY or folded in skip: continue
            hit = found.get(folded)
            if hit: hit['count'] += 1; continue
            for target, display, source in targets:
                if not near_miss(folded, target, allow_suffix=bool(suffix)): continue
                found[folded] = {'original': stem, 'replacement': display, 'segment_id': row['id'], 'count': 1, 'source': source}
                break
            else:
                skip.add(folded)   # nothing matched this token; never fold it again in this meeting
    return sorted(found.values(), key=lambda f: (f['segment_id'], f['original']))[:limit]
