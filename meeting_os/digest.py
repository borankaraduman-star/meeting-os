"""End-of-day personal digest: promises made, answers expected and decisions from today's meetings, with sources.
Only what concerns the owner. Draft only — nothing is sent anywhere and nothing stored is changed."""
from datetime import date, datetime, timezone
from .memory import Memory
from .metrics import normalize

STATE_LABELS = {'open': 'açık', 'in_progress': 'devam ediyor', 'done': 'tamamlandı', 'dismissed': 'kaldırıldı'}


def local_day(created):
    """Calendar day of an ISO UTC timestamp in the Mac's local time zone; None when unparsable."""
    if not isinstance(created, str): return None
    try: dt = datetime.fromisoformat(created)
    except ValueError: return None
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()


def parse_day(day):
    if day is None: return datetime.now(timezone.utc).astimezone().date()
    if isinstance(day, date): return day
    try: return date.fromisoformat(str(day))
    except ValueError: raise ValueError('Gün YYYY-AA-GG biçiminde olmalı')


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


def build_digest(store, day=None, owner='Boran'):
    day = parse_day(day)
    memory = Memory(store)
    meetings = sorted((m for m in store.meetings() if local_day(m['created']) == day), key=lambda m: m['created'])
    titles = {m['id']: m['title'] for m in meetings}
    wanted = normalize(owner or '')
    tasks = [t for t in memory.actions() if t.get('meeting') in titles and wanted and normalize(t.get('owner') or '') == wanted and t.get('state') != 'dismissed']
    lines = []; questions = []; decisions = []
    for m in meetings:
        line, latest = meeting_line(store, memory, m)
        lines.append(line)
        payload = (latest or {}).get('payload') or {}
        for q in payload.get('questions', []): questions.append({'meeting': m['id'], 'title': m['title'], 'text': q.get('text'), 'evidence': q.get('evidence', [])})
        for d in payload.get('decisions', []): decisions.append({'meeting': m['id'], 'title': m['title'], 'text': d.get('text'), 'evidence': d.get('evidence', [])})
    return {'day': day.isoformat(), 'owner': owner, 'meetings': lines, 'tasks': tasks, 'questions': questions, 'decisions': decisions}


def _source(evidence):
    return f"  - Kaynak #{evidence.get('segment_id')}: “{evidence.get('quote', '')}”"


def render_digest(digest):
    day = digest['day']
    lines = [f'# Gün sonu özeti · {day}', '',
             f"Hazırlanma: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')} · {digest['owner']} için · {len(digest['meetings'])} toplantı", '',
             'Bu özet yalnız o gün kaydedilen toplantılardan çıkarılmıştır; dışarı otomatik gönderilmez. Her maddeyi kaynağıyla doğrulayın.', '']
    lines += ['## Verdiğin sözler']
    if not digest['tasks']: lines.append('- Bugün sana düşen kayıtlı görev yok.')
    for t in digest['tasks']:
        title = t.get('meeting_title') or ''
        lines.append(f"- {t['title']} · {t.get('due_text') or 'tarih yok'} · {STATE_LABELS.get(t.get('state'), t.get('state'))}" + (' · GÜNCEL DEĞİL' if t.get('stale') else '') + f'  ({title})')
        for e in (t.get('payload') or {}).get('evidence', [])[:1]: lines.append(_source(e))
    lines += ['', '## Senden beklenen cevaplar']
    if not digest['questions']: lines.append('- Kayıtlı açık soru yok.')
    for q in digest['questions']:
        lines.append(f"- {q['text']}  ({q['title']})")
        for e in q['evidence'][:1]: lines.append(_source(e))
    lines += ['', '## Değişen/alınan kararlar']
    if not digest['decisions']: lines.append('- Kayıtlı karar yok.')
    for d in digest['decisions']:
        lines.append(f"- {d['text']}  ({d['title']})")
        for e in d['evidence'][:1]: lines.append(_source(e))
    lines += ['', '## Bugünkü toplantılar']
    if not digest['meetings']: lines.append('- Bu gün kayıtlı toplantı yok.')
    for m in digest['meetings']:
        analysis = 'analiz güncel değil' if m['stale'] else ('analiz hazır' if m['analyzed'] else 'analiz yok')
        lines.append(f"- {m['title'] or 'Adsız toplantı'} · {duration_label(m['seconds'])} · {m['speakers']} konuşmacı · {analysis}")
    lines.append('')
    return '\n'.join(lines)
