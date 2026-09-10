"""Karar günlüğü: her toplantının en güncel analizindeki kararlar, yenisi üstte, önceki hâlleriyle birlikte.
Read-only — deterministic similarity only, no model call; masking happens in the rendered text only."""
from difflib import SequenceMatcher
from pathlib import Path
from .continuity import prepare, score
from .insights import build_masker, payload_items, prepared_header, source_line
from .memory import Memory, normalize

PREVIOUS_THRESHOLD = 0.45
DEFAULT_LIMIT = 200


def decision_log(store, query=None, limit=DEFAULT_LIMIT, threshold=PREVIOUS_THRESHOLD):
    memory = Memory(store)
    entries = [{**d, 'previous': []} for d in payload_items(store, memory, 'decisions') if not d.get('superseded')]   # a decision the same meeting reversed is not a standing decision
    prepared = [prepare(e['text']) for e in entries]
    sm = SequenceMatcher(None)
    for e, pe in zip(entries, prepared):
        hits = [{'meeting': o['meeting'], 'title': o['title'], 'created': o['created'], 'text': o['text'], 'similarity': score(pe, po, threshold, sm)}
                for o, po in zip(entries, prepared) if o['meeting'] != e['meeting'] and (o['created'] or '') < (e['created'] or '')]
        e['previous'] = sorted([h for h in hits if h['similarity'] >= threshold], key=lambda h: h['created'] or '', reverse=True)[:5]
    needle = normalize(query or '')
    matched = [e for e in entries if not needle or needle in normalize(e['text']) or needle in normalize(e['title'] or '')]
    return {'decisions': matched[:min(max(1, int(limit or DEFAULT_LIMIT)), 1000)], 'total': len(entries), 'matched': len(matched), 'query': query or None}


def render_decision_log(log, mask=None):
    m = mask or (lambda t: t)
    lines = prepared_header('Karar günlüğü', f"{log['matched']}/{log['total']} karar" + (f" · filtre: {m(log['query'])}" if log.get('query') else ''),
                            'Her toplantının en güncel analizinden alınmıştır; paylaşmadan önce kaynağıyla doğrulayın.')
    if not log['decisions']: lines.append('- Kayıtlı karar yok.')
    for d in log['decisions']:
        lines += ['', f"## {m(d['text'])}", f"- {m(d['title'] or 'Adsız toplantı')} · {(d['created'] or '')[:10]}"]
        if d['evidence']: lines.append(source_line(d['evidence'], m))
        for p in d['previous']:
            lines.append(f"  - Önceki hâli: {m(p['text'])}  ({m(p['title'] or 'Adsız toplantı')} · {(p['created'] or '')[:10]} · benzerlik {p['similarity']})")
    lines.append('')
    return '\n'.join(lines)


def export_decision_log(store, path, query=None, limit=DEFAULT_LIMIT, mask_names=False, glossary=None):
    log = decision_log(store, query, limit)
    masker = build_masker(store, glossary=glossary) if mask_names else None
    Path(path).write_text(render_decision_log(log, masker.mask if masker else None), encoding='utf-8')
    return {'path': str(path), 'decisions': len(log['decisions']), 'total': log['total'], 'matched': log['matched'],
            'masked_names': masker.masked_names if masker else 0}
