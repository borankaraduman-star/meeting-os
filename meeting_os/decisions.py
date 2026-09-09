"""Karar günlüğü: her toplantının en güncel analizindeki kararlar, yenisi üstte, önceki hâlleriyle birlikte.
Read-only — deterministic similarity only, no model call; masking happens in the rendered text only."""
from datetime import datetime, timezone
from pathlib import Path
from .continuity import similarity
from .memory import Memory, normalize

PREVIOUS_THRESHOLD = 0.45
DEFAULT_LIMIT = 200


def decision_log(store, query=None, limit=DEFAULT_LIMIT, threshold=PREVIOUS_THRESHOLD):
    memory = Memory(store)
    entries = []
    for m in sorted(store.meetings(), key=lambda m: m['created'] or '', reverse=True):
        latest = memory.latest(m['id'])
        if not latest: continue
        for d in (latest.get('payload') or {}).get('decisions', []):
            evidence = [e for e in (d.get('evidence') or []) if isinstance(e, dict)]
            first = evidence[0] if evidence else None
            entries.append({'meeting': m['id'], 'title': m['title'], 'created': m['created'], 'text': d.get('text') or '',
                            'evidence': {'segment_id': first.get('segment_id'), 'start': first.get('start'), 'quote': first.get('quote')} if first else None,
                            'previous': []})
    for e in entries:
        hits = [{'meeting': o['meeting'], 'title': o['title'], 'created': o['created'], 'text': o['text'], 'similarity': similarity(e['text'], o['text'])}
                for o in entries if o['meeting'] != e['meeting'] and (o['created'] or '') < (e['created'] or '')]
        e['previous'] = sorted([h for h in hits if h['similarity'] >= threshold], key=lambda h: h['created'] or '', reverse=True)[:5]
    needle = normalize(query or '')
    matched = [e for e in entries if not needle or needle in normalize(e['text']) or needle in normalize(e['title'] or '')]
    return {'decisions': matched[:min(max(1, int(limit or DEFAULT_LIMIT)), 1000)], 'total': len(entries), 'matched': len(matched), 'query': query or None}


def render_decision_log(log, mask=None):
    m = mask or (lambda t: t)
    lines = ['# Karar günlüğü', '',
             f"Hazırlanma: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')} · {log['matched']}/{log['total']} karar"
             + (f" · filtre: {m(log['query'])}" if log.get('query') else ''), '',
             'Her toplantının en güncel analizinden alınmıştır; paylaşmadan önce kaynağıyla doğrulayın.', '']
    if not log['decisions']: lines.append('- Kayıtlı karar yok.')
    for d in log['decisions']:
        lines += ['', f"## {m(d['text'])}", f"- {m(d['title'] or 'Adsız toplantı')} · {(d['created'] or '')[:10]}"]
        if d['evidence']: lines.append(f"  - Kaynak #{d['evidence'].get('segment_id')}: “{m(d['evidence'].get('quote') or '')}”")
        for p in d['previous']:
            lines.append(f"  - Önceki hâli: {m(p['text'])}  ({m(p['title'] or 'Adsız toplantı')} · {(p['created'] or '')[:10]} · benzerlik {p['similarity']})")
    lines.append('')
    return '\n'.join(lines)


def export_decision_log(store, path, query=None, limit=DEFAULT_LIMIT, mask_names=False, glossary=None):
    log = decision_log(store, query, limit)
    masker = None
    if mask_names:
        from .share import NameMasker, name_groups
        rows = [r for m in store.meetings() for r in store.display_segments(m['id'])]
        masker = NameMasker(name_groups(rows, glossary))
    Path(path).write_text(render_decision_log(log, masker.mask if masker else None), encoding='utf-8')
    return {'path': str(path), 'decisions': len(log['decisions']), 'total': log['total'], 'matched': log['matched'],
            'masked_names': masker.masked_names if masker else 0}
