"""Pre-meeting brief for named attendees: what each person still owes, what they asked, what was decided with them.
Deterministic, from recorded meetings only; a draft the user reads before walking in."""
from .insights import prepared_header
from .intelligence import REVERSED_NOTE
from .memory import Memory, owner_key


def same_person(a, b):
    """Two written forms of one name, or not.

    `owner_key` equality decides it — case and İ/I/ı are noise, exactly as in the waiting board and the
    digest. A one-word name may additionally match one WHOLE word of a longer one ("Ayşe" ↔ "Ayşe Yılmaz"),
    because a calendar attendee is a full name and an analysis owner is usually a first name. What is gone
    is the substring test this brief used to run: it made "Ali" the owner of everything "Salih" owed."""
    ka, kb = owner_key(a or ''), owner_key(b or '')
    if not ka or not kb: return False
    if ka == kb: return True
    short, long = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    return ' ' not in short and short in long.split()


def _person_meetings(store, name):
    rows = store.db.execute("SELECT DISTINCT meeting FROM segments WHERE speaker_name IS NOT NULL AND speaker_name<>''").fetchall()
    out = []
    for (mid,) in rows:
        names = [r[0] for r in store.db.execute("SELECT DISTINCT speaker_name FROM segments WHERE meeting=? AND speaker_name<>''", (mid,))]
        if any(same_person(name, n) for n in names): out.append(mid)
    return out


def build_brief(store, title, attendees, limit=5, owner=None):
    memory = Memory(store)
    meetings = {m['id']: m for m in store.meetings() if m['status'] == 'complete'}
    tasks = memory.actions()
    people = []
    for name in [a for a in attendees if a and a.strip()][:12]:
        owed = [t for t in tasks if t.get('state') in ('open', 'in_progress') and same_person(t.get('owner'), name)]
        mids = [m for m in _person_meetings(store, name) if m in meetings]
        mids.sort(key=lambda m: meetings[m]['created'], reverse=True)
        decisions, questions = [], []
        for mid in mids[:limit]:
            latest = memory.latest(mid)
            payload = (latest or {}).get('payload') or {}
            # The user's own summary, not the model's: what they removed is not briefed back at them.
            from .insight_layer import visible
            for d in visible(payload.get('decisions', []))[:5]: decisions.append({'meeting': mid, 'title': meetings[mid]['title'], 'text': d.get('text'), 'superseded': bool(d.get('superseded')), 'note': d.get('note') or (REVERSED_NOTE if d.get('superseded') else None)})
            for q in visible(payload.get('questions', []))[:5]: questions.append({'meeting': mid, 'title': meetings[mid]['title'], 'text': q.get('text')})
        last = meetings[mids[0]] if mids else None
        people.append({'name': name.strip(), 'owed': [{'title': t['title'], 'due_text': t.get('due_text'), 'meeting_title': t.get('meeting_title'), 'created': t.get('created'), 'due_date': (t.get('payload') or {}).get('due_date')} for t in owed],
                       'meetings': len(mids), 'last_meeting': {'title': last['title'], 'created': last['created']} if last else None, 'decisions': decisions[:8], 'questions': questions[:8]})
    mine = [t for t in tasks if t.get('state') in ('open', 'in_progress') and owner and owner_key(t.get('owner') or '') == owner_key(owner)]
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
            for d in p['decisions']: lines.append(f"- {d['text']}" + (f" ({d.get('note') or REVERSED_NOTE})" if d.get('superseded') else '') + f"  ({d['title']})")
        lines.append('')
    lines += ['## Benim açık görevlerim']
    if not brief['mine']: lines.append('- Yok.')
    for t in brief['mine']: lines.append(f"- {t['title']} · {t.get('due_text') or 'tarih yok'} · {t.get('meeting_title')}")
    lines += ['', '## Bu toplantıda', '- (buraya yaz)', '']
    return '\n'.join(lines)
