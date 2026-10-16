"""Bounded metadata-only timeline metrics. No audio quality or queue inference."""
import collections
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


MARK_EVENTS = ('first_buffer', 'channel_flow')
OTHER_LINES_KEPT = 2048   # lifecycle lines (started, permission, error, stopped, relaunch, gap, …): a handful per meeting


class _StateReducer:
    """The whole journal folded into what the session state can still change on, in bounded memory. The
    64 KB tail lost a channel's `first_buffer` after roughly half an hour of chunk lines (a steady signal or a
    steady silence writes no further transitions), and the channel read 'awaiting_first_buffer' while it was
    recording. Kept, in journal order: every lifecycle line (capped), the newest evidence line per
    (session, launch, source, epoch) and the newest chunk per (session, launch, source). Everything
    `session_view` and `desktop.capture_state` derive from that is identical to reading every line."""
    def __init__(self):
        self.offset = 0; self.position = 0; self.identity = None; self.seam = b''
        self.marks = {}; self.chunks = {}; self.other = collections.deque(maxlen=OTHER_LINES_KEPT)

    def add(self, event):
        self.position += 1; kind = event.get('event'); n = self.position
        if kind == 'chunk':
            # The newest line (order against error/stopped, freshest wall) and the furthest-reaching one (coverage:
            # mic and system lines may be journaled out of order) — often the same line, then kept once.
            key = (event.get('session'), event.get('launch'), event.get('source'))
            reach = _chunk_end(event); held = self.chunks.get(key)
            furthest = (n, event) if held is None or reach >= _chunk_end(held[1][1]) else held[1]
            self.chunks[key] = ((n, event), furthest)
        elif kind in MARK_EVENTS:
            # The epoch's `first_buffer` is kept beside its newest flow line: a later `stalled` must not erase the
            # only proof that this channel ever delivered a buffer (session_view tells "stalled" from "never came").
            key = (event.get('session'), event.get('launch'), event.get('source'), event.get('epoch'), kind == 'first_buffer')
            seq = _int(event.get('seq')); rank = (seq if seq is not None else -1, n)
            held = self.marks.get(key)
            if held is None or rank >= held[0]: self.marks[key] = (rank, n, event)
        else: self.other.append((n, event))

    def events(self):
        kept = list(self.other) + [(n, e) for _, n, e in self.marks.values()]
        for newest, furthest in self.chunks.values(): kept += [newest] if newest[0] == furthest[0] else [furthest, newest]
        return [e for _, e in sorted(kept, key=lambda pair: pair[0])]


def _chunk_end(event):
    start, duration = event.get('start'), event.get('duration')
    if type(start) not in (int, float) or not math.isfinite(start): return -math.inf
    return float(start) + (float(duration) if type(duration) in (int, float) and math.isfinite(duration) else 0.0)


_REDUCERS = {}   # path → reducer; a long-lived process (the app's bridge) reads only the bytes added since its last poll
_REDUCERS_KEPT = 8


def journal_state_events(path):
    """The events `session_view` needs, from the WHOLE journal however long the meeting runs. Incremental: a
    poll reads only what was appended since the previous one; a replaced, truncated or rewritten file (the bytes
    before the saved offset no longer match) starts over. A last line without its newline is still being
    written and waits for the next poll."""
    key = str(path)
    try:
        st = os.stat(path)
        f = open(path, 'rb')
    except OSError: return []
    with f:
        identity = (st.st_dev, st.st_ino)
        reducer = _REDUCERS.get(key)
        if reducer is not None and (reducer.identity != identity or st.st_size < reducer.offset): reducer = None
        if reducer is not None and reducer.seam:
            f.seek(reducer.offset - len(reducer.seam))
            if f.read(len(reducer.seam)) != reducer.seam: reducer = None
        if reducer is None: reducer = _StateReducer(); reducer.identity = identity
        f.seek(reducer.offset); tail = None
        for raw in f:
            if not raw.endswith(b'\n'):
                # Not folded in (the rest of it may still arrive), but a complete JSON line without its newline
                # is read for this answer, as the tail reader always did; a cut-off line simply fails to parse.
                try: tail = json.loads(raw.decode('utf-8', errors='replace'))
                except ValueError: tail = None
                break
            reducer.offset += len(raw); reducer.seam = raw[-64:]
            try: event = json.loads(raw.decode('utf-8', errors='replace'))
            except ValueError: continue
            if isinstance(event, dict): reducer.add(event)
    _REDUCERS.pop(key, None); _REDUCERS[key] = reducer
    while len(_REDUCERS) > _REDUCERS_KEPT: _REDUCERS.pop(next(iter(_REDUCERS)))
    return reducer.events() + ([tail] if isinstance(tail, dict) else [])


COUNTER_MARKERS = ('restarted', 'relaunch', 'wake', 'gap', 'error')   # substrings that make a line worth parsing


def _blank_health():
    return {'restarts': 0, 'relaunches': 0, 'wakes': 0, 'gap_seconds': 0.0, 'wake_gap_seconds': 0.0, 'capture_errors': 0}


def _foreign(event, session):
    """A line another recording session wrote. Lines without a session are the supervisor's own notes or an old
    (schema 1) helper's, and always belong to the meeting being read."""
    other = event.get('session')
    return session is not None and isinstance(other, str) and other != session


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


def capture_health(events, session=None):
    """What the owner asks about after a meeting: how often the audio stream was rebuilt, how often the
    supervisor had to replace the whole helper, how many times the Mac woke, and how many seconds were lost.
    Sleep costs wall-clock seconds that never reach the audio timeline, so they are counted separately from
    the chunk discontinuities the helper writes as 'gap'."""
    out = _blank_health()
    for event in events:
        if not _foreign(event, session): _count(out, event)
    return _rounded(out)


def journal_counters(path, session=None):
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
                if isinstance(event, dict) and not _foreign(event, session): _count(out, event)
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


# Recording session state (schema 2 helper). The helper writes `started` right after startCapture returns, which
# proves nothing about audio: only a `first_buffer` line — the first valid PCM of one source in one stream epoch —
# does. Everything here reads metadata lines only; no audio and no transcript text is ever opened or logged.
CHANNEL_SOURCES = ('mic', 'system')
PERMISSION_MESSAGES = {
    'microphone': "Mikrofon izni verilmedi; Sistem Ayarları › Gizlilik ve Güvenlik › Mikrofon bölümünden Meeting OS'a izin verin.",
    'screen_audio': "Ekran ve sistem sesi kaydı izni verilmedi; Sistem Ayarları › Gizlilik ve Güvenlik › Ekran ve Sistem Sesi Kaydı bölümünden Meeting OS'a izin verin.",
}
CAPTURE_FAILED_MESSAGE = 'Kayıt yardımcısı ses akışını başlatamadı; ses kaydı alınamadı.'
CHANNEL_ERROR_MESSAGE = {'mic': 'Mikrofon kanalı başlatılamadı.', 'system': 'Sistem sesi kanalı başlatılamadı.'}


def _int(value):
    return value if type(value) is int else None


def _wall(event):
    wall = event.get('wall')
    return float(wall) if type(wall) in (int, float) and math.isfinite(wall) else None


def current_session(events):
    """(schema, session, launch) of the recording the journal is about now. The session is the one named by the
    newest lifecycle line (`started` or `permission`) — a relaunch keeps the session and raises the launch, so the
    launch is the highest one that session has written. A journal no line of which names a session is schema 1."""
    session = None
    for event in events:
        if event.get('event') in ('started', 'permission') and isinstance(event.get('session'), str): session = event['session']
    if session is None:
        for event in events:
            if isinstance(event.get('session'), str): session = event['session']
    if session is None: return 1, None, None
    launches = [_int(e.get('launch')) for e in events if e.get('session') == session]
    launches = [n for n in launches if n is not None]
    schema = max([_int(e.get('schema')) or 2 for e in events if e.get('session') == session and e.get('event') == 'started'], default=2)
    return schema, session, max(launches, default=None)


def belongs(event, session, launch):
    """True for a line of the current session and launch. A late line of a replaced helper (older launch) or of
    another session never moves the state; supervisor lines carry no session and always count."""
    if session is None: return True
    if _foreign(event, session): return False
    own = _int(event.get('launch'))
    return launch is None or own is None or own >= launch


def session_view(events, now=None):
    """schema, session, session_state and per-channel state from the journal tail. Schema 1 journals cannot say
    whether a buffer ever arrived, so their channels are 'unverified' and their session state comes from the
    old started/chunk/stopped lines alone."""
    import time
    now = time.time() if now is None else now
    schema, session, launch = current_session(events)
    if session is None:
        state = 'awaiting_stream'
        for event in events:
            kind = event.get('event')
            if kind == 'chunk': state = 'receiving'
            elif kind == 'error': state = 'failed'
            elif kind == 'stopped': state = 'stopped' if state != 'failed' else state
        return {'schema': 1, 'session': None, 'session_state': state,
                'channels': {s: {'state': 'unverified', 'epoch': None, 'age_seconds': None} for s in CHANNEL_SOURCES}}
    own = [e for e in events if belongs(e, session, launch)]
    epoch, epoch_wall = 0, None
    for event in own:
        value = _int(event.get('epoch'))
        if event.get('event') in ('started', 'restarted') and value is not None and value >= epoch:
            epoch = value; epoch_wall = _wall(event) or epoch_wall
        elif event.get('event') in ('first_buffer', 'channel_flow') and value is not None and value > epoch:
            epoch = value   # the restarted line fell out of the tail; the newer epoch still wins
    channels, errors = {}, {}
    for source in CHANNEL_SOURCES:
        # Ordered by (epoch, seq), not by line position: mic and system arrive on their own queues and may be
        # journaled out of order; a stale epoch's line never overrides the current one.
        marks = [(i, e) for i, e in enumerate(own) if e.get('source') == source and e.get('event') in ('first_buffer', 'channel_flow') and _int(e.get('epoch')) == epoch]
        marks.sort(key=lambda m: (_int(m[1].get('seq')) if _int(m[1].get('seq')) is not None else -1, m[0]))
        walls = [_wall(e) for e in own if e.get('source') == source and e.get('event') in ('first_buffer', 'channel_flow', 'chunk')]
        walls = [w for w in walls if w is not None]
        # The helper's stall timer runs from the stream's set-up, so a `stalled` line can arrive before any buffer
        # (seq carries over from the previous epoch, so it proves nothing either). Only a first_buffer or a
        # signal/silent flow line of THIS epoch says audio arrived; without one the channel is still waiting.
        if any(e.get('event') == 'first_buffer' or e.get('state') in ('signal', 'silent') for _, e in marks):
            last = marks[-1][1]
            state = ('silent' if last.get('silent') is True else 'signal') if last.get('event') == 'first_buffer' else last.get('state')
            if state not in ('signal', 'silent', 'stalled'): state = 'signal'
            # For a channel that is flowing, age is the time since its newest evidence line.
            age = round(max(0.0, now - max(walls)), 1) if walls else None
        else:
            state = 'awaiting_first_buffer'
            # Waiting: seconds since this epoch's stream was set up, so the app can warn (never fail) after 5 s.
            age = round(max(0.0, now - epoch_wall), 1) if epoch_wall is not None else None
        channels[source] = {'state': state, 'epoch': epoch, 'age_seconds': age}
    permissions, started, failed, stopped, chunks = {}, False, None, False, False
    for event in own:
        kind = event.get('event')
        if kind == 'permission' and event.get('kind') in PERMISSION_MESSAGES: permissions[event['kind']] = event.get('state')
        elif kind in ('started', 'restarted'): started = True; failed = None if kind == 'started' else failed
        elif kind == 'chunk': chunks = True
        elif kind == 'stopped': stopped = True
        elif kind == 'error':
            source = event.get('source')
            # One channel failing to start is that channel's problem; the other one may be recording fine.
            if source in CHANNEL_SOURCES: errors[source] = CHANNEL_ERROR_MESSAGE[source]
            else: failed = CAPTURE_FAILED_MESSAGE
    for source, message in errors.items(): channels[source]['error'] = message
    denied = [kind for kind, value in permissions.items() if value == 'denied']
    receiving = chunks or any(c['state'] != 'awaiting_first_buffer' for c in channels.values())
    message = None
    if denied: state, message = 'failed', PERMISSION_MESSAGES[denied[0]]
    elif failed: state, message = 'failed', failed
    elif stopped: state = 'stopped'
    elif any(value == 'requested' for value in permissions.values()) and not receiving: state = 'awaiting_permission'   # no start timeout while macOS asks
    elif started and receiving: state = 'receiving'
    else: state = 'awaiting_stream'
    view = {'schema': schema, 'session': session, 'session_state': state, 'channels': channels}
    if message: view['message'] = message
    # The app names a denied permission itself (CaptureSessionState.deniedPermission) and dates its five-second
    # first-buffer warning from the stream's own set-up, not from the poll that first saw it.
    if permissions: view['permission'] = dict(permissions)
    if epoch_wall is not None: view['stream_age_seconds'] = round(max(0.0, now - epoch_wall), 1)
    return view
