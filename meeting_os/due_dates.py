"""Turn the free-text timing a meeting mentioned ("yarın", "haftaya salı", "ay sonu") into a *suggested* date.

Anchored to the meeting date. Only a suggestion: the app asks the user to approve before anything is written,
and an expression that is not clearly a date yields None rather than a guess."""
import calendar, re
from datetime import date, timedelta

from .memory import RETIRED

RETIRED_OR_DONE = ('done',) + RETIRED

DAYS = {'pazartesi': 0, 'salı': 1, 'sali': 1, 'çarşamba': 2, 'carsamba': 2, 'perşembe': 3, 'persembe': 3, 'cuma': 4, 'cumartesi': 5, 'pazar': 6}
MONTHS = {'ocak': 1, 'şubat': 2, 'subat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'mayis': 5, 'haziran': 6, 'temmuz': 7, 'ağustos': 8, 'agustos': 8, 'eylül': 9, 'eylul': 9, 'ekim': 10, 'kasım': 11, 'kasim': 11, 'aralık': 12, 'aralik': 12}
NUMBER_WORDS = {'bir': 1, 'iki': 2, 'üç': 3, 'uc': 3, 'dört': 4, 'dort': 4, 'beş': 5, 'bes': 5, 'altı': 6, 'alti': 6, 'yedi': 7, 'sekiz': 8, 'dokuz': 9, 'on': 10, 'on beş': 15, 'yirmi': 20}


def _norm(text):
    t = (text or '').replace('İ', 'i').replace('I', 'ı').lower()
    return re.sub(r'\s+', ' ', t).strip()


def _weekday_on_or_after(anchor, weekday, weeks_ahead=0):
    delta = (weekday - anchor.weekday()) % 7
    if delta == 0: delta = 7   # "salı" said on a Tuesday means next Tuesday
    return anchor + timedelta(days=delta + 7 * weeks_ahead)


def _number(token):
    if token.isdigit(): return int(token)
    return NUMBER_WORDS.get(token)


def suggest_due(text, anchor):
    """Return a date or None. `anchor` is the meeting date (datetime.date)."""
    t = _norm(text)
    if not t: return None
    if re.search(r'\bbugün\b', t): return anchor
    if re.search(r'\böbür gün\b', t): return anchor + timedelta(days=2)
    if re.search(r'\byarın\b', t): return anchor + timedelta(days=1)
    m = re.search(r'\b(\d{1,2})\s+(' + '|'.join(MONTHS) + r')\b', t)
    if m:
        day, month = int(m.group(1)), MONTHS[m.group(2)]; year = anchor.year + (1 if month < anchor.month else 0)
        try: return date(year, month, min(day, calendar.monthrange(year, month)[1]))
        except ValueError: return None
    m = re.search(r'\b(\d{1,2})\s*[\'’]?\s*(?:i|ı|si|sı|u|ü|ü)?n?[ae]\s+kadar\b', t) or re.search(r"\bayın (\d{1,2})", t)
    if m:
        day = int(m.group(1)); month, year = anchor.month, anchor.year
        if day < anchor.day: month += 1
        if month > 12: month, year = 1, year + 1
        try: return date(year, month, min(day, calendar.monthrange(year, month)[1]))
        except ValueError: return None
    if re.search(r'\bay sonu', t) or re.search(r'\bayın son', t): return date(anchor.year, anchor.month, calendar.monthrange(anchor.year, anchor.month)[1])
    if re.search(r'\bhafta sonu', t): return _weekday_on_or_after(anchor, 5) if anchor.weekday() < 5 else anchor
    m = re.search(r'\b(\d+|' + '|'.join(NUMBER_WORDS) + r')\s+(gün|hafta|ay)\s+(içinde|sonra|içerisinde)\b', t)
    if m:
        n = _number(m.group(1)) or 0
        if m.group(2) == 'gün': return anchor + timedelta(days=n)
        if m.group(2) == 'hafta': return anchor + timedelta(weeks=n)
        month = anchor.month + n; year = anchor.year + (month - 1) // 12; month = (month - 1) % 12 + 1
        return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))
    for name, wd in DAYS.items():
        if re.search(r'\b(haftaya|gelecek hafta|önümüzdeki hafta)\s+' + name + r'\b', t): return _weekday_on_or_after(anchor, wd, 1 if _weekday_on_or_after(anchor, wd) <= anchor + timedelta(days=6 - anchor.weekday()) else 0)
    for name, wd in DAYS.items():
        if re.search(r'\b(bu|önümüzdeki|gelecek|)\s*' + name + r'(ya|ye|a|e|\'?ya|\'?ye)?\b', t): return _weekday_on_or_after(anchor, wd)
    if re.search(r'\b(haftaya|gelecek hafta|önümüzdeki hafta|bir hafta sonra)\b', t): return anchor + timedelta(days=7)
    if re.search(r'\bbu hafta\b', t): return anchor + timedelta(days=max(0, 4 - anchor.weekday()))   # Friday of this week
    if re.search(r'\b(gelecek ay|önümüzdeki ay|aya)\b', t):
        month = anchor.month + 1; year = anchor.year + (1 if month > 12 else 0); month = 1 if month > 12 else month
        return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))
    return None


def suggestions_for_tasks(tasks, anchors=None):
    """tasks: iterable of dicts with 'id', 'due_text', 'created' (ISO), optional 'meeting' and payload.due_date.
    Returns proposals for tasks without a confirmed date.

    `anchors` maps a meeting id to that meeting's local calendar day, and that is what "yarın" is counted from:
    the day the words were spoken. The task row's own `created` is the moment the ANALYSIS was saved, in UTC —
    a meeting recorded at 00:30 local was analysed on the previous UTC day, and every relative date came out
    one day early. Without an anchor the local day of `created` is the closest honest fallback."""
    from .insights import local_day
    out = []
    for t in tasks:
        payload = t.get('payload') or {}
        if not t.get('due_text') or payload.get('due_date') or t.get('state') in RETIRED_OR_DONE: continue
        anchor = (anchors or {}).get(t.get('meeting')) or local_day(t.get('created'))
        if anchor is None: continue
        d = suggest_due(t['due_text'], anchor)
        if d: out.append({'task': t['id'], 'title': t.get('title'), 'due_text': t['due_text'], 'suggested': d.isoformat(), 'anchor': anchor.isoformat()})
    return out
