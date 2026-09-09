"""Pre-meeting brief for named attendees: what each person still owes, what they asked, what was decided with them.
Deterministic, from recorded meetings only; a draft the user reads before walking in."""
from .insights import prepared_header
from .memory import Memory
from .metrics import normalize


def _person_meetings(store, name):
    key = normalize(name)
    rows = store.db.execute("SELECT DISTINCT meeting FROM segments WHERE speaker_name IS NOT NULL AND speaker_name<>''").fetchall()
    out = []
    for (mid,) in rows:
        names = {normalize(r[0]) for r in store.db.execute("SELECT DISTINCT speaker_name FROM segments WHERE meeting=? AND speaker_name<>''", (mid,))}
        if key in names or any(key and (key in n or n in key) for n in names if n): out.append(mid)
    return out


def build_brief(store, title, attendees, limit=5):
    memory = Memory(store)
    meetings = {m['id']: m for m in store.meetings() if m['status'] == 'complete'}
    tasks = memory.actions()
    people = []
    for name in [a for a in attendees if a and a.strip()][:12]:
        key = normalize(name)
        owed = [t for t in tasks if t.get('state') in ('open', 'in_progress') and normalize(t.get('owner') or '') and (normalize(t['owner']) in key or key in normalize(t['owner']))]
        mids = [m for m in _person_meetings(store, name) if m in meetings]
        mids.sort(key=lambda m: meetings[m]['created'], reverse=True)
        decisions, questions = [], []
        for mid in mids[:limit]:
            latest = memory.latest(mid)
            payload = (latest or {}).get('payload') or {}
            for d in payload.get('decisions', [])[:5]: decisions.append({'meeting': mid, 'title': meetings[mid]['title'], 'text': d.get('text')})
            for q in payload.get('questions', [])[:5]: questions.append({'meeting': mid, 'title': meetings[mid]['title'], 'text': q.get('text')})
        last = meetings[mids[0]] if mids else None
        people.append({'name': name.strip(), 'owed': [{'title': t['title'], 'due_text': t.get('due_text'), 'meeting_title': t.get('meeting_title'), 'created': t.get('created'), 'due_date': (t.get('payload') or {}).get('due_date')} for t in owed],
                       'meetings': len(mids), 'last_meeting': {'title': last['title'], 'created': last['created']} if last else None, 'decisions': decisions[:8], 'questions': questions[:8]})
    mine = [t for t in tasks if t.get('state') in ('open', 'in_progress') and normalize(t.get('owner') or '') == 'boran']
    return {'title': title or 'Sıradaki toplantı', 'people': people, 'mine': [{'title': t['title'], 'due_text': t.get('due_text'), 'meeting_title': t.get('meeting_title')} for t in mine[:10]]}


def render_brief(brief):
    lines = prepared_header(f"Brifing · {brief['title']}", 'yalnız kayıtlı toplantılardan; dışarı gönderilmez.')
    if not brief['people']: lines.append('- Katılımcı adı yok; takvim etkinliğinde katılımcı bulunamadı.')
    for p in brief['people']:
        seen = f" · son görüşme: {p['last_meeting']['title']} ({p['last_meeting']['created'][:10]})" if p['last_meeting'] else ' · kayıtlı toplantı yok'
        lines += [f"## {p['name']}{seen}"]
        lines.append('**Senden beklediklerim (verdiği sözler):**' if p['owed'] else '_Açık sözü yok._')
        for t in p['owed']: lines.append(f"- {t['title']} · {t.get('due_date') or t.get('due_text') or 'tarih yok'} · {t.get('meeting_title')}")
        if p['questions']:
            lines.append('**Açık sorular (birlikte olduğumuz toplantılardan):**')
            for q in p['questions']: lines.append(f"- {q['text']}  ({q['title']})")
        if p['decisions']:
            lines.append('**Kararlar (hatırlatma):**')
            for d in p['decisions']: lines.append(f"- {d['text']}  ({d['title']})")
        lines.append('')
    lines += ['## Benim açık görevlerim']
    if not brief['mine']: lines.append('- Yok.')
    for t in brief['mine']: lines.append(f"- {t['title']} · {t.get('due_text') or 'tarih yok'} · {t.get('meeting_title')}")
    lines += ['', '## Bu toplantıda', '- (buraya yaz)', '']
    return '\n'.join(lines)
