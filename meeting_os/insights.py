"""What every read-only report needs: the latest analysis of each meeting, the items inside it, and the few
lines they all print the same way. No model call and no writes — these only read what is already stored."""
from datetime import datetime, timezone


def latest_analyses(store, memory):
    """(meeting, its newest analysis) for every meeting that has one, newest meeting first."""
    return [(m, latest) for m in sorted(store.meetings(), key=lambda m: m['created'] or '', reverse=True)
            for latest in (memory.latest(m['id']),) if latest]


def first_evidence(item):
    """The first usable evidence of an analysis item, trimmed to what a report prints; None when there is none."""
    for e in item.get('evidence') or []:
        if isinstance(e, dict): return {'segment_id': e.get('segment_id'), 'start': e.get('start'), 'quote': e.get('quote')}
    return None


def payload_items(store, memory, key):
    """One flat list of `key` items (decisions, questions, risks…) from every meeting's latest analysis,
    newest meeting first, each with its meeting and its first source."""
    return [{'meeting': m['id'], 'title': m['title'], 'created': m['created'], 'text': i.get('text') or '', 'evidence': first_evidence(i)}
            for m, latest in latest_analyses(store, memory) for i in (latest.get('payload') or {}).get(key, [])]


def build_masker(store, meetings=None, glossary=None):
    """A NameMasker over the speaker names of `meetings` (the whole archive by default), in order of first
    appearance. Only the name column is read: the segments themselves are never loaded to work out who spoke."""
    from .share import NameMasker, name_groups
    order = {m['id']: n for n, m in enumerate(meetings if meetings is not None else store.meetings())}
    rows = store.db.execute("SELECT meeting,speaker_name,MIN(CASE WHEN source='chatgpt_manual' THEN id ELSE start END) AS pos,MIN(id) AS sid"
                            " FROM segments WHERE speaker_name IS NOT NULL AND speaker_name<>'' GROUP BY meeting,speaker_name")
    named = sorted((r for r in rows if r['meeting'] in order), key=lambda r: (order[r['meeting']], r['pos'], r['sid']))
    return NameMasker(name_groups([{'speaker_name': r['speaker_name']} for r in named], glossary))


def local_day(created):
    """Calendar day of an ISO UTC timestamp in the Mac's local time zone; None when unparsable."""
    if not isinstance(created, str): return None
    try: dt = datetime.fromisoformat(created)
    except ValueError: return None
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()


def age_days(created):
    """Days since the timestamp was recorded; None when it is unusable."""
    try: dt = datetime.fromisoformat(created or '')
    except ValueError: return None
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - dt).days)


def prepared_header(title, subtitle, note=None):
    """The opening of every report: heading, when it was prepared and what it was drawn from."""
    lines = [f'# {title}', '', f"Hazırlanma: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')} · {subtitle}", '']
    return lines + [note, ''] if note else lines


def source_line(evidence, mask=None):
    """The indented source under a reported item; `mask` applies to the quote only."""
    e = evidence or {}
    quote = e.get('quote') or ''
    return f"  - Kaynak #{e.get('segment_id')}: “{mask(quote) if mask else quote}”"
