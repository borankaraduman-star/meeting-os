"""Share preview: one meeting as Markdown with optional name masking and a decisions-only mode.
Read-only — stored segments, names and analyses are never changed; masking happens in the rendered text only."""
import re
from datetime import datetime, timezone
from .intelligence import REVERSED_NOTE
from .memory import Memory, RETIRED

STATE_LABELS = {'open': 'açık', 'in_progress': 'devam ediyor', 'done': 'tamamlandı', 'dismissed': 'kaldırıldı', 'superseded': 'yenilendi'}
_TURKISH = dict.fromkeys('iİıI', 'iİıI')   # STT output mixes dotted/dotless forms; for redaction, matching all four is the safe side
# First names that are also everyday Turkish words. Case-insensitive masking turned "can sıkıntısı" into
# "Kişi A sıkıntısı"; for these, only a capitalised occurrence is treated as the person.
COMMON_WORDS = {'can', 'su', 'deniz', 'umut', 'barış', 'nur', 'güneş', 'yağmur', 'kaya', 'duru', 'ece', 'ada'}


def placeholder(index):
    """Kişi A … Kişi Z, Kişi AA, Kişi AB … — stable for a given order of names."""
    letters = ''
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return f'Kişi {letters}'


def _char_class(c):
    variants = set(_TURKISH.get(c, '') or (c.lower() + c.upper()))
    variants.add(c)
    return '[' + ''.join(re.escape(v) for v in sorted(variants)) + ']'


def _initial_class(c):
    """The capital forms of one letter only — 'C' and 'İ'/'I', never 'c' or 'i'."""
    variants = set(_TURKISH.get(c, '') or (c.lower() + c.upper()))
    variants.add(c)
    upper = {v for v in variants if v.isupper()} or variants
    return '[' + ''.join(re.escape(v) for v in sorted(upper)) + ']'


def _pattern(name, capitalised=False):
    words = name.split()
    parts = []
    for index, word in enumerate(words):
        head = _initial_class(word[0]) if capitalised and index == 0 else _char_class(word[0])
        parts.append(head + ''.join(_char_class(c) for c in word[1:]))
    return re.compile(r'(?<!\w)' + r'\s+'.join(parts) + r'(?!\w)')


class NameMasker:
    """Replaces every listed name with a stable placeholder. Matching ignores case (Turkish İ/ı aware) and
    stops at word boundaries, so possessive suffixes after an apostrophe survive (“Boran’ın” → “Kişi A’ın”).
    A one-word name that is also an everyday Turkish word (“Can”, “Su”, “Deniz”) is matched only when it is
    capitalised: “can sıkıntısı” is not a person and redacting it made the shared text unreadable."""
    def __init__(self, groups):
        self.mapping = {}; self.rules = []; self.hits = {}
        for index, group in enumerate(groups):
            label = placeholder(index)
            for name in group:
                name = (name or '').strip()
                if len(name) < 2 or name.casefold() in self.mapping: continue
                self.mapping[name.casefold()] = label
                self.rules.append((name, label, _pattern(name, len(name.split()) == 1 and name.casefold() in COMMON_WORDS)))
        self.rules.sort(key=lambda r: -len(r[0]))   # longest first: “Ali Tasarım” before “Ali”
    def mask(self, text):
        if not text or not self.rules: return text
        for name, label, pattern in self.rules:
            text, n = pattern.subn(label, text)
            if n: self.hits[label] = self.hits.get(label, 0) + n
        return text
    @property
    def masked_names(self): return len(self.hits)


def speaker_label(row):
    if row.get('speaker_name'): return row['speaker_name']
    speaker = row.get('speaker') or ''
    flags = row.get('flags') or []
    if 'provisional' in flags: return 'Geçici konuşmacı'
    tail = speaker.split(':')[-1]
    if tail.startswith('S') and tail[1:].isdigit(): return f'Konuşmacı {int(tail[1:]) + 1}'
    if speaker and speaker != 'unknown': return speaker
    return 'İsimsiz konuşmacı'


def clock(seconds):
    if seconds is None: return 'Zaman belirtilmemiş'
    s = int(seconds); return f'{s // 60:02d}:{s % 60:02d}'


def name_groups(rows, glossary, owner=None):
    """People in order of first appearance, then glossary people (term with its aliases).

    `speaker_name` alone is not the list of people: a microphone row keeps its label in the `speaker`
    column (that label is the owner of this Mac), so a mask built from names only published the one name
    the user most wanted hidden — their own. `owner` is the settings name, and it counts as a person of
    THIS meeting only when a microphone row exists in it: the owner of the Mac was not in a meeting they
    never spoke in, and masking their name there redacted an ordinary word ("Can sıkıntısı") for nothing.
    A meeting where they did speak already carries their label, so nothing is lost."""
    from .intelligence import row_person
    rows = list(rows)
    # The owner is always a person to redact; only an everyday-word name (Can, Deniz…) additionally needs proof
    # that they took part, or "Can sıkıntısı" turns into "Kişi A sıkıntısı" for nothing.
    spoke = any((r.get('source') or '') == 'mic' for r in rows) or (owner or '').strip().casefold() not in COMMON_WORDS
    groups = []; seen = set()
    for r in rows + ([{'speaker_name': owner}] if spoke else []):
        name = (row_person(r, owner) or '').strip()
        if name and name.casefold() not in seen: seen.add(name.casefold()); groups.append([name])
    for e in glossary or []:
        if e.get('category') != 'kişi': continue
        names = [e.get('term')] + list(e.get('aliases') or [])
        fresh = [n for n in names if n and n.casefold() not in seen]
        if fresh: seen.update(n.casefold() for n in fresh); groups.append(fresh)
    return groups


def prepare_share(store, mid, *, include_segments=None, exclude_segments=None, mask_names=False, only_decisions=False, kinds=('transcript', 'summary'), glossary=None, owner=None):
    meeting = store.db.execute('SELECT * FROM meetings WHERE id=?', (mid,)).fetchone()
    if not meeting: raise ValueError('Toplantı bulunamadı')
    all_rows = store.display_segments(mid)
    include = {int(i) for i in include_segments} if include_segments else None
    exclude = {int(i) for i in (exclude_segments or [])}
    rows = [r for r in all_rows if (include is None or r['id'] in include) and r['id'] not in exclude]
    memory = Memory(store)
    if owner is None:
        from .reports import store_owner
        owner = store_owner(store)   # the mic label is a person: masking has to cover the user's own name
    latest = memory.latest(mid)
    payload = (latest or {}).get('payload') or {}
    masker = NameMasker(name_groups(all_rows, glossary, owner)) if mask_names else None
    m = (lambda t: masker.mask(t)) if masker else (lambda t: t)
    kinds = tuple(kinds or ())
    with_transcript = 'transcript' in kinds and not only_decisions
    with_summary = 'summary' in kinds and not only_decisions

    def cite(item):
        return [f"  - Kaynak #{e.get('segment_id')} ({clock(e.get('start'))}): “{m(e.get('quote', ''))}”" for e in item.get('evidence', [])]

    lines = [f"# {m(meeting['title'] or 'Adsız toplantı')}", '',
             f"Paylaşım önizlemesi · {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')} · " + ('isimler maskelendi' if mask_names else 'isimler açık'), '',
             'Meeting OS yerel kaydından hazırlandı; paylaşmadan önce gözden geçirin. ' + ('Model çıkarımı kaynak alıntılarıyla birlikte verilmiştir.' if latest else 'Bu toplantı için analiz yok.'), '']
    if latest and latest.get('stale'): lines += ['> Analiz güncel değil; kaynak metin değişti.', '']
    if only_decisions or with_summary:
        lines += ['## Kararlar']
        decisions = payload.get('decisions', [])
        if not decisions: lines.append('- Kayıtlı karar yok.')
        for d in decisions: lines += [f"- {m(d.get('text', ''))}" + (f" ({d.get('note') or REVERSED_NOTE})" if d.get('superseded') else '')] + cite(d)
        lines.append('')
    if with_summary:
        lines += ['## Özet']
        summary = payload.get('summary', [])
        if not summary: lines.append('- Özet yok.')
        for s in summary: lines += [f"- {m(s.get('text', ''))}"] + cite(s)
        lines += ['', '## Görevler']
        tasks = [t for t in memory.actions(meeting=mid) if t.get('state') not in RETIRED]
        if not tasks: lines.append('- Kayıtlı görev yok.')
        for t in tasks:
            lines.append(f"- {m(t['title'])} · {m(t.get('owner') or 'sahibi belirsiz')} · {t.get('due_text') or 'tarih yok'} · {STATE_LABELS.get(t.get('state'), t.get('state'))}" + (' · GÜNCEL DEĞİL' if t.get('stale') else ''))
            lines += cite(t.get('payload') or {})
        lines.append('')
    segments = 0
    if with_transcript:
        lines += ['## Transkript', '']
        if not rows: lines.append('Seçilen bölüm yok.')
        for r in rows:
            segments += 1
            lines += [f"**{clock(r.get('start'))} · {m(speaker_label(r))}**", '', m(r.get('text') or ''), '']
    text = '\n'.join(lines).rstrip('\n') + '\n'
    return {'text': text, 'masked_names': masker.masked_names if masker else 0, 'segments': segments, 'title': meeting['title']}
