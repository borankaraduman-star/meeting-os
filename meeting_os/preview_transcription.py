"""Opt-in draft transcript while a meeting is still being recorded.

The recorder never waits for this. It hands each closed chunk to `PreviewWorker.offer()` (a `put_nowait` onto a
queue of three); a separate daemon thread reads the closed WAVs, asks an adapter for text and keeps the answer in
`transcript_previews`, a table apart from `segments` — a draft is never a result, a task source or a speaker
identity. What the queue cannot hold stays in `events.jsonl` (the recorder's fsynced chunk journal) and is read
back from there by cursor, so a slow provider costs lag, not memory and not audio.

The contract of one answer is (meeting, source, span, epoch, revision): an older epoch (a connection that was
since replaced) never changes the cache, a revision only replaces a lower one, and a final row is never reopened.
Budgets (cost, audio seconds, disk, backlog, age) pause the preview, never the recording. Without upload
permission no adapter is even constructed. OpenRouter is not assumed to stream: the first adapter sends the
already-closed 12 s chunk through the same one-shot call the final pass uses."""
import contextlib
import json
import math
import queue
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

QUEUE_LIMIT = 3                 # file references held in memory; everything else waits in the chunk journal
STOP_GRACE_SECONDS = 5.0        # how long a stop waits for an answer already in flight
FAILURES_BEFORE_PAUSE = 3
STATUSES = ('partial', 'final', 'unknown', 'skipped', 'failed')
DDL = '''
CREATE TABLE IF NOT EXISTS transcript_previews(meeting TEXT NOT NULL, span_id TEXT NOT NULL, source TEXT, epoch INTEGER NOT NULL DEFAULT 1,
  revision INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL, text TEXT NOT NULL DEFAULT '', audio_start REAL, audio_end REAL, reason TEXT,
  updated REAL, PRIMARY KEY(meeting, span_id));
CREATE TABLE IF NOT EXISTS preview_sessions(meeting TEXT PRIMARY KEY, epoch INTEGER NOT NULL DEFAULT 1, cursor INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'running', reason TEXT, offered INTEGER NOT NULL DEFAULT 0, lag_seconds REAL NOT NULL DEFAULT 0,
  spent_cost REAL NOT NULL DEFAULT 0, spent_seconds REAL NOT NULL DEFAULT 0, calls INTEGER NOT NULL DEFAULT 0, model TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS preview_calls(meeting TEXT NOT NULL, span_id TEXT NOT NULL, seq INTEGER NOT NULL, epoch INTEGER NOT NULL,
  state TEXT NOT NULL, started REAL, PRIMARY KEY(meeting, span_id));
'''


class PreviewUnavailable(RuntimeError):
    """The provider could not be reached or refused: the draft for this span is lost, the recording is not."""


@dataclass
class PreviewPolicy:
    max_cost: float = 1.0                # USD, summed from what the provider reports (or the estimate below)
    max_audio_seconds: float = 7200.0    # audio sent to the provider in this recording
    est_cost_per_second: float = 0.0001  # used only when the provider reports no cost
    min_free_bytes: int = 2 * 1024 ** 3  # below this the preview stops adding disk pressure
    max_backlog_chunks: int = 30         # chunks waiting behind the worker; lag grows past this only as a pause
    max_age_seconds: float = 900.0       # a chunk this old is no longer a live draft


def connect(path):
    conn = sqlite3.connect(str(path), timeout=5, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=5000')
    conn.executescript(DDL)
    return conn


def span_id(event):
    return f"{event.get('source')}:{float(event.get('start') or 0):.3f}"


def apply_preview(conn, meeting, *, source, span, epoch, revision, status, text='', audio_start=None, audio_end=None,
                  reason=None, cursor=None, spend=None, call_state=None):
    """One answer into the cache, atomically with the cursor move and the spend. True when the row changed.

    Rejected (False, but the cursor and spend still land, because the span was handled): an epoch older than the
    session's, a revision not newer than the stored one, anything after a final."""
    if status not in STATUSES: raise ValueError('Bilinmeyen önizleme durumu')
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('INSERT OR IGNORE INTO preview_sessions(meeting) VALUES(?)', (meeting,))
        session_epoch = conn.execute('SELECT epoch FROM preview_sessions WHERE meeting=?', (meeting,)).fetchone()[0]
        applied = False
        if epoch >= session_epoch:
            row = conn.execute('SELECT epoch,revision,status FROM transcript_previews WHERE meeting=? AND span_id=?', (meeting, span)).fetchone()
            if row is None or (row['status'] != 'final' and (epoch, revision) > (row['epoch'], row['revision'])):
                conn.execute('INSERT OR REPLACE INTO transcript_previews(meeting,span_id,source,epoch,revision,status,text,audio_start,audio_end,reason,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (meeting, span, source, epoch, revision, status, text, audio_start, audio_end, reason, time.time()))
                applied = True
        if cursor is not None: conn.execute('UPDATE preview_sessions SET cursor=MAX(cursor,?) WHERE meeting=?', (cursor, meeting))
        if spend: conn.execute('UPDATE preview_sessions SET spent_cost=spent_cost+?,spent_seconds=spent_seconds+?,calls=calls+1 WHERE meeting=?', (spend[0], spend[1], meeting))
        if call_state: conn.execute('UPDATE preview_calls SET state=? WHERE meeting=? AND span_id=?', (call_state, meeting, span))
        conn.execute('COMMIT')
        return applied
    except BaseException:
        with contextlib.suppress(sqlite3.Error): conn.execute('ROLLBACK')
        raise


def session_status(conn, meeting):
    row = conn.execute('SELECT * FROM preview_sessions WHERE meeting=?', (meeting,)).fetchone()
    return dict(row) if row else None


def previews(conn, meeting):
    return [dict(r) for r in conn.execute('SELECT * FROM transcript_previews WHERE meeting=? ORDER BY audio_start,span_id', (meeting,))]


def _age(event):
    """Seconds since the helper wrote this chunk line (its own `wall` stamp), so a chunk read back from the
    journal is dated the same as one that came through the queue, and nothing per chunk is kept in memory."""
    wall = event.get('wall')
    if type(wall) not in (int, float) or not math.isfinite(wall): return None
    return max(0.0, time.time() - float(wall))


class PreviewWorker:
    """`adapter_factory()` → object with `transcribe(path, source, start, end, cancel) -> {'text', 'status'?, 'revision'?, 'usage'?}`.
    It is called lazily, on the worker thread, and never when `upload_allowed` is False."""

    def __init__(self, db_path, meeting, capture_dir, adapter_factory, *, upload_allowed=False, policy=None, model=None, mic_windows=None, session=None):
        self.db_path = Path(db_path); self.meeting = meeting; self.capture_dir = Path(capture_dir); self.session = session
        self.adapter_factory = adapter_factory; self.upload_allowed = upload_allowed is True
        self.policy = policy or PreviewPolicy(); self._mic_windows = mic_windows or self._journal_windows
        self._queue = queue.Queue(maxsize=QUEUE_LIMIT); self._lock = threading.Lock()
        self._cancel = threading.Event(); self._stop = threading.Event(); self._closed = False
        self._thread = None; self._adapter = None; self._failures = 0
        # Memory stays bounded however long the meeting runs: no list of chunks, no set of span ids, no arrival
        # map. The journal is read back through `_scan` (a byte offset and an index) one line at a time, and
        # duplicate or late lines are recognised by a per-source high-water mark instead of a growing set.
        self._scan = self._fresh_scan(); self._last_read = None
        with contextlib.closing(connect(self.db_path)) as c:
            c.execute('INSERT OR IGNORE INTO preview_sessions(meeting) VALUES(?)', (meeting,))
            c.execute('UPDATE preview_sessions SET model=?,updated=? WHERE meeting=?', (model, time.time(), meeting))
            known = self._fresh_scan()
            for _ in self._read_journal(known): pass   # what is already on disk counts as offered
            self._live = {'top': known['top'], 'high': dict(known['high'])}; self._offered = known['index']
            self._cursor = c.execute('SELECT cursor FROM preview_sessions WHERE meeting=?', (meeting,)).fetchone()[0]
            if not self.upload_allowed: self._set(c, 'disabled', 'upload_not_allowed')
            elif c.execute('SELECT state FROM preview_sessions WHERE meeting=?', (meeting,)).fetchone()[0] in ('stopped', 'disabled'): self._set(c, 'running')   # a new worker resumes by cursor

    # ---- recorder side: nothing here may block or raise into the capture loop -------------------------------
    def offer(self, event):
        """Called from the recording loop for every closed chunk. Never waits, never touches the network or disk."""
        if not isinstance(event, dict) or event.get('event') != 'chunk' or not event.get('path'): return False
        with self._lock:
            if self._closed or not self._accept(event, self._live): return False
            seq = self._offered; self._offered += 1
        try: self._queue.put_nowait((seq, dict(event)))
        except queue.Full: pass   # the journal has it; the worker reads it back by cursor
        return True

    def queue_depth(self): return self._queue.qsize()

    def start(self):
        if not self.upload_allowed or self._thread is not None: return self
        self._recover()
        self._thread = threading.Thread(target=self._run, name='preview-transcription', daemon=True)
        self._thread.start()
        return self

    def status(self):
        with contextlib.closing(connect(self.db_path)) as c: row = session_status(c, self.meeting) or {}
        with self._lock:
            row.update(offered=self._offered, queue_depth=self._queue.qsize(), lag_chunks=max(0, self._offered - self._cursor),
                       upload_allowed=self.upload_allowed)
        return row

    def reconnect(self):
        """A new connection to the provider: answers from the old one can no longer change the cache."""
        with contextlib.closing(connect(self.db_path)) as c:
            c.execute('UPDATE preview_sessions SET epoch=epoch+1,updated=? WHERE meeting=?', (time.time(), self.meeting))
            return c.execute('SELECT epoch FROM preview_sessions WHERE meeting=?', (self.meeting,)).fetchone()[0]

    def cancel(self):
        self._cancel.set(); self._stop.set()
        with contextlib.closing(connect(self.db_path)) as c: self._set(c, 'canceled', 'user')

    def stop(self, grace=STOP_GRACE_SECONDS):
        """Wait at most `grace` for the answer in flight, then cancel and return; True when the worker ended cleanly."""
        began = time.monotonic(); self._stop.set()
        thread = self._thread
        if thread is not None: thread.join(max(0.0, grace))
        clean = thread is None or not thread.is_alive()
        if not clean: self._cancel.set()
        with self._lock: self._closed = True
        with contextlib.closing(connect(self.db_path)) as c:
            row = session_status(c, self.meeting)
            if row and row['state'] == 'running': self._set(c, 'stopped', None if clean else 'grace_exceeded')
        self.elapsed = time.monotonic() - began
        return clean

    # ---- worker side ------------------------------------------------------------------------------------------
    def _set(self, c, state, reason=None):
        c.execute('UPDATE preview_sessions SET state=?,reason=?,updated=? WHERE meeting=?', (state, reason, time.time(), self.meeting))

    def _eligible(self, event, top):
        """(take it, highest launch so far). Another session's chunk is not this meeting's audio, and a replaced
        helper's chunk that arrives after the new helper's is a late line (docs/CANLI_DURUM_ONIZLEME_NOTLAR.md A):
        neither gets a draft. The final pass still reads every file on disk. offer() and the journal read-back apply
        this to the same ordered lines, so the sequence number and the journal index keep meaning the same chunk."""
        other, number = event.get('session'), event.get('launch')
        if self.session and isinstance(other, str) and other != self.session: return False, top
        if type(number) is not int: return True, top   # a schema 1 helper stamps nothing
        if top is not None and number < top: return False, top
        return True, number if top is None else max(top, number)

    @staticmethod
    def _fresh_scan():
        return {'offset': 0, 'index': 0, 'top': None, 'high': {}}

    def _accept(self, event, state):
        """The one rule offer() and the journal read-back share, so a sequence number and a journal index keep
        naming the same chunk. Chunks of one source are written in time order (a relaunch continues at the last
        end), so a start at or below that source's high-water mark is a duplicate or a late line."""
        if not isinstance(event, dict) or event.get('event') != 'chunk' or not event.get('path'): return False
        eligible, state['top'] = self._eligible(event, state['top'])
        if not eligible: return False
        source = str(event.get('source')); start = float(event.get('start') or 0)
        high = state['high'].get(source)
        if high is not None and start <= high: return False
        state['high'][source] = start
        return True

    def _read_journal(self, state):
        """Accepted chunk lines from `state['offset']` on, one at a time; the state moves with them. A last line
        without its newline is still being written (or was cut by a crash) and is left for the next read."""
        try: f = (self.capture_dir / 'events.jsonl').open('rb')
        except OSError: return
        with f:
            f.seek(state['offset'])
            for raw in f:
                if not raw.endswith(b'\n'): return
                state['offset'] += len(raw)
                try: event = json.loads(raw.decode('utf-8', errors='replace'))
                except ValueError: continue
                if self._accept(event, state):
                    state['index'] += 1
                    yield state['index'] - 1, event

    def _journal_at(self, index):
        """Chunk number `index` of the journal, or None when it is not there yet. Holds at most the one chunk it
        returned: the cursor only moves forward, so a read normally continues where the last one stopped."""
        if self._last_read is not None and self._last_read[0] == index: return self._last_read[1]
        if index < self._scan['index']: self._scan = self._fresh_scan()   # asked for one already passed: read again from the top
        for i, event in self._read_journal(self._scan):
            if i == index: self._last_read = (i, event); return event
        return None

    def _journal_chunks(self):
        """Every accepted chunk, for diagnostics and tests only — the worker itself reads by `_journal_at`."""
        return [e for _, e in self._read_journal(self._fresh_scan())]

    def _journal_windows(self):
        from .cloud_finalize import mic_gate_windows
        return mic_gate_windows(self.capture_dir, live=True)   # a gate that has only said "off" so far is closed

    def _recover(self):
        """A call recorded as in flight whose answer was never stored: the provider may have billed it. It is
        marked unknown and never repeated; the final pass reads that audio anyway."""
        with contextlib.closing(connect(self.db_path)) as c:
            for row in c.execute('SELECT span_id,seq,epoch FROM preview_calls WHERE meeting=? AND state=?', (self.meeting, 'inflight')).fetchall():
                source = row['span_id'].split(':')[0]
                apply_preview(c, self.meeting, source=source, span=row['span_id'], epoch=row['epoch'], revision=1, status='unknown',
                              reason='interrupted', cursor=row['seq'] + 1, call_state='unknown')
            self._cursor = c.execute('SELECT cursor FROM preview_sessions WHERE meeting=?', (self.meeting,)).fetchone()[0]

    def _run(self):
        while not self._stop.is_set():
            job = self._pull()
            if job is None: continue
            try: self._handle(*job)
            except Exception:
                with contextlib.closing(connect(self.db_path)) as c: self._set(c, 'paused', 'internal')   # never raises into the recorder

    def _pull(self):
        item = None
        try: item = self._queue.get(timeout=.25)
        except queue.Empty: pass
        if item is not None and item[0] < self._cursor: item = None   # already handled
        if item is not None and item[0] == self._cursor: return item
        with self._lock: behind = self._offered > self._cursor
        if behind:
            event = self._journal_at(self._cursor)
            if event is not None: return self._cursor, event
        return item

    def _paused_reason(self, c, seq, event):
        s = session_status(c, self.meeting)
        if s['state'] != 'running': return s['reason'] or s['state']
        p = self.policy
        if s['spent_cost'] >= p.max_cost: return 'cost'
        if s['spent_seconds'] >= p.max_audio_seconds: return 'audio_seconds'
        try:
            if shutil.disk_usage(self.capture_dir).free < p.min_free_bytes: return 'disk'
        except OSError: pass
        with self._lock: backlog = self._offered - seq
        if backlog > p.max_backlog_chunks: return 'backlog'
        age = _age(event)
        if age is not None and age > p.max_age_seconds: return 'age'
        return None

    def _handle(self, seq, event):
        meeting = self.meeting; sid = span_id(event); source = event.get('source')
        start = float(event.get('start') or 0); duration = event.get('duration')
        end = start + float(duration) if type(duration) in (int, float) else start
        with contextlib.closing(connect(self.db_path)) as c:
            with self._lock: offered = self._offered
            lag = _age(event) or 0.0
            c.execute('UPDATE preview_sessions SET offered=?,lag_seconds=?,updated=? WHERE meeting=?', (offered, lag, time.time(), meeting))
            def finish(status, reason=None, **kw):
                epoch = session_status(c, meeting)['epoch']
                apply_preview(c, meeting, source=source, span=sid, epoch=kw.pop('epoch', epoch), revision=1, status=status, reason=reason,
                              audio_start=start, audio_end=end, cursor=seq + 1, **kw)
                self._cursor = max(self._cursor, seq + 1)
            reason = self._paused_reason(c, seq, event)
            if reason:
                if session_status(c, meeting)['state'] == 'running': self._set(c, 'paused', reason)
                self._stop.wait(.25)   # paused: nothing is sent, the journal keeps the rest
                return
            if source == 'mic':
                from .cloud_finalize import MIC_GATE_MIN_OVERLAP, gate_overlap
                windows = self._mic_windows()
                if windows is not None and gate_overlap(windows, start, end) < MIC_GATE_MIN_OVERLAP:
                    return finish('skipped', 'mic_gated')   # never sent; the WAV stays where the final pass will find it
            path = Path(str(event['path']))
            if not path.is_file(): return finish('failed', 'missing_file')
            try:
                if self._adapter is None: self._adapter = self.adapter_factory()
            except Exception:
                self._set(c, 'paused', 'adapter_unavailable'); self._stop.wait(.25); return
            epoch = session_status(c, meeting)['epoch']
            c.execute('INSERT OR REPLACE INTO preview_calls(meeting,span_id,seq,epoch,state,started) VALUES(?,?,?,?,?,?)', (meeting, sid, seq, epoch, 'inflight', time.time()))
            try: answer = self._adapter.transcribe(path, source, start, end, self._cancel)
            except Exception as exc:
                if self._cancel.is_set() or self._closed:
                    c.execute('UPDATE preview_calls SET state=? WHERE meeting=? AND span_id=?', ('canceled', meeting, sid)); return
                self._failures += 1; new_epoch = self.reconnect()   # whatever this connection still delivers is stale now
                if self._failures >= FAILURES_BEFORE_PAUSE: self._set(c, 'paused', 'network')
                return finish('failed', type(exc).__name__, epoch=new_epoch, call_state='failed')
            if self._cancel.is_set() or self._closed:
                c.execute('UPDATE preview_calls SET state=? WHERE meeting=? AND span_id=?', ('canceled', meeting, sid)); return
            self._failures = 0
            usage = answer.get('usage') or {}
            cost = usage.get('cost') if type(usage.get('cost')) in (int, float) and math.isfinite(usage['cost']) else (end - start) * self.policy.est_cost_per_second
            status = answer.get('status') if answer.get('status') in ('partial', 'final') else 'final'
            applied = apply_preview(c, meeting, source=source, span=sid, epoch=epoch, revision=int(answer.get('revision') or 1), status=status,
                                    text=str(answer.get('text') or ''), audio_start=start, audio_end=end, cursor=seq + 1,
                                    spend=(float(cost), end - start), call_state='done')
            self._cursor = max(self._cursor, seq + 1)
            if not applied: c.execute('UPDATE preview_calls SET state=? WHERE meeting=? AND span_id=?', ('stale', meeting, sid))


class OpenRouterPreviewAdapter:
    """The existing one-shot OpenRouter transcription over one closed chunk. Not a stream: a 12 s window per call."""

    def __init__(self, model=None, client=None, ffmpeg=None):
        from .openrouter import OpenRouterClient, STT_MODEL, validate_stt_model
        self.model = model or STT_MODEL; validate_stt_model(self.model)
        self.client = client or OpenRouterClient(); self.ffmpeg = ffmpeg

    def transcribe(self, path, source, start, end, cancel):
        from .cloud_finalize import encode_piece
        if cancel.is_set(): raise PreviewUnavailable('iptal')
        audio = encode_piece(path, 0, max(0.1, end - start), self.ffmpeg)
        try: out = self.client.transcribe(audio, 'ogg', model=self.model, consent=True, language='tr', timeout=30)
        except Exception as exc: raise PreviewUnavailable(str(exc)) from None
        return {'text': out['text'], 'status': 'final', 'usage': out.get('usage')}


def worker_factory(*, cloud_preview=False, allow_upload=False, model=None, db_path=None, policy=None, adapter_factory=None):
    """The record command's hook: None unless the user asked for the preview. Asked for without permission it
    still returns a worker, so the app can show "kapalı" — but that worker never builds an adapter."""
    if not cloud_preview: return None
    def build(capture_dir, meeting, session=None):
        factory = adapter_factory or (lambda: OpenRouterPreviewAdapter(model))
        return PreviewWorker(db_path, meeting, capture_dir, factory, upload_allowed=allow_upload, policy=policy, model=model, session=session).start()
    return build
