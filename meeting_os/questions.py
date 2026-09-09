"""Soru radarı: her toplantının en güncel analizindeki açık sorular, tekrar edenler tek grupta.
Read-only — deterministic similarity only, no model call. A question is never closed on its own; a later decision
that looks like an answer is offered as a hint ("muhtemelen cevaplandı"), nothing is marked answered."""
from difflib import SequenceMatcher
from pathlib import Path
from .continuity import prepare, score
from .insights import build_masker, payload_items, prepared_header, source_line
from .memory import Memory, normalize

REPEAT_THRESHOLD = 0.5
ANSWER_THRESHOLD = 0.45
DEFAULT_LIMIT = 100


def question_radar(store, query=None, limit=DEFAULT_LIMIT, threshold=REPEAT_THRESHOLD, answer_threshold=ANSWER_THRESHOLD):
    """Repeated questions, the ones asked in most meetings first. `answered_by` is a hint, never a closure."""
    memory = Memory(store)
    questions = payload_items(store, memory, 'questions')   # newest meeting first
    decisions = payload_items(store, memory, 'decisions')
    pq = [prepare(q['text']) for q in questions]
    pd = [prepare(d['text']) for d in decisions]
    sm = SequenceMatcher(None)
    clusters = []   # question indexes, so the prepared text of each one is reused
    for n in range(len(questions)):
        for c in clusters:
            if max(score(pq[n], pq[k], threshold, sm) for k in c) >= threshold: c.append(n); break
        else: clusters.append([n])
    groups = []
    for c in clusters:
        newest = questions[c[0]]; meetings = []; seen = set()
        for i in (questions[k] for k in c):
            if i['meeting'] in seen: continue
            seen.add(i['meeting']); meetings.append({'meeting': i['meeting'], 'title': i['title'], 'created': i['created']})
        hits = [{'text': d['text'], 'meeting': d['meeting'], 'title': d['title'], 'created': d['created'], 'similarity': score(pq[c[0]], p, answer_threshold, sm)}
                for d, p in zip(decisions, pd) if (d['created'] or '') > (newest['created'] or '')]
        hits = sorted([h for h in hits if h['similarity'] >= answer_threshold], key=lambda h: (h['similarity'], h['created'] or ''), reverse=True)
        groups.append({'text': newest['text'], 'meetings': meetings, 'count': len(meetings), 'created': newest['created'],
                       'evidence': newest['evidence'], 'answered_by': hits[0] if hits else None})
    groups.sort(key=lambda g: (g['count'], g['created'] or ''), reverse=True)   # most meetings first, then newest
    needle = normalize(query or '')
    matched = [g for g in groups if not needle or needle in normalize(g['text']) or any(needle in normalize(x['title'] or '') for x in g['meetings'])]
    return {'groups': matched[:min(max(1, int(limit or DEFAULT_LIMIT)), 1000)], 'total': len(groups), 'matched': len(matched),
            'questions': len(questions), 'query': query or None}


def render_question_radar(radar, mask=None):
    m = mask or (lambda t: t)
    lines = prepared_header('Soru radarı',
                            f"{radar['matched']}/{radar['total']} soru başlığı · {radar['questions']} kayıt" + (f" · filtre: {m(radar['query'])}" if radar.get('query') else ''),
                            'Her toplantının en güncel analizinden alınmıştır; hiçbir soru kendiliğinden kapanmaz, cevap ipuçlarını kaynağıyla doğrulayın.')
    if not radar['groups']: lines.append('- Kayıtlı açık soru yok.')
    for g in radar['groups']:
        lines += ['', f"## {m(g['text'])}", f"- {g['count']} toplantıda soruldu"]
        for x in g['meetings']: lines.append(f"  - {m(x['title'] or 'Adsız toplantı')} · {(x['created'] or '')[:10]}")
        if g['evidence']: lines.append(source_line(g['evidence'], m))
        a = g['answered_by']
        if a: lines.append(f"- Muhtemelen cevaplandı: {m(a['text'])}  ({m(a['title'] or 'Adsız toplantı')} · {(a['created'] or '')[:10]} · benzerlik {a['similarity']})")
    lines.append('')
    return '\n'.join(lines)


def export_question_radar(store, path, query=None, limit=DEFAULT_LIMIT, mask_names=False, glossary=None):
    radar = question_radar(store, query, limit)
    masker = build_masker(store, glossary=glossary) if mask_names else None
    Path(path).write_text(render_question_radar(radar, masker.mask if masker else None), encoding='utf-8')
    return {'path': str(path), 'groups': len(radar['groups']), 'total': radar['total'], 'matched': radar['matched'],
            'answered': sum(1 for g in radar['groups'] if g['answered_by']), 'masked_names': masker.masked_names if masker else 0}
