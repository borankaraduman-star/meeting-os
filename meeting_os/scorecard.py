"""Toplantı karnesi: bir toplantının süresi, konuşma payı, karar/görev/soru/risk sayısı ve bulut maliyeti,
ve bir dönemin toplamı. Read-only — no model call, nothing stored is changed.
Talk share repeats the app's own computation (TalkShare.compute + Row.label): echo rows out, grouped by display label."""
from datetime import datetime, timedelta, timezone
from .digest import parse_range
from .insights import local_day
from .memory import Memory

DEFAULT_DAYS = 7
TOP_SPEAKERS = 8


def label(row):
    """The label the app shows for a row (Row.label); talk share must group by exactly the same string."""
    name = (row.get('speaker_name') or '').strip()
    if name: return name
    flags = row.get('flags') or []
    if 'provisional' in flags: return 'Geçici konuşmacı'
    suggested = (row.get('suggested') or '').strip()
    if suggested: return suggested + '?'
    if 'possible_echo' in flags: return 'Hoparlör yankısı'
    speaker = row.get('speaker') or ''
    if 'cloud_transcript' in flags and speaker and speaker != 'unknown': return speaker
    tail = speaker.split(':')[-1]
    if tail.startswith('S') and tail[1:].isdigit(): return f'Konuşmacı {int(tail[1:]) + 1}'
    return 'İsimsiz konuşmacı'


def percent(share):
    return int(share * 100 + 0.5)   # Swift's (share*100).rounded(): half away from zero, not banker's rounding


def talk_share(rows):
    """Seconds and share per display label. Microphone echo of the speakers is excluded so the host is not double-counted."""
    totals = {}; named = set()
    for r in rows:
        start, end = r.get('start'), r.get('end')
        if 'possible_echo' in (r.get('flags') or []) or start is None or end is None or end <= start: continue
        who = label(r); totals[who] = totals.get(who, 0.0) + (end - start)
        if (r.get('speaker_name') or '').strip(): named.add(who)
    total = sum(totals.values())
    if total <= 0: return []
    out = [{'label': who, 'seconds': round(sec, 1), 'minutes': round(sec / 60, 1), 'share': round(sec / total, 4),
            'percent': percent(sec / total), 'named': who in named} for who, sec in totals.items()]
    out.sort(key=lambda s: (-s['seconds'], s['label']))
    return out


def meeting_costs(store):
    """Real OpenRouter transcription charges per meeting; the table only exists once a cloud run happened."""
    if not store.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cloud_chunks'").fetchone(): return {}
    return {r[0]: round(float(r[1] or 0), 4) for r in store.db.execute("SELECT meeting,sum(json_extract(usage,'$.cost')) FROM cloud_chunks GROUP BY meeting")}


def meeting_scorecard(store, memory, m, cost=0.0):
    rows = store.display_segments(m['id'])
    seconds = max((r['end'] for r in rows if r.get('end') is not None), default=0)
    latest = memory.latest(m['id'])
    payload = (latest or {}).get('payload') or {}
    return {'meeting': m['id'], 'title': m['title'], 'created': m['created'], 'seconds': round(seconds, 1), 'minutes': round(seconds / 60, 1),
            'speakers': talk_share(rows), 'counts': {k: len(payload.get(k, [])) for k in ('decisions', 'actions', 'questions', 'risks')},
            'analyzed': latest is not None, 'stale': bool(latest and latest.get('stale')), 'cost': cost}


def period_range(start=None, end=None):
    """Last seven local days by default; --from/--to override it exactly like the digest."""
    if start is None and end is None:
        today = datetime.now(timezone.utc).astimezone().date()
        return today - timedelta(days=DEFAULT_DAYS - 1), today
    return parse_range(None, start, end)


def build_scorecard(store, start=None, end=None):
    first, last = period_range(start, end)
    memory = Memory(store)
    money = meeting_costs(store)
    inside = lambda created: (lambda d: d is not None and first <= d <= last)(local_day(created))
    meetings = [m for m in store.meetings() if m['status'] == 'complete' and inside(m['created'])]   # newest first
    cards = [meeting_scorecard(store, memory, m, money.get(m['id'], 0.0)) for m in meetings]
    ids = {c['meeting'] for c in cards}
    people = {}
    for c in cards:
        for s in c['speakers']:
            if not s['named']: continue   # unnamed clusters are not people yet
            p = people.setdefault(s['label'], {'name': s['label'], 'seconds': 0.0, 'meetings': 0})
            p['seconds'] += s['seconds']; p['meetings'] += 1
    top = sorted(people.values(), key=lambda p: (-p['seconds'], p['name']))[:TOP_SPEAKERS]
    for p in top: p['seconds'] = round(p['seconds'], 1); p['minutes'] = round(p['seconds'] / 60, 1)
    seconds = sum(c['seconds'] for c in cards)
    period = {'from': first.isoformat(), 'to': last.isoformat(), 'meetings': len(cards), 'seconds': round(seconds, 1), 'hours': round(seconds / 3600, 2),
              'decisions': sum(c['counts']['decisions'] for c in cards), 'questions': sum(c['counts']['questions'] for c in cards),
              'risks': sum(c['counts']['risks'] for c in cards), 'tasks': sum(1 for t in memory.actions() if t.get('meeting') in ids),
              'cost': round(sum(c['cost'] for c in cards), 4), 'speakers': top}
    return {'period': period, 'meetings': cards}
