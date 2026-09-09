"""Beklediklerim: açık görevlerin başkalarına düşen kısmı, kişi kişi, yaşı ve kaynağıyla.
Deterministic only — no model call; nothing is sent anywhere and nothing stored is changed."""
from datetime import datetime, timezone
from .continuity import similarity
from .memory import Memory, normalize

OPEN = ('open', 'in_progress')
REPEAT_THRESHOLD = 0.6


def age_days(created):
    """Days since the task was first recorded; None when the timestamp is unusable."""
    try: dt = datetime.fromisoformat(created or '')
    except ValueError: return None
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - dt).days)


def first_quote(task):
    for e in (task.get('payload') or {}).get('evidence') or []:
        if isinstance(e, dict) and e.get('quote'): return e['quote']
    return None


def reminder_text(owner, items):
    """A short, polite Turkish note the user can copy as is; drafted locally, never sent."""
    lines = [f'Merhaba {owner}, aşağıdaki maddeler bende hâlâ açık görünüyor:']
    for i in items:
        parts = [i['title'], ' · '.join(x for x in (i.get('meeting_title'), i.get('meeting_date')) if x) or 'toplantı bilinmiyor']
        if i.get('due_text'): parts.append(i['due_text'])
        if i.get('age_days') is not None: parts.append(f"{i['age_days']} gündür açık")
        if i.get('repeat'): parts.append('birden fazla toplantıda konuşuldu')
        lines.append('- ' + ' · '.join(parts))
    lines.append('Uygun olduğunda durumlarını yazabilir misin? Teşekkürler.')
    return '\n'.join(lines)


def build_waiting(store, owner='Boran', threshold=REPEAT_THRESHOLD):
    """Open tasks owned by someone other than the user, grouped by that person. An empty owner is not waiting on anyone."""
    memory = Memory(store)
    dates = {m['id']: (m['created'] or '')[:10] for m in store.meetings()}
    everything = [t for t in memory.actions() if t.get('state') in OPEN]
    mine = normalize(owner or '')
    people = {}
    for t in everything:
        who = (t.get('owner') or '').strip()
        if not who or (mine and normalize(who) == mine): continue
        meetings = {o['meeting'] for o in everything if o['meeting'] != t['meeting'] and similarity(t['title'], o['title']) >= threshold}
        meetings.add(t['meeting'])
        item = {'task': t['id'], 'title': t['title'], 'owner': who, 'meeting': t['meeting'], 'meeting_title': t.get('meeting_title'),
                'meeting_date': dates.get(t['meeting']), 'created': t.get('created'), 'due_text': t.get('due_text'), 'state': t.get('state'),
                'stale': t.get('stale'), 'age_days': age_days(t.get('created')), 'quote': first_quote(t),
                'repeat': len(meetings) >= 2, 'meetings': len(meetings)}
        people.setdefault(normalize(who), {'owner': who, 'items': []})['items'].append(item)
    board = []
    for group in people.values():
        group['items'].sort(key=lambda i: (-(i['age_days'] or 0), i.get('created') or '', i['title']))   # longest wait first
        group['reminder_text'] = reminder_text(group['owner'], group['items'])
        board.append(group)
    board.sort(key=lambda g: (-len(g['items']), normalize(g['owner'])))
    return {'people': board, 'total': sum(len(g['items']) for g in board)}


def render_waiting(board):
    lines = ['# Beklediklerim', '',
             f"Hazırlanma: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')} · {len(board['people'])} kişi · {board['total']} madde", '',
             'Yalnız kayıtlı açık görevlerden çıkarılmıştır; hatırlatma metinleri taslaktır, hiçbir yere gönderilmez.', '']
    if not board['people']: lines.append('- Kimseden bekleyen kayıtlı görev yok.')
    for g in board['people']:
        lines += ['', f"## {g['owner']} · {len(g['items'])} madde"]
        for i in g['items']:
            lines.append(f"- {i['title']} · {i.get('meeting_title') or 'toplantı bilinmiyor'} · {i.get('meeting_date') or 'tarih yok'} · "
                         f"{i['age_days'] if i['age_days'] is not None else '?'} gün · {i.get('due_text') or 'tarih yok'}"
                         + (' · TEKRAR EDEN' if i['repeat'] else '') + (' · GÜNCEL DEĞİL' if i.get('stale') else ''))
            if i.get('quote'): lines.append(f"  - Kaynak: “{i['quote']}”")
        lines += ['', '**Hatırlatma taslağı**', '', '```', g['reminder_text'], '```']
    lines.append('')
    return '\n'.join(lines)
