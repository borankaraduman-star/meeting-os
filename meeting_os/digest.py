"""End-of-day personal digest and the weekly stakeholder report over a date range: promises made, answers expected,
decisions, risks and the tasks opened/closed in the period, with sources. Draft only — nothing is sent anywhere and
nothing stored is changed; masking happens in the rendered text only."""
from datetime import date, datetime, timezone
from .insights import build_masker, local_day, prepared_header, source_line
from .memory import Memory
from .metrics import normalize

STATE_LABELS = {'open': 'açık', 'in_progress': 'devam ediyor', 'done': 'tamamlandı', 'dismissed': 'kaldırıldı'}


def parse_day(day):
    if day is None: return datetime.now(timezone.utc).astimezone().date()
    if isinstance(day, date): return day
    try: return date.fromisoformat(str(day))
    except ValueError: raise ValueError('Gün YYYY-AA-GG biçiminde olmalı')


def parse_range(day=None, start=None, end=None):
    """One local day by default; --from/--to widen it. Either end alone is enough."""
    if start is None and end is None:
        d = parse_day(day); return d, d
    first = parse_day(start if start is not None else end)
    last = parse_day(end if end is not None else start)
    if last < first: raise ValueError('Bitiş tarihi başlangıçtan önce olamaz')
    return first, last


def duration_label(seconds):
    minutes = int(round(seconds / 60))
    if minutes < 1: return '1 dk altı'
    if minutes < 60: return f'{minutes} dk'
    return f'{minutes // 60} sa {minutes % 60:02d} dk'


def meeting_line(store, memory, m):
    rows = store.display_segments(m['id'])
    seconds = max((r['end'] for r in rows if r.get('end') is not None), default=0)
    speakers = {r.get('speaker_name') or r.get('speaker') for r in rows}
    speakers.discard(None); speakers.discard(''); speakers.discard('unknown')
    latest = memory.latest(m['id'])
    return {'id': m['id'], 'title': m['title'], 'created': m['created'], 'status': m['status'], 'seconds': seconds,
            'speakers': len(speakers), 'analyzed': latest is not None, 'stale': bool(latest and latest.get('stale'))}, latest


def build_digest(store, day=None, owner='Boran', start=None, end=None, mask_names=False, glossary=None):
    first, last = parse_range(day, start, end)
    memory = Memory(store)
    inside = lambda created: (lambda d: d is not None and first <= d <= last)(local_day(created))
    meetings = sorted((m for m in store.meetings() if inside(m['created'])), key=lambda m: m['created'])
    titles = {m['id']: m['title'] for m in meetings}
    wanted = normalize(owner or '')
    period = [t for t in memory.actions() if t.get('meeting') in titles]
    tasks = [t for t in period if wanted and normalize(t.get('owner') or '') == wanted and t.get('state') != 'dismissed']
    lines = []; questions = []; decisions = []; risks = []; groups = []
    for m in meetings:
        line, latest = meeting_line(store, memory, m)
        lines.append(line)
        payload = (latest or {}).get('payload') or {}
        pick = lambda key: [{'meeting': m['id'], 'title': m['title'], 'text': i.get('text'), 'evidence': i.get('evidence', [])} for i in payload.get(key, [])]
        qs, ds, rs = pick('questions'), pick('decisions'), pick('risks')
        questions += qs; decisions += ds; risks += rs
        own = [t for t in period if t.get('meeting') == m['id']]
        groups.append({'meeting': m['id'], 'title': m['title'], 'created': m['created'], 'decisions': ds, 'risks': rs, 'questions': qs,
                       'closed': [t for t in own if t.get('state') in ('done', 'dismissed') and inside(t.get('updated'))],
                       'open': [t for t in own if t.get('state') in ('open', 'in_progress')]})
    groups.reverse()   # newest meeting first; the per-day lists keep their chronological order
    digest = {'day': last.isoformat(), 'from': first.isoformat(), 'to': last.isoformat(), 'range': first != last, 'owner': owner,
              'meetings': lines, 'tasks': tasks, 'questions': questions, 'decisions': decisions, 'risks': risks, 'groups': groups, 'masked_names': 0}
    if mask_names: mask_digest(store, digest, meetings, glossary)
    return digest


def mask_digest(store, digest, meetings, glossary=None):
    """Replace speaker and glossary person names in the rendered digest only; stored rows are untouched."""
    masker = build_masker(store, meetings, glossary); mask = masker.mask
    def item(i):
        i['text'] = mask(i.get('text') or ''); i['title'] = mask(i.get('title') or '')
        i['evidence'] = [{**e, 'quote': mask(e.get('quote') or '')} for e in i.get('evidence') or []]
    def task(t):
        t['title'] = mask(t.get('title') or ''); t['owner'] = mask(t.get('owner') or '') or None
        t['meeting_title'] = mask(t.get('meeting_title') or '')
    for key in ('questions', 'decisions', 'risks'):
        for i in digest[key]: item(i)
    for t in digest['tasks']: task(t)
    digest['owner'] = mask(digest.get('owner') or '')
    for m in digest['meetings']: m['title'] = mask(m.get('title') or '')
    for g in digest['groups']:
        g['title'] = mask(g.get('title') or '')
        for key in ('decisions', 'risks', 'questions'):
            for i in g[key]: item(i)
        for key in ('closed', 'open'):
            for t in g[key]: task(t)
    digest['masked_names'] = masker.masked_names
    return digest


def _task_line(t):
    return f"- {t['title']} · {t.get('owner') or 'sahibi belirsiz'} · {t.get('due_text') or 'tarih yok'} · {STATE_LABELS.get(t.get('state'), t.get('state'))}" + (' · GÜNCEL DEĞİL' if t.get('stale') else '')


def render_groups(digest):
    """Weekly stakeholder view: every meeting of the period, newest first, with what it decided, opened and closed."""
    lines = ['', '## Toplantı toplantı']
    if not digest['groups']: lines.append('- Bu dönemde kayıtlı toplantı yok.')
    for g in digest['groups']:
        lines += ['', f"### {g['title'] or 'Adsız toplantı'} · {(g['created'] or '')[:10]}"]
        for key, label, empty in (('decisions', 'Kararlar', 'Kayıtlı karar yok.'), ('risks', 'Riskler', 'Kayıtlı risk yok.'), ('questions', 'Cevapsız sorular', 'Kayıtlı açık soru yok.')):
            lines.append(f'**{label}**')
            if not g[key]: lines.append(f'- {empty}')
            for i in g[key]:
                lines.append(f"- {i['text']}")
                for e in (i.get('evidence') or [])[:1]: lines.append(source_line(e))
        lines.append('**Bu dönemde kapanan görevler**')
        if not g['closed']: lines.append('- Bu dönemde kapanan görev yok.')
        for t in g['closed']: lines.append(_task_line(t))
        lines.append('**Hâlâ açık görevler**')
        if not g['open']: lines.append('- Açık görev yok.')
        for t in g['open']: lines.append(_task_line(t))
    return lines


def render_digest(digest):
    day = digest['day']; first = digest.get('from', day); last = digest.get('to', day); ranged = bool(digest.get('range'))
    lines = prepared_header(f'Dönem özeti · {first} → {last}' if ranged else f'Gün sonu özeti · {day}',
                            f"{digest['owner']} için · {len(digest['meetings'])} toplantı"
                            + (f" · isimler maskelendi ({digest['masked_names']})" if digest.get('masked_names') else ''),
                            ('Bu özet yalnız o dönemde kaydedilen toplantılardan' if ranged else 'Bu özet yalnız o gün kaydedilen toplantılardan')
                            + ' çıkarılmıştır; dışarı otomatik gönderilmez. Her maddeyi kaynağıyla doğrulayın.')
    lines += ['## Verdiğin sözler']
    if not digest['tasks']: lines.append('- Bu dönemde sana düşen kayıtlı görev yok.' if ranged else '- Bugün sana düşen kayıtlı görev yok.')
    for t in digest['tasks']:
        title = t.get('meeting_title') or ''
        lines.append(f"- {t['title']} · {t.get('due_text') or 'tarih yok'} · {STATE_LABELS.get(t.get('state'), t.get('state'))}" + (' · GÜNCEL DEĞİL' if t.get('stale') else '') + f'  ({title})')
        for e in (t.get('payload') or {}).get('evidence', [])[:1]: lines.append(source_line(e))
    lines += ['', '## Senden beklenen cevaplar']
    if not digest['questions']: lines.append('- Kayıtlı açık soru yok.')
    for q in digest['questions']:
        lines.append(f"- {q['text']}  ({q['title']})")
        for e in q['evidence'][:1]: lines.append(source_line(e))
    lines += ['', '## Değişen/alınan kararlar']
    if not digest['decisions']: lines.append('- Kayıtlı karar yok.')
    for d in digest['decisions']:
        lines.append(f"- {d['text']}  ({d['title']})")
        for e in d['evidence'][:1]: lines.append(source_line(e))
    if ranged: lines += render_groups(digest)
    lines += ['', '## Dönemdeki toplantılar' if ranged else '## Bugünkü toplantılar']
    if not digest['meetings']: lines.append('- Bu dönemde kayıtlı toplantı yok.' if ranged else '- Bu gün kayıtlı toplantı yok.')
    for m in digest['meetings']:
        analysis = 'analiz güncel değil' if m['stale'] else ('analiz hazır' if m['analyzed'] else 'analiz yok')
        lines.append(f"- {m['title'] or 'Adsız toplantı'} · {duration_label(m['seconds'])} · {m['speakers']} konuşmacı · {analysis}")
    lines.append('')
    return '\n'.join(lines)
