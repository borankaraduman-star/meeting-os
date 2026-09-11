"""What every read-only report needs: the latest analysis of each meeting, the items inside it, and the few
lines they all print the same way. No model call and no writes — these only read what is already stored."""
from datetime import datetime, timezone

from .intelligence import REVERSED_NOTE


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
    newest meeting first, each with its meeting, its first source, whether the meeting itself reversed it,
    and whether the analysis it came from is older than the transcript (`stale`) — a report that hides that
    presents a stale sentence as today's truth."""
    return [{'meeting': m['id'], 'title': m['title'], 'created': m['created'], 'text': i.get('text') or '', 'evidence': first_evidence(i),
             'superseded': bool(i.get('superseded')), 'note': i.get('note') or (REVERSED_NOTE if i.get('superseded') else None),
             'stale': bool(latest.get('stale')), 'item_id': i.get('item_id'), 'user_edited': bool(i.get('user_edited')), 'confirmed': bool(i.get('confirmed'))}
            # An item the user removed is not in their summary any more, so no report may keep quoting it back
            # at them; their corrected wording is already on `text`, because `Memory.latest` laid the layer on.
            for m, latest in latest_analyses(store, memory) for i in (latest.get('payload') or {}).get(key, []) if not i.get('removed')]


def stale_meetings(items):
    """How many distinct meetings in `items` are showing an out-of-date analysis."""
    return len({i['meeting'] for i in items if i.get('stale')})


def build_masker(store, meetings=None, glossary=None, owner=None):
    """A NameMasker over the people of `meetings` (the whole archive by default), in order of first appearance.
    Only the name columns are read: the segments themselves are never loaded to work out who spoke.

    A microphone row of a cloud meeting has no `speaker_name` — its label sits in the `speaker` column — so
    building the masker from `speaker_name` alone left the user's own name in plain text in every masked
    export. The mic label and the settings owner are people like anyone else."""
    from .share import NameMasker, name_groups
    order = {m['id']: n for n, m in enumerate(meetings if meetings is not None else store.meetings())}
    rows = list(store.db.execute("SELECT meeting,speaker_name AS name,source,speaker,MIN(CASE WHEN source='chatgpt_manual' THEN id ELSE start END) AS pos,MIN(id) AS sid"
                                 " FROM segments WHERE speaker_name IS NOT NULL AND speaker_name<>'' GROUP BY meeting,speaker_name"))
    rows += list(store.db.execute("SELECT meeting,NULL AS name,source,speaker,MIN(start) AS pos,MIN(id) AS sid"
                                  " FROM segments WHERE source='mic' AND (speaker_name IS NULL OR speaker_name='') GROUP BY meeting,speaker"))
    people = sorted((r for r in rows if r['meeting'] in order), key=lambda r: (order[r['meeting']], r['pos'] if r['pos'] is not None else 0, r['sid']))
    from .intelligence import row_person
    if owner is None:
        from .reports import store_owner
        owner = store_owner(store)
    # A microphone row already resolves to the owner (row_person); the owner is appended as well, carrying a
    # mic source, so they are redacted across a whole range even in the meetings they only listened to.
    # `name_groups` is what decides whether an everyday-word name ("Can sıkıntısı") needs proof they took part.
    names = [{'speaker_name': row_person({'speaker_name': r['name'], 'source': r['source'], 'speaker': r['speaker']}, owner)} for r in people]
    if (owner or '').strip(): names.append({'speaker_name': owner, 'source': 'mic'})
    return NameMasker(name_groups(names, glossary, owner))


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
