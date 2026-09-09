"""Beklediklerim: açık görevlerin başkalarına düşen kısmı, kişi kişi, yaşı ve kaynağıyla.
Deterministic only — no model call; nothing is sent anywhere and nothing stored is changed."""
from .continuity import similarity_index
from .insights import age_days, prepared_header
from .memory import Memory, normalize

OPEN = ('open', 'in_progress')
REPEAT_THRESHOLD = 0.6


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


def build_waiting(store, owner=None, threshold=REPEAT_THRESHOLD):
    """Open tasks owned by someone other than the user, grouped by that person. An empty owner is not waiting on anyone.
    Callers resolve the name from reports.settings_owner."""
    memory = Memory(store)
    dates = {m['id']: (m['created'] or '')[:10] for m in store.meetings()}
    everything = [t for t in memory.actions() if t.get('state') in OPEN]
    mine = normalize(owner or '')
    links = {}
    for i, j in similarity_index([t['title'] for t in everything], threshold): links.setdefault(i, []).append(j)
    people = {}
    for n, t in enumerate(everything):
        who = (t.get('owner') or '').strip()
        if not who or (mine and normalize(who) == mine): continue
        meetings = {everything[j]['meeting'] for j in links.get(n, ()) if everything[j]['meeting'] != t['meeting']}
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
    lines = prepared_header('Beklediklerim', f"{len(board['people'])} kişi · {board['total']} madde",
                            'Yalnız kayıtlı açık görevlerden çıkarılmıştır; hatırlatma metinleri taslaktır, hiçbir yere gönderilmez.')
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
