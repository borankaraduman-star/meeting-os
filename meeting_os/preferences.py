"""Three bounded summary preferences, derived from what the user changed about their own bullets.

Codex, 11 Sep 2026, #8. The app already remembers whether the person likes the detailed view; it never
learned WHICH kind of detail they keep putting back and WHICH repetitions they keep deleting. This module
reads the decisions `insight_layer` stores (`insight_edits`) and derives at most three preferences:

* **`detail`** — `kısa` · `orta` · `ayrıntılı`, from removals whose reason is "gereksiz ayrıntı" against
  edits that make a bullet longer.
* **`bullet_length`** — `kısa` · `uzun`, the median length ratio of the user's wording to the model's,
  counted ONLY over edits that are a matter of wording.
* **`merge_duplicates`** — `az` · `çok`, from removals whose reason is "tekrar".

Three rules this file exists to keep, and every one of them is the review's:

1. **A real correction never reaches the cloud prompt.** What `prompt_line` returns is a FIXED Turkish
   sentence chosen out of `TEMPLATES` below. No bullet of the user's, no name, no number, no meeting —
   the template table is the whole vocabulary, and the budget is ≤300 tokens with zero extra model calls.
2. **A factual correction is not a style preference.** An edit that changes a number, a name or a negation
   is the user fixing what the model got WRONG; counting it as "they like shorter bullets" would teach the
   model the wrong lesson from the most important signal there is. `classify_edit` decides, and only
   `style` edits reach `bullet_length`.
3. **One meeting is not a preference.** Every value needs consistent evidence from at least
   `MIN_MEETINGS` (3) DIFFERENT meetings; below that the value is `None` and nothing is added to the
   prompt at all.

Everything here is local and cheap: one read of `insight_edits`, one read of the analyses it points at, no
model call, no network. It is recomputed by the idle housekeeping pass and only READ at analysis time.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .intelligence import SECTION_LISTS, item_text
from .metrics import normalize

DIR = 'quality'
FILE = 'preferences.json'
MAX_AGE_HOURS = 24            # the derivation is cheap, but it cannot change between two analyses of one day
MIN_MEETINGS = 3              # "en az üç ayrı toplantı" — the review's bar, not a tunable
MIN_EVIDENCE = 3              # and at least this many decisions behind the value
MIN_AGAINST = 2 * MIN_EVIDENCE   # the "no, leave it alone" values need more, because absence is weaker evidence
LONGER, SHORTER = 1.15, 0.85  # a bullet is longer/shorter only outside this band; below it, it was reworded

DETAIL_VALUES = ('kısa', 'orta', 'ayrıntılı')
LENGTH_VALUES = ('kısa', 'uzun')
MERGE_VALUES = ('az', 'çok')
KEYS = ('detail', 'bullet_length', 'merge_duplicates')

# ---------------------------------------------------------------- the only text that can reach a prompt

# One fixed clause per (preference, value). This table IS the prompt vocabulary: nothing the user typed,
# nothing measured, nothing about their meetings can be expressed through it.
TEMPLATES = {
    ('detail', 'kısa'): 'özette ana hatlar yeterli, ayrıntıya girme',
    ('detail', 'ayrıntılı'): 'her maddede kararın ayrıntısını da ver',
    ('bullet_length', 'kısa'): 'maddeler kısa olsun (en fazla 20 kelime)',
    ('bullet_length', 'uzun'): 'maddeler gerektiği kadar uzun olabilir',
    ('merge_duplicates', 'çok'): 'aynı konudaki tekrarları tek maddede birleştir',
    ('merge_duplicates', 'az'): 'benzer maddeleri birleştirme, ayrı tut',
}
PREFIX = 'Kullanıcı tercihi: '
# Said every time a preference is said, because the one thing a style preference must never buy is a lost
# topic: the acceptance bar for #8 is "less rewording AND no drop in what was captured".
GUARD = ' Bu tercih yalnızca anlatım biçimidir; hiçbir konuyu, sayıyı, adı veya kararı atlama.'
PROMPT_TOKEN_BUDGET = 300     # the review's ceiling for the whole addition


def token_estimate(text):
    """A deliberately pessimistic token count for the prompt budget: two characters per token.

    The real tokenizer lives behind whichever model is answering, and this number exists to keep a fixed
    sentence table under a fixed ceiling — being wrong on the safe side is the whole job."""
    return -(-len(text or '') // 2)


def prompt_line(prefs):
    """The sentence that is appended to the analysis prompt, or '' when there is no preference.

    `prefs` is a plain mapping of preference → value. Values that are not in the table (including the
    neutral `orta` and every `None`) contribute nothing, and a line that would break the token budget is
    dropped whole rather than truncated."""
    parts = [TEMPLATES[(key, (prefs or {}).get(key))] for key in KEYS if (key, (prefs or {}).get(key)) in TEMPLATES]
    if not parts:
        return ''
    line = PREFIX + '; '.join(parts) + '.' + GUARD
    return line if token_estimate(line) <= PROMPT_TOKEN_BUDGET else ''


def scale(target, detail):
    """`summary_target` after the detail preference, ±25 % and never outside the existing bounds."""
    from .intelligence import SUMMARY_MAX, SUMMARY_MIN
    factor = {'kısa': 0.75, 'ayrıntılı': 1.25}.get(detail)
    if not factor or not isinstance(target, (int, float)):
        return target
    return max(SUMMARY_MIN, min(SUMMARY_MAX, int(round(target * factor))))


# ---------------------------------------------------------------- style or fact?

NUMBER = re.compile(r'\d+(?:[.,]\d+)*\s*%?|%\s*\d+(?:[.,]\d+)*')
# A capitalised word. Turkish uppercase includes Ç Ğ İ Ö Ş Ü; the genitive and dative suffixes hang off an
# apostrophe ("Deniz'e"), which is not part of the name.
NAME = re.compile(r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]+")
STRIP = '.,;:!?()"«»…'
# Turkish negation, narrow on purpose: the verb suffixes -ma/-me (-mayacak, -madı, -mıyor, -maz) and the
# standalone words. A missed case costs one edit's classification; a false one turns a style edit into a
# "factual" one and drops it, which is the safe direction.
NEGATION = re.compile(r'\bdeğil|\byok\b|\byoktu\b|\bhayır\b|\bhiç\b|\basla\b'
                      r'|m[ae]y[ae]c[ae][kğ]|m[ae]d[ıi]|m[ae]m[ıi]ş|m[ıiuü]yor|\w{2,}m[ae]z\b|\bmemnun değil')


def numbers(text):
    """Every number a bullet states, normalised so "%20" and "% 20" are one number."""
    return frozenset(re.sub(r'\s+', '', m) for m in NUMBER.findall(text or ''))


def _bare(word):
    return word.split("'")[0].split('’')[0].strip(STRIP)


def names(text):
    """The capitalised words of a bullet, folded — the ones that are probably people or products."""
    return frozenset(_bare(w).casefold() for w in (text or '').split() if NAME.fullmatch(_bare(w)))


def _words_of(text):
    return frozenset(_bare(w).casefold() for w in (text or '').split() if _bare(w))


def names_changed(model_text, user_text):
    """Did a name appear or disappear?

    A capitalised word that is still there in the other wording — moved, lower-cased, made the first word
    of the sentence — is not a changed fact. Turkish capitalises the first word of every sentence, so a
    rewrite that only reorders ("Fatura ekranındaki hata…" → "Hata fatura ekranında…") must not read as the
    user replacing a person. What counts is a name that is in one wording and in the other not at all."""
    mine, theirs = _words_of(model_text), _words_of(user_text)
    return bool({n for n in names(model_text) if n not in theirs} | {n for n in names(user_text) if n not in mine})


def negated(text):
    return bool(NEGATION.search(normalize(text or '')))


def classify_edit(model_text, user_text):
    """`'factual'` when the user changed WHAT the bullet says, `'style'` when they changed how it says it.

    Numbers, names and negation are the three things that carry the claim. If any of them differs between
    the model's sentence and the user's, this correction is the user fixing an error, and it says nothing
    about how long they like their bullets (Codex #8: "olgusal düzeltmeler üslup tercihi sayılmasın")."""
    model_text, user_text = model_text or '', user_text or ''
    if numbers(model_text) != numbers(user_text):
        return 'factual'
    if names_changed(model_text, user_text):
        return 'factual'
    if negated(model_text) != negated(user_text):
        return 'factual'
    return 'style'


def _words(text):
    return len((text or '').split())


def _median(values):
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


# ---------------------------------------------------------------- deriving

def _rows(store):
    """Every summary decision this Mac holds, newest last. A missing table is an empty history."""
    try:
        return [dict(r) for r in store.db.execute('SELECT * FROM insight_edits ORDER BY id')]
    except Exception:
        return []


def _model_texts(store, mid, version, cache):
    """What the model itself wrote, by item id, for the analysis a decision was made on.

    The user's own wording is in the decision row; the model's is only in the analysis payload, and that is
    the half a length ratio needs. The analysis the decision names is preferred; if it has been pruned, the
    newest one for that meeting stands in."""
    key = (mid, version)
    if key in cache:
        return cache[key]
    row = None
    try:
        if version is not None:
            row = store.db.execute('SELECT payload FROM analyses WHERE meeting=? AND id=?', (mid, version)).fetchone()
        if row is None:
            row = store.db.execute('SELECT payload FROM analyses WHERE meeting=? ORDER BY id DESC LIMIT 1', (mid,)).fetchone()
    except Exception:
        row = None
    out = {}
    if row is not None:
        try:
            payload = json.loads(row['payload'] or '{}')
        except (TypeError, ValueError):
            payload = {}
        for _, key_name in SECTION_LISTS:
            for item in (payload.get(key_name) or []):
                if isinstance(item, dict) and item.get('item_id') and item['item_id'] not in out:
                    out[item['item_id']] = item_text(item)
    cache[key] = out
    return out


def _value(count, meetings, other_count):
    """One side of a two-sided preference wins only with enough decisions, from enough meetings, and more
    of them than the other side. A tie is not a preference."""
    return count >= MIN_EVIDENCE and len(meetings) >= MIN_MEETINGS and count > other_count


def derive(store):
    """The three preferences and the evidence behind each, computed from this Mac's own decisions.

    Nothing here reads a transcript; the only text touched is the user's own bullet wording, which is
    compared against the model's and then thrown away — only counts and one ratio survive into the record."""
    rows = _rows(store)
    cache = {}
    too_detailed = {'n': 0, 'meetings': set()}
    lengthened = {'n': 0, 'meetings': set()}
    duplicate = {'n': 0, 'meetings': set()}
    removals = {'n': 0, 'meetings': set()}
    ratios = []
    style = {'n': 0, 'meetings': set()}
    factual = 0
    for row in rows:
        mid = row.get('meeting') or ''
        action = row.get('action')
        if action == 'remove':
            removals['n'] += 1
            removals['meetings'].add(mid)
            reason = row.get('reason')
            if reason == 'too_detailed':
                too_detailed['n'] += 1
                too_detailed['meetings'].add(mid)
            elif reason == 'duplicate':
                duplicate['n'] += 1
                duplicate['meetings'].add(mid)
            continue
        if action != 'edit' or not (row.get('text') or '').strip():
            continue
        model = _model_texts(store, mid, row.get('analysis_version'), cache).get(row.get('item_id'))
        if not model:
            continue   # the analysis it was made on is gone; the edit stays a decision, it is not evidence here
        if classify_edit(model, row['text']) == 'factual':
            factual += 1
            continue
        style['n'] += 1
        style['meetings'].add(mid)
        model_words, user_words = _words(model), _words(row['text'])
        if not model_words:
            continue
        ratio = user_words / model_words
        ratios.append(ratio)
        if ratio >= LONGER:
            lengthened['n'] += 1
            lengthened['meetings'].add(mid)

    detail = None
    if _value(too_detailed['n'], too_detailed['meetings'], lengthened['n']):
        detail = 'kısa'
    elif _value(lengthened['n'], lengthened['meetings'], too_detailed['n']):
        detail = 'ayrıntılı'
    elif too_detailed['n'] + lengthened['n'] >= MIN_EVIDENCE and len(too_detailed['meetings'] | lengthened['meetings']) >= MIN_MEETINGS:
        detail = 'orta'   # they push both ways: measured, and deliberately says nothing in the prompt

    median = _median(ratios)
    bullet_length = None
    if style['n'] >= MIN_EVIDENCE and len(style['meetings']) >= MIN_MEETINGS and median is not None:
        if median <= SHORTER:
            bullet_length = 'kısa'
        elif median >= LONGER:
            bullet_length = 'uzun'

    merge = None
    if duplicate['n'] >= MIN_EVIDENCE and len(duplicate['meetings']) >= MIN_MEETINGS:
        merge = 'çok'
    elif duplicate['n'] == 0 and removals['n'] >= MIN_AGAINST and len(removals['meetings']) >= MIN_MEETINGS:
        # They delete plenty of bullets and never once because it repeated another: asking the model to
        # merge harder could only cost topics here. The weaker side of the pair, so it asks for more.
        merge = 'az'

    record = {
        'version': 1,
        'computed': datetime.now(timezone.utc).isoformat(),
        'meetings': len({r.get('meeting') or '' for r in rows}),
        'decisions': len(rows),
        'detail': {'value': detail, 'evidence': {'too_detailed': too_detailed['n'], 'lengthened': lengthened['n'],
                                                 'meetings': len(too_detailed['meetings'] | lengthened['meetings'])}},
        'bullet_length': {'value': bullet_length, 'evidence': {'style_edits': style['n'], 'factual_edits': factual,
                                                               'meetings': len(style['meetings']),
                                                               'median_ratio': round(median, 3) if median is not None else None}},
        'merge_duplicates': {'value': merge, 'evidence': {'duplicate': duplicate['n'], 'removals': removals['n'],
                                                          'meetings': len(duplicate['meetings'])}},
    }
    record['prompt'] = prompt_line(values(record))
    record['prompt_tokens'] = token_estimate(record['prompt'])
    return record


def values(record):
    """Just the three values, the shape `prompt_line` and `scale` take."""
    out = {}
    for key in KEYS:
        entry = (record or {}).get(key)
        value = entry.get('value') if isinstance(entry, dict) else entry
        if value:
            out[key] = value
    return out


# ---------------------------------------------------------------- the file

def path(data_dir):
    return Path(data_dir) / DIR / FILE


def load(data_dir):
    """The last derivation, or `{}`. Every reader (the analysis, the card, the CLI) goes through here —
    deriving is the housekeeping pass's job, never an analysis's."""
    try:
        record = json.loads(path(data_dir).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def save(data_dir, record):
    from .reports import publish
    target = path(data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        publish(target, json.dumps(record, ensure_ascii=False, indent=1))
    except OSError:
        pass   # a preference is never worth failing a job for
    return record


def refresh(store, data_dir, *, max_age_hours=MAX_AGE_HOURS, now=None):
    """Recompute at most once a day, on the idle housekeeping pass. Returns the record with `fresh` saying
    whether this call did the work. Never raises: it runs next to the retention sweep."""
    try:
        existing = load(data_dir)
        moment = now or datetime.now(timezone.utc)
        stamp = existing.get('computed')
        if stamp:
            try:
                if datetime.fromisoformat(stamp) > moment - timedelta(hours=max(1, int(max_age_hours))):
                    return {**existing, 'fresh': False}
            except ValueError:
                pass
        record = derive(store)
        save(data_dir, record)
        return {**record, 'fresh': True}
    except Exception:
        return {'fresh': False}


LABELS = {'detail': 'ayrıntı', 'bullet_length': 'madde uzunluğu', 'merge_duplicates': 'tekrar birleştirme'}


def line(record):
    """One Turkish line for the setup card and the CLI: what was derived, or why nothing was."""
    chosen = values(record)
    if not chosen:
        return f"özet tercihi: veri yetersiz (en az {MIN_MEETINGS} toplantı)"
    return 'özet tercihi: ' + ', '.join(f'{LABELS[k]} {chosen[k]}' for k in KEYS if k in chosen)


__all__ = ['KEYS', 'MIN_MEETINGS', 'PROMPT_TOKEN_BUDGET', 'TEMPLATES', 'classify_edit', 'derive', 'line',
           'load', 'path', 'prompt_line', 'refresh', 'save', 'scale', 'token_estimate', 'values']
