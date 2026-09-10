"""Bounded metadata-only timeline metrics. No audio quality or queue inference."""
import json
import math
import os

JOURNAL_TAIL_BYTES = 64*1024


def journal_events(path, tail=JOURNAL_TAIL_BYTES):
    """Parsed events from the end of a capture journal, newest last. Only the last `tail` bytes are read:
    a long recording writes thousands of chunk lines and the state anyone asks about is at the end. A line the
    window cuts in half simply fails to parse and is dropped, as a truncated line always was."""
    try:
        with open(path, 'rb') as f:
            f.seek(max(0, os.path.getsize(path) - tail))
            data = f.read().decode('utf-8', errors='replace')
    except OSError: return []
    events = []
    for line in data.splitlines():
        try: event = json.loads(line)
        except ValueError: continue
        if isinstance(event, dict): events.append(event)
    return events


COUNTER_MARKERS = ('restarted', 'relaunch', 'wake', 'gap', 'error')   # substrings that make a line worth parsing


def _blank_health():
    return {'restarts': 0, 'relaunches': 0, 'wakes': 0, 'gap_seconds': 0.0, 'wake_gap_seconds': 0.0, 'capture_errors': 0}


def _count(out, event):
    kind = event.get('event')
    if kind == 'restarted': out['restarts'] += 1
    elif kind == 'relaunch': out['relaunches'] += 1
    elif kind == 'error': out['capture_errors'] += 1
    elif kind == 'wake':
        out['wakes'] += 1
        gap = event.get('gap')
        if type(gap) in (int, float) and math.isfinite(gap) and gap > 0: out['wake_gap_seconds'] += float(gap)
    elif kind == 'gap':
        a, b = event.get('start'), event.get('end')
        if type(a) in (int, float) and type(b) in (int, float) and b > a: out['gap_seconds'] += float(b-a)


def _rounded(out):
    out['gap_seconds'] = round(out['gap_seconds'], 2); out['wake_gap_seconds'] = round(out['wake_gap_seconds'], 2)
    return out


def capture_health(events):
    """What the owner asks about after a meeting: how often the audio stream was rebuilt, how often the
    supervisor had to replace the whole helper, how many times the Mac woke, and how many seconds were lost.
    Sleep costs wall-clock seconds that never reach the audio timeline, so they are counted separately from
    the chunk discontinuities the helper writes as 'gap'."""
    out = _blank_health()
    for event in events: _count(out, event)
    return _rounded(out)


def journal_counters(path):
    """The same counters, from the WHOLE journal instead of its tail. These events happen a handful of times and
    early — a wake or a relaunch near the start of a long meeting — while the helper writes a chunk line every
    12 seconds, so past roughly 35 minutes the 64 KB window holds nothing but chunks and every counter reads
    zero. Scanned line by line and parsed only where an event name appears, so it costs a read, not memory."""
    out = _blank_health()
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if not any(marker in line for marker in COUNTER_MARKERS): continue
                try: event = json.loads(line)
                except ValueError: continue
                if isinstance(event, dict): _count(out, event)
    except OSError: return _rounded(out)
    return _rounded(out)


def timeline_metrics(events):
    sources = {'mic': [], 'system': []}
    for count, event in enumerate(events):
        if count >= 10000:
            raise ValueError('At most10000 chunks are supported')
        source = event.get('source')
        start, duration = event.get('start'), event.get('duration')
        if source not in sources or any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, duration)):
            raise ValueError('Invalid chunk metadata')
        if start < 0 or not 0 < duration <= 60.1 or start+duration > 14400:
            raise ValueError('Chunk outside supported timeline')
        sources[source].append((float(start), float(start+duration)))
    result = {'scope': 'metadata_only', 'sources': {}}
    for source, intervals in sources.items():
        high = -1.
        out_of_order = 0
        for start, end in intervals:
            if start < high: out_of_order += 1
            high = max(high, start)
        ordered = sorted(intervals)
        covered = gaps = overlap = 0.
        last = None
        for start, end in ordered:
            if last is None:
                covered += end-start
            elif start > last:
                gaps += start-last
                covered += end-start
            else:
                overlap += max(0., min(last, end)-start)
                covered += max(0., end-last)
            last = end if last is None else max(last, end)
        result['sources'][source] = dict(chunks=len(intervals),
            first_start=ordered[0][0] if ordered else None, last_end=last,
            covered_seconds=covered, gap_seconds=gaps, overlap_seconds=overlap,
            out_of_order_chunks=out_of_order)
    return result
