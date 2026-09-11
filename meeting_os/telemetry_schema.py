"""ONE whitelist for everything diagnostic that leaves this Mac.

The error journal already had a contract: `errors.export_for_team` builds the upload out of five enumerated
fields and the free message text is not one of them. But two other code paths carried diagnostics to the same
server without passing through it — the heartbeat's `errors` block (the tail of `last-job.log`) and its
`error_journal.last` messages, and a meeting report's `_errors` lines. `team_cloud._anonymous` removed names
and transcripts; it never looked at those. Not an observed leak: a second door in a contract everyone believed
was closed (Codex, 11 Sep 2026, P0 #1, "bu maddenin yayın kapısı").

So there is one door now. `ALLOWED` names every field of every payload kind that may be uploaded, with its
TYPE, and `filter(kind, payload)` builds the outgoing copy out of that list and nothing else. A field nobody
has enumerated does not travel, which is the opposite of the usual arrangement: a new key added to a report
next month is invisible to the team until someone writes it down here.

**Free text never passes.** There is no type in this module that accepts a sentence. A log line, an exception
message, `update_status.message`, a probe's Turkish summary, a recording's human-readable line: none of them
have a type they could be given. What replaces them are classifications and counts — `code` (errors.code_for),
`error_journal.codes`, `team_cloud.last_error_code` — which are bounded, enumerable and say the same thing to
a person reading a fleet view.

The LOCAL files keep everything. `errors.jsonl`, the heartbeat on disk and the report on disk are written in
full detail, because that is what debugging your own Mac needs; this module governs the copy that leaves.
"""
import math
import re

# ---------------------------------------------------------------- types

NUM = 'num'        # int or float (finite), or None
BOOL = 'bool'
STAMP = 'stamp'    # an ISO timestamp and nothing else
TOKEN = 'token'    # one bounded identifier-ish word: a version, a commit, a status, a model id, a check name
LABEL = 'label'    # a short machine name that may contain a space (host, device); never a sentence
NULL = 'null'      # only None passes: the key survives, any value in it does not

TOKEN_RE = re.compile(r'^[A-Za-z0-9._:@/+-]{1,64}$')
LABEL_RE = re.compile(r"^[^\n\r\t]{1,64}$")
STAMP_RE = re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ]?[0-9:.+\-Z]{0,26}$')
KEY_RE = re.compile(r'^[A-Za-z0-9._:/ -]{1,48}$')
LIST_LIMIT = 64


class Map:
    """A mapping whose KEYS are data (statuses, kinds, sources, error codes) and whose values share one type."""
    def __init__(self, value, limit=64): self.value = value; self.limit = limit


class List:
    def __init__(self, item, limit=LIST_LIMIT): self.item = item; self.limit = limit


def _looks_like_path(text):
    """Same rule as errors._team_value: a folder is somebody's disk, never a diagnostic field."""
    return text.startswith(('/', '~', '.')) or '\\' in text or ' /' in text or text.count('/') > 1


def _scalar(spec, value):
    """(ok, value) for one leaf. None passes every scalar type: "not measured" is not a leak."""
    if value is None: return True, None
    if spec is NULL: return False, None
    if spec is BOOL: return (True, value) if isinstance(value, bool) else (False, None)
    if spec is NUM:
        if isinstance(value, bool) or not isinstance(value, (int, float)): return False, None
        return (True, value) if math.isfinite(value) else (False, None)
    if not isinstance(value, str): return False, None
    text = value.strip()
    if not text: return True, text
    if spec is STAMP: return (True, text) if STAMP_RE.match(text) else (False, None)
    if spec is TOKEN: return (True, text) if TOKEN_RE.match(text) and not _looks_like_path(text) else (False, None)
    if spec is LABEL: return (True, text) if LABEL_RE.match(text) and not _looks_like_path(text) else (False, None)
    return False, None


def _apply(spec, value):
    """(ok, filtered) for one node of the schema."""
    if isinstance(spec, dict):
        if value is None: return True, None
        if not isinstance(value, dict): return False, None
        out = {}
        for key, sub in spec.items():
            if key not in value: continue
            ok, cleaned = _apply(sub, value[key])
            if ok: out[key] = cleaned
        return True, out
    if isinstance(spec, Map):
        if value is None: return True, None
        if not isinstance(value, dict): return False, None
        out = {}
        for key, item in list(value.items())[:spec.limit]:
            if not isinstance(key, str) or not KEY_RE.match(key): continue
            ok, cleaned = _apply(spec.value, item)
            if ok: out[key] = cleaned
        return True, out
    if isinstance(spec, List):
        if value is None: return True, None
        if not isinstance(value, (list, tuple)): return False, None
        out = []
        for item in list(value)[:spec.limit]:
            ok, cleaned = _apply(spec.item, item)
            if ok: out.append(cleaned)
        return True, out
    return _scalar(spec, value)


# ---------------------------------------------------------------- the list itself

_CAPTURE = {'chunk_files': Map(NUM), 'announced_chunks': Map(NUM), 'expected_chunks': NUM, 'chunk_seconds': NUM,
            'gaps': NUM, 'full_bytes': Map(NUM), 'journal': TOKEN, 'restarts': NUM, 'relaunches': NUM,
            'wakes': NUM, 'gap_seconds': NUM, 'wake_gap_seconds': NUM, 'capture_errors': NUM}

_SCORECARD = {'clusters': NUM, 'auto_verified': NUM, 'auto_falsified': NUM, 'auto_unreviewed': NUM,
              'auto_correct': NUM, 'auto_wrong': NUM, 'suggestion_confirmed': NUM, 'suggestion_rejected': NUM,
              'missed_known': NUM, 'still_unnamed': NUM, 'auto_precision': NUM}

# What `learning.summary` contributes to the heartbeat: counts, and nothing that could name a word, a person,
# a task or a meeting. The key set of `actions` is `learning.ACTIONS`, which is an enum in code.
# `team` is the time-to-value stopwatch (Codex #6): three stamps and the two durations between them, plus
# the counterfactual the team's samples earned. Stamps and counts — no host, no person, no meeting.
_LEARNING = {'days': NUM, 'events': NUM, 'undo': NUM, 'actions': Map(NUM),
             'names': {'verified': NUM, 'falsified': NUM, 'unreviewed': NUM},
             'team': {'team_join': STAMP, 'team_knowledge_ready': STAMP, 'team_first_value': STAMP,
                      'join_to_ready_seconds': NUM, 'join_to_first_value_seconds': NUM,
                      'profile_effect': {'right': NUM, 'wrong': NUM, 'clusters': NUM, 'meetings': NUM, 'team_samples': NUM}}}

ALLOWED = {
    'heartbeat': {
        'heartbeat_version': NUM, 'host': LABEL, 'macos': TOKEN, 'app_version': TOKEN, 'commit': TOKEN,
        'repo_version': TOKEN, 'signing_partition': BOOL, 'written': STAMP,
        # `message` is the updater's own sentence and has no type here; state and time say what the fleet needs.
        'update_status': {'state': TOKEN, 'time': STAMP},
        'meetings': NUM, 'statuses': Map(NUM), 'last_complete': STAMP,
        'sizes': {'recordings': NUM, 'imports': NUM, 'database': NUM, 'free_disk': NUM},
        'memory_pressure': TOKEN, 'thermal': NUM, 'load_average': List(NUM, 8),
        # A recording in progress: numbers only. The meeting id, the capture folder and the Turkish line the
        # owner reads are not on the list — `reports.recording_line` rebuilds that line from these numbers.
        'recording': {'recording_heartbeat_version': NUM, 'host': LABEL, 'written': STAMP, 'age_seconds': NUM,
                      'elapsed_seconds': NUM, 'chunks': Map(NUM), 'chunks_total': NUM, 'free_disk': NUM,
                      'relaunches': NUM, 'restarts': NUM, 'wakes': NUM, 'gap_seconds': NUM,
                      'wake_gap_seconds': NUM, 'last_chunk_age_seconds': NUM},
        # `errors` (the tail of last-job.log) and `error_journal.last` (the newest messages) are DELIBERATELY
        # absent: those are the two free-text diagnostics paths this schema exists to close. What travels is
        # how many of each kind, how many crashes, and the classification of each line.
        'error_journal': {'last_24h': Map(NUM), 'crashes_24h': NUM, 'codes': Map(NUM)},
        'cloud_blocked': NUM,
        'probe': {'ok': BOOL, 'failed': List(TOKEN, 24), 'warnings': List(TOKEN, 24), 'at': STAMP},
        'team_cloud': {'last_ok': STAMP, 'last_error_code': TOKEN, 'hosts': List(LABEL), 'device': TOKEN},
        'team_profiles': NUM, 'team_words': NUM, 'shared_profiles': NUM, 'shared_words': NUM,
        'learning': _LEARNING,
        # `quality.daily_summary` records (1.2.82): one per (device, day, app_version), numbers as n/d/rate,
        # analysis seconds as percentiles. No word, no name, no meeting id can be expressed in this shape.
        'quality_daily': List({'day': TOKEN, 'device': TOKEN, 'app_version': TOKEN, 'written': STAMP, 'meetings': NUM,
                               'metrics': Map({'n': NUM, 'd': NUM, 'rate': NUM}),
                               'analysis_seconds': {'p50': NUM, 'p95': NUM, 'n': NUM}}, 14),
    },
    'report': {
        'report_version': NUM, 'host': LABEL, 'macos': TOKEN, 'app_version': TOKEN, 'commit': TOKEN,
        'written': STAMP, 'meeting': TOKEN, 'title': NULL, 'created': STAMP, 'status': TOKEN,
        'engine': TOKEN, 'model': TOKEN, 'cloud_mode': TOKEN,
        'duration_seconds': NUM, 'segments': NUM, 'words': NUM, 'capture': _CAPTURE,
        'pieces': NUM, 'pieces_paid': NUM, 'pieces_skipped': NUM, 'cost_usd': NUM, 'uploaded_seconds': NUM,
        'echo_windows_skipped': NUM, 'mic_gated_windows': NUM, 'echo_segments': NUM,
        'identity': {'embedded': NUM, 'named': NUM, 'suggested': NUM, 'fed': NUM},
        'markers': NUM, 'glossary_suggestions': NUM,
        'job_usage': {'cpu_seconds': NUM, 'peak_rss_mb': NUM, 'wall_seconds': NUM, 'low_priority': BOOL, 'upload_workers': NUM},
        'speakers': Map({'segments': NUM, 'seconds': NUM, 'clusters': NUM, 'similarity': NUM,
                         'named': BOOL, 'name': NULL, 'suggested': NULL}),
        'review_queue': Map(NUM),
        'analysis': {'model': TOKEN, 'counts': Map(NUM), 'superseded_decisions': NUM,
                     'coverage': {'segments': NUM, 'chunks': NUM, 'all_chunks_processed': BOOL},
                     'dropped_quotes': NUM, 'dropped_items': NUM, 'cost_usd': NUM, 'calls': NUM,
                     'cost_estimated': BOOL, 'created': STAMP},
        'scorecard': _SCORECARD,
        # `errors` (the tail of last-job.log) is absent on purpose, and so is `identity_error`: both are
        # sentences. `transcript` is absent too — it reaches the server only through the share_text switch,
        # which is the user's own consent and is handled where that switch is read.
    },
    'errors_export': {
        'time': STAMP, 'kind': TOKEN, 'version': TOKEN, 'code': TOKEN,
        # `errors.TEAM_CONTEXT` decides WHICH keys per kind; this is the last gate on their values.
        'context': Map(TOKEN, 8),
    },
}

# `context` values may also be numbers and flags, which Map(TOKEN) would drop. One Map cannot hold three
# scalar types, so the errors export gets its own value rule. Deliberately no LABEL: every context value the
# app actually writes is an identifier, a count or a flag ('failed', 'finalize', 'openai/gpt-4.1-mini', 401),
# and allowing a string with spaces in it would be a door a person's name could walk through.
_CONTEXT_TYPES = (BOOL, NUM, TOKEN)


def _context(value):
    if not isinstance(value, dict): return {}
    out = {}
    for key, item in list(value.items())[:8]:
        if not isinstance(key, str) or not KEY_RE.match(key): continue
        for spec in _CONTEXT_TYPES:
            ok, cleaned = _scalar(spec, item)
            if ok and cleaned is not None: out[key] = cleaned; break
    return out


def filter(kind, payload):   # noqa: A001 — this is the name the review asked for
    """The outgoing copy of `payload`, built from `ALLOWED[kind]` and nothing else.

    An unknown kind produces `{}`: a payload nobody has written a schema for does not leave. Never raises —
    a sync must not fail because a report had a surprising shape; it simply carries less."""
    try:
        spec = ALLOWED.get(kind)
        if spec is None or not isinstance(payload, dict): return {}
        ok, out = _apply(spec, payload)
        if not ok or not isinstance(out, dict): return {}
        if kind == 'errors_export' and isinstance(payload.get('context'), dict):
            out['context'] = _context(payload['context'])
        return out
    except Exception:
        return {}


def kind_of(payload):
    """Which schema one file on its way to the server is judged by: a heartbeat or a meeting report."""
    if isinstance(payload, dict) and 'heartbeat_version' in payload: return 'heartbeat'
    return 'report'
