"""SQLite speaker memory. Only explicit enrollment changes voice profiles."""
import json
import math
import sqlite3
import unicodedata
import uuid
from pathlib import Path
from datetime import datetime, timezone

def fold_name(value):
    """Comparison key for a person's name, Turkish-aware. 'Ayse', 'ayşe' and 'AYŞE' are one person: typing the
    suggestion back without its diacritics is a confirmation, not "this voice is not Ayşe". Diacritics are
    dropped for comparison only — what is stored and shown is always exactly what the user typed."""
    s = (value or '').replace('İ', 'i').replace('I', 'ı').casefold()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return s.replace('ı', 'i').strip()

def unit(vector):
    values = [float(v) for v in vector]
    norm = math.sqrt(sum(v*v for v in values))
    if not values or not math.isfinite(norm) or norm < 1e-8:
        raise ValueError('Invalid voice embedding')
    return [v/norm for v in values]

def cosine(a, b):
    if len(a) != len(b): return -1.0
    return sum(x*y for x, y in zip(a, b))

class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        self.db = sqlite3.connect(path)
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA busy_timeout=5000')   # the 2 s poll and a job open the same file; wait instead of failing
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA secure_delete=ON')   # deleted transcript pages are zeroed, not left in free space
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS meetings(id TEXT PRIMARY KEY, title TEXT, created TEXT, status TEXT, metadata TEXT);
        CREATE TABLE IF NOT EXISTS segments(id INTEGER PRIMARY KEY, meeting TEXT REFERENCES meetings(id), start REAL, end REAL, source TEXT, speaker TEXT, speaker_name TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, name TEXT, model TEXT, vector TEXT, duration REAL, provenance TEXT);
        CREATE TABLE IF NOT EXISTS corrections(id INTEGER PRIMARY KEY, meeting TEXT, speaker TEXT, name TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS text_edits(id INTEGER PRIMARY KEY, meeting TEXT, segment INTEGER, previous TEXT, replacement TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS rejections(id INTEGER PRIMARY KEY, name TEXT, model TEXT, vector TEXT, provenance TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS profile_stats(name TEXT PRIMARY KEY, confirmed INTEGER DEFAULT 0, wrong INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS segment_meeting ON segments(meeting,start);
        ''')
        # Samples a naming rejected are hidden, not destroyed: undo has to be able to give them back.
        if 'deleted_by' not in {r[1] for r in self.db.execute('PRAGMA table_info(samples)')}:
            try: self.db.execute('ALTER TABLE samples ADD COLUMN deleted_by TEXT')
            except sqlite3.OperationalError: pass   # another process migrated first
        columns={r[1] for r in self.db.execute('PRAGMA table_info(corrections)')}
        if 'previous_name' not in columns:
            try: self.db.execute('ALTER TABLE corrections ADD COLUMN previous_name TEXT')
            except sqlite3.OperationalError: pass
        if 'feedback' not in columns:
            # New column, so exactly once per database: the corrections the user already made are the evidence
            # Q5 needs, and the segments still carry the automatic verdict those corrections overruled.
            try: self.db.execute('ALTER TABLE corrections ADD COLUMN feedback TEXT'); self._backfill_feedback()
            except sqlite3.OperationalError: pass   # the poll and a job opened the file together; the other one migrated
    def close(self): self.db.close()
    def create_meeting(self, title, metadata=None):
        mid = uuid.uuid4().hex[:12]
        with self.db:
            self.db.execute('INSERT INTO meetings VALUES(?,?,?,?,?)', (mid, title, datetime.now(timezone.utc).isoformat(), 'processing', json.dumps(metadata or {})))
        return mid
    def status(self, mid, status):
        with self.db: self.db.execute('UPDATE meetings SET status=? WHERE id=?', (status, mid))
    def meetings(self): return [dict(r) for r in self.db.execute('SELECT * FROM meetings ORDER BY created DESC')]
    def add_segment(self, mid, segment):
        d = segment.to_dict()
        with self.db:
            cur = self.db.execute('INSERT INTO segments(meeting,start,end,source,speaker,speaker_name,payload) VALUES(?,?,?,?,?,?,?)',
                (mid, d['start'], d['end'], d['source'], d['speaker'], d['speaker_name'], json.dumps(d, ensure_ascii=False)))
        return cur.lastrowid
    def segments(self, mid):
        result = []
        for r in self.db.execute("SELECT * FROM segments WHERE meeting=? ORDER BY CASE WHEN source='chatgpt_manual' THEN id ELSE start END,id", (mid,)):
            d = json.loads(r['payload'])
            d.update(id=r['id'], speaker_name=r['speaker_name'])
            result.append(d)
        return result
    def display_segments(self, mid):
        # Keep 256-dimensional voice vectors out of every UI polling response.
        rows=self.db.execute("SELECT id,start,end,source,speaker,speaker_name,json_extract(payload,'$.text') AS text,json_extract(payload,'$.flags') AS flags,json_extract(payload,'$.metrics.identity.suggested') AS suggested FROM segments WHERE meeting=? ORDER BY CASE WHEN source='chatgpt_manual' THEN id ELSE start END,id",(mid,))
        return [{**dict(r),'flags':json.loads(r['flags'] or '[]')} for r in rows]
    def correct(self, mid, speaker, name):
        name = name.strip()
        if not name: raise ValueError('Name cannot be empty')
        rows=[r for r in self.segments(mid) if r['speaker']==speaker]
        if not rows: raise ValueError('Speaker not found in meeting')
        created=datetime.now(timezone.utc).isoformat()
        with self.db:
            previous=self._reject_previous(mid, speaker, rows, name, created)
            feedback=self._record_feedback(rows, name)
            self.db.execute('UPDATE segments SET speaker_name=? WHERE meeting=? AND speaker=?', (name, mid, speaker))
            self.db.execute('INSERT INTO corrections(meeting,speaker,name,created,previous_name,feedback) VALUES(?,?,?,?,?,?)', (mid, speaker, name, created, previous, feedback))
    @staticmethod
    def naming_mark(mid, speaker, created=''):
        return f'{mid}:speaker:{speaker}'+(f'@{created}' if created else '')
    REJECT_SIMILARITY = 0.90   # a voice this close to one the user said is "not X" can never be X again
    def _previous_names(self, rows):
        """What the app called this cluster before the user corrected it: a confirmed name, an automatic match or an unconfirmed suggestion."""
        names=[]
        for r in rows:
            identity=(r.get('metrics') or {}).get('identity') or {}
            for n in (r.get('speaker_name'), identity.get('name'), identity.get('suggested')):
                if n and n not in names: names.append(n)
        return names
    def _cluster_vector(self, rows):
        voiced=[r for r in rows if r.get('embedding') and 'speaker_ambiguous' not in r['flags']]
        model=voiced[0]['embedding_model'] if voiced else None
        vectors=[unit(r['embedding']) for r in voiced if r['embedding_model']==model]
        if not vectors: return None, None
        try: return unit([sum(col)/len(vectors) for col in zip(*vectors)]), model
        except ValueError: return None, None
    def _reject_previous(self, mid, speaker, rows, name, created=''):
        """Negative feedback (must run inside the caller's transaction): renaming a cluster away from a person
        hides the samples that cluster fed into that person and remembers the voice as rejected for them.
        Names are compared folded, so writing "Ayse" over the suggestion "Ayşe" confirms the person rather
        than convicting them; the samples are soft-deleted so undo can hand them back intact."""
        wrong=[n for n in self._previous_names(rows) if fold_name(n)!=fold_name(name)]
        if not wrong: return None
        clusters={(r.get('metrics') or {}).get('cluster') for r in rows} - {None}
        provenances=[f'auto:{mid}:{c}' for c in clusters]+[f'{mid}:speaker:{speaker}']
        vector,model=self._cluster_vector(rows)
        mark=self.naming_mark(mid, speaker, created)   # unique per naming: undoing the second naming must not unwind the first
        for prev in wrong:
            self.db.executemany('UPDATE samples SET deleted_by=? WHERE name=? AND provenance=? AND deleted_by IS NULL',[(mark,prev,p) for p in provenances])
            if vector is not None and not self.db.execute('SELECT 1 FROM rejections WHERE name=? AND provenance LIKE ?',(prev,f'{mid}:speaker:{speaker}%')).fetchone():
                self.db.execute('INSERT INTO rejections(name,model,vector,provenance,created) VALUES(?,?,?,?,?)',(prev,model,json.dumps(vector),mark,created or datetime.now(timezone.utc).isoformat()))
        return wrong[0]
    # --- Q5: per-person evidence. Only automation is judged here; a name the user typed into an empty cluster says
    # nothing about the model, so it moves no counter. One overruled automatic name outweighs one confirmed suggestion.
    PERSON_THRESHOLD_FLOOR=0.84   # 3 profiles of real data still separate different people at 0.85; never go under
    PERSON_THRESHOLD_CAP=0.93
    def _feedback(self, identities, name):
        """(confirmed, wrong) for one naming: the suggestion the user accepted, and the automatic name he overruled."""
        key=fold_name(name)   # folding only decides what is NOT a rejection; a confirmation must be the exact suggested spelling
        confirmed=next((i['suggested'] for i in identities if i and i.get('suggested')==name),None)
        wrong=sorted({(i or {}).get('name') for i in identities if (i or {}).get('name') and fold_name(i['name'])!=key})
        return confirmed,(wrong[0] if wrong else None)
    def _bump(self, name, column, delta):
        """Move one evidence counter (must run inside the caller's transaction). Counters never go negative."""
        self.db.execute('INSERT OR IGNORE INTO profile_stats(name,confirmed,wrong) VALUES(?,0,0)',(name,))
        self.db.execute(f'UPDATE profile_stats SET {column}=max(0,{column}+?) WHERE name=?',(delta,name))
    def _record_feedback(self, rows, name):
        """Apply this naming's evidence and return the JSON the correction row keeps, so undo can take it back."""
        confirmed,wrong=self._feedback([(r.get('metrics') or {}).get('identity') for r in rows], name)
        if not confirmed and not wrong: return None
        if confirmed: self._bump(confirmed,'confirmed',1)
        if wrong: self._bump(wrong,'wrong',1)
        return json.dumps({'confirmed':confirmed,'wrong':wrong})
    def _backfill_feedback(self):
        """Migration only: replay the existing cluster corrections into the counters, cheaply (no vectors read)."""
        with self.db:
            for row in self.db.execute("SELECT id,meeting,speaker,name FROM corrections WHERE speaker NOT LIKE 'segment:%' ORDER BY id"):
                identities=[{'name':r[0],'suggested':r[1]} for r in self.db.execute(
                    "SELECT json_extract(payload,'$.metrics.identity.name'),json_extract(payload,'$.metrics.identity.suggested') FROM segments WHERE meeting=? AND speaker=?",(row['meeting'],row['speaker']))]
                confirmed,wrong=self._feedback(identities,row['name'])
                if not confirmed and not wrong: continue
                self.db.execute('UPDATE corrections SET feedback=? WHERE id=?',(json.dumps({'confirmed':confirmed,'wrong':wrong}),row['id']))
                if confirmed: self._bump(confirmed,'confirmed',1)
                if wrong: self._bump(wrong,'wrong',1)
    def person_threshold(self, name, base, exclude=None):
        """The bar this one person has to clear. Each confirmed suggestion lowers it 0.01 (floor 0.84), each
        overruled automatic name raises it 0.02 (cap 0.93); people the user never judged keep the global bar.
        `exclude` drops one meeting's own evidence, so a replay cannot let a meeting vouch for itself."""
        row=self.db.execute('SELECT confirmed,wrong FROM profile_stats WHERE name=?',(name,)).fetchone()
        confirmed,wrong=(row['confirmed'] or 0,row['wrong'] or 0) if row else (0,0)
        if exclude:
            for r in self.db.execute('SELECT feedback FROM corrections WHERE meeting=? AND feedback IS NOT NULL',(exclude,)):
                try: f=json.loads(r['feedback'])
                except ValueError: continue
                if f.get('confirmed')==name: confirmed-=1
                if f.get('wrong')==name: wrong-=1
        confirmed=max(0,min(confirmed,3));wrong=max(0,min(wrong,3))
        if not confirmed and not wrong: return base
        # The floor may never push the bar up: on the local paths base is 0.80, and clamping to 0.84 made a
        # person the user had *confirmed* harder to match than one he had never judged. Only `wrong` raises.
        floor=min(base,self.PERSON_THRESHOLD_FLOOR)
        return min(self.PERSON_THRESHOLD_CAP, max(base-0.01*confirmed, floor)+0.02*wrong)
    def correct_segment(self, mid, sid, name):
        name = name.strip()
        if not name: raise ValueError('Name cannot be empty')
        with self.db:
            cur = self.db.execute('UPDATE segments SET speaker_name=? WHERE meeting=? AND id=?', (name, mid, sid))
            if not cur.rowcount: raise ValueError('Segment not found in meeting')
            self.db.execute('INSERT INTO corrections(meeting,speaker,name,created) VALUES(?,?,?,?)', (mid, f'segment:{sid}', name, datetime.now(timezone.utc).isoformat()))
    def enroll(self, name, vector, model, duration, provenance='manual'):
        if not name.strip() or not math.isfinite(duration) or duration < 3: raise ValueError('Enrollment needs named, clean speech >=3 seconds')
        vector = unit(vector)
        with self.db:
            self.db.execute('INSERT INTO samples(name,model,vector,duration,provenance) VALUES(?,?,?,?,?)', (name.strip(), model, json.dumps(vector), duration, provenance))
    def correct_text(self, mid, sid, text):
        text=text.strip()
        if not text: raise ValueError('Transcript text cannot be empty')
        row=self.db.execute('SELECT payload FROM segments WHERE meeting=? AND id=?',(mid,sid)).fetchone()
        if not row: raise ValueError('Segment not found')
        payload=json.loads(row['payload']); previous=payload['text']
        payload.setdefault('original_text',previous);payload['text']=text;payload['edited']=True
        with self.db:
            self.db.execute('UPDATE segments SET payload=? WHERE meeting=? AND id=?',(json.dumps(payload,ensure_ascii=False),mid,sid))
            self.db.execute('INSERT INTO text_edits(meeting,segment,previous,replacement,created) VALUES(?,?,?,?,?)',(mid,sid,previous,text,datetime.now(timezone.utc).isoformat()))
    UNCLEAN_FLAGS={'speaker_ambiguous','possible_non_speech','repetition','provisional','low_asr_confidence','short_context_diarization'}
    CLEAN_MIN_SECONDS=6.0   # the picker asks for more than enrollment's bare minimum: a long turn makes a better sample
    def clean_candidates(self, name, limit=8):
        """Q8: this person's longest turns that could become a voice sample — long enough, no uncertainty flag, a
        vector already stored, and not already enrolled. Vectors stay in SQLite; only the row summary comes back."""
        name=(name or '').strip()
        if not name: return []
        used={r[0] for r in self.db.execute('SELECT provenance FROM samples WHERE name=? AND deleted_by IS NULL',(name,))}
        out=[]
        for r in self.db.execute("""SELECT s.id,s.meeting,s.start,s.end,s.source,m.title,
                json_extract(s.payload,'$.text') text,json_extract(s.payload,'$.flags') flags,json_type(s.payload,'$.embedding') vector
                FROM segments s JOIN meetings m ON m.id=s.meeting
                WHERE s.speaker_name=? AND m.status='complete' AND s.end-s.start>=? ORDER BY s.end-s.start DESC LIMIT ?""",
                (name,self.CLEAN_MIN_SECONDS,max(8,limit*8))):
            if r['vector']!='array' or f"{r['meeting']}:{r['id']}" in used: continue
            try: flags=set(json.loads(r['flags'] or '[]'))
            except ValueError: flags=set()
            if self.UNCLEAN_FLAGS & flags: continue
            out.append({'id':r['id'],'meeting':r['meeting'],'meeting_title':r['title'],'start':round(r['start'],1),'end':round(r['end'],1),
                        'seconds':round(r['end']-r['start'],1),'source':r['source'],'text':(r['text'] or '')[:120]})
            if len(out)>=limit: break
        return out
    def enroll_segment(self, mid, sid, name):
        rows=[r for r in self.segments(mid) if r['id']==sid]
        if not rows: raise ValueError('Segment not found')
        r=rows[0]
        if not r['embedding'] or self.UNCLEAN_FLAGS.intersection(r['flags']): raise ValueError('Choose clean final speech, at least 3 seconds, without speaker uncertainty')
        duration=r['end']-r['start']; name=name.strip()
        if not name or duration < 3: raise ValueError('Enrollment needs a name and at least 3 seconds')
        vector=unit(r['embedding'])
        provenance=f'{mid}:{sid}'
        if self.db.execute('SELECT 1 FROM samples WHERE name=? AND model=? AND provenance=? AND deleted_by IS NULL',(name,r['embedding_model'],provenance)).fetchone():
            self.correct_segment(mid,sid,name); return
        # One transaction: label and voice sample either both persist or neither.
        with self.db:
            self.db.execute('INSERT INTO samples(name,model,vector,duration,provenance) VALUES(?,?,?,?,?)', (name,r['embedding_model'],json.dumps(vector),duration,f'{mid}:{sid}'))
            self.db.execute('UPDATE segments SET speaker_name=? WHERE meeting=? AND id=?',(name,mid,sid))
            self.db.execute('INSERT INTO corrections(meeting,speaker,name,created) VALUES(?,?,?,?)',(mid,f'segment:{sid}',name,datetime.now(timezone.utc).isoformat()))
    def enroll_speaker(self, mid, speaker, name):
        """Name every segment of a diarized speaker cluster and save one voice sample from the cluster's embedded segments."""
        name=name.strip()
        if not name: raise ValueError('Name cannot be empty')
        rows=[r for r in self.segments(mid) if r['speaker']==speaker]
        if not rows: raise ValueError('Speaker not found in meeting')
        voiced=[r for r in rows if r.get('embedding') and (r['end']-r['start']>=3 or (r.get('metrics') or {}).get('cluster_embedding')) and 'speaker_ambiguous' not in r['flags']]
        model=voiced[0]['embedding_model'] if voiced else None
        vectors=[unit(r['embedding']) for r in voiced if r['embedding_model']==model]
        duration=sum(r['end']-r['start'] for r in rows if 'speaker_ambiguous' not in r['flags'])  # cluster-level samples pool every short turn
        provenance=f'{mid}:speaker:{speaker}'
        created=datetime.now(timezone.utc).isoformat()
        with self.db:
            previous=self._reject_previous(mid, speaker, rows, name, created)
            feedback=self._record_feedback(rows, name)
            self.db.execute('UPDATE segments SET speaker_name=? WHERE meeting=? AND speaker=?',(name,mid,speaker))
            self.db.execute('INSERT INTO corrections(meeting,speaker,name,created,previous_name,feedback) VALUES(?,?,?,?,?,?)',(mid,speaker,name,created,previous,feedback))
            if vectors and duration>=3 and not self.db.execute('SELECT 1 FROM samples WHERE name=? AND model=? AND provenance=? AND deleted_by IS NULL',(name,model,provenance)).fetchone():
                centroid=unit([sum(col)/len(vectors) for col in zip(*vectors)])
                self.db.execute('INSERT INTO samples(name,model,vector,duration,provenance) VALUES(?,?,?,?,?)',(name,model,json.dumps(centroid),duration,provenance))
                return {'labeled':len(rows),'profile_saved':True,'seconds':duration}
        return {'labeled':len(rows),'profile_saved':False,'seconds':duration}
    def undo_correction(self, mid):
        """Take back the newest cluster naming of a meeting: labels return to what they were, the sample and the
        rejection that naming created disappear, the samples it hid come back, and the correction row is removed
        so quality stats do not count it. Restoring skips a sample whose slot has since been refilled, so undo
        can never leave the same voice stored twice."""
        row=self.db.execute("SELECT * FROM corrections WHERE meeting=? AND speaker NOT LIKE 'segment:%' ORDER BY id DESC LIMIT 1",(mid,)).fetchone()
        if not row: raise ValueError('Geri alınacak adlandırma yok')
        speaker,name,previous=row['speaker'],row['name'],row['previous_name']
        try: feedback=json.loads(row['feedback'] or 'null') or {}
        except ValueError: feedback={}
        with self.db:
            self.db.execute('UPDATE segments SET speaker_name=? WHERE meeting=? AND speaker=?',(previous,mid,speaker))
            mark=self.naming_mark(mid, speaker, row['created'] or '')
            self.db.execute('DELETE FROM samples WHERE name=? AND provenance=?',(name,f'{mid}:speaker:{speaker}'))
            self.db.execute("""UPDATE samples SET deleted_by=NULL WHERE deleted_by=? AND NOT EXISTS(
                SELECT 1 FROM samples live WHERE live.name=samples.name AND live.model IS samples.model
                  AND live.provenance=samples.provenance AND live.deleted_by IS NULL)""",(mark,))
            self.db.execute('DELETE FROM rejections WHERE provenance=?',(mark,))   # this naming's rejections, every name it convicted
            if feedback.get('confirmed'): self._bump(feedback['confirmed'],'confirmed',-1)   # the evidence goes back too
            if feedback.get('wrong'): self._bump(feedback['wrong'],'wrong',-1)
            self.db.execute('DELETE FROM corrections WHERE id=?',(row['id'],))
        # The cluster is open again (or back to its old name): what the rest of the meeting can be has changed.
        return {'speaker':speaker,'name':name,'previous':previous,**self.resuggest(mid)}
    def _retry_workspace_rows(self, mid, tables):
        if 'retry_workspaces' not in tables: return []
        return [dict(r) for r in self.db.execute('SELECT w.attempt,w.root,w.name,w.device,w.inode FROM retry_workspaces w JOIN retry_attempts a ON a.id=w.attempt WHERE a.meeting=?', (mid,))]
    @staticmethod
    def _remove_retry_workspaces(rows):
        """A crashed retry leaves full mic/system WAVs in a temp workspace outside the data dir. Removed with the
        module's hardened remover (inode identity, uid, 0700, whitelisted names, no symlinks) AFTER the
        transaction: slow file I/O never holds the write lock, and a refusal is reported, not swallowed."""
        import os
        from .retry_workspaces import _remove
        removed, kept = [], []
        for row in rows:
            try:
                root_fd = os.open(row['root'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try: _remove(root_fd, row); removed.append(str(Path(row['root']) / row['name']))
                finally: os.close(root_fd)
            except (OSError, ValueError, TypeError) as exc:
                if not isinstance(exc, FileNotFoundError): kept.append(f"{row.get('name')}: {type(exc).__name__}")
        return removed, kept
    def delete_meeting(self, mid):
        """Remove one meeting and every row derived from it. Voice profiles are kept. Returns metadata for file cleanup."""
        row=self.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()
        if not row: raise ValueError('Toplantı bulunamadı')
        tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        workspaces=self._retry_workspace_rows(mid, tables)   # read now, remove after the commit
        with self.db:
            if 'tasks' in tables:
                if 'drafts' in tables:
                    if 'draft_edits' in tables:
                        self.db.execute('DELETE FROM draft_edits WHERE draft IN (SELECT id FROM drafts WHERE task IN (SELECT id FROM tasks WHERE meeting=?))',(mid,))
                    self.db.execute('DELETE FROM drafts WHERE task IN (SELECT id FROM tasks WHERE meeting=?)',(mid,))
                if 'task_edits' in tables:
                    self.db.execute('DELETE FROM task_edits WHERE task IN (SELECT id FROM tasks WHERE meeting=?)',(mid,))
                self.db.execute('DELETE FROM tasks WHERE meeting=?',(mid,))
            if 'retry_attempts' in tables:
                for t in ('retry_segments','retry_workspaces'):
                    if t in tables: self.db.execute(f'DELETE FROM {t} WHERE attempt IN (SELECT id FROM retry_attempts WHERE meeting=?)',(mid,))
                self.db.execute('DELETE FROM retry_attempts WHERE meeting=?',(mid,))
            for t in ('analyses','cloud_chunks','cloud_sources','asr_checkpoints','diarization_checkpoints','corrections','text_edits','segments'):
                if t in tables: self.db.execute(f'DELETE FROM {t} WHERE meeting=?',(mid,))
            self.db.execute('DELETE FROM meetings WHERE id=?',(mid,))
        removed, kept = self._remove_retry_workspaces(workspaces)
        try: meta=json.loads(row['metadata']) or {}
        except (TypeError,ValueError): meta={}
        if removed or kept: meta['retry_workspaces']={'removed':removed,'kept':kept}   # the caller reports leftovers instead of hiding them
        return meta
    def profiles(self):
        return [dict(r) for r in self.db.execute('SELECT name,model,count(*) samples,sum(duration) seconds FROM samples WHERE deleted_by IS NULL GROUP BY name,model')]
    def delete_profile(self, name):
        with self.db: self.db.execute('DELETE FROM samples WHERE name=?', (name,)); self.db.execute('DELETE FROM rejections WHERE name=?', (name,)); self.db.execute('DELETE FROM profile_stats WHERE name=?', (name,))
    def profile_samples(self, name):
        """Every stored voice sample of a person with where it came from, for the maintenance screen."""
        titles = {r['id']: r['title'] for r in self.db.execute('SELECT id,title FROM meetings')}
        out = []
        for r in self.db.execute('SELECT id,model,duration,provenance FROM samples WHERE name=? AND deleted_by IS NULL ORDER BY id', (name,)):
            prov = r['provenance'] or ''
            parts = prov.split(':')
            mid = parts[1] if parts[0] == 'auto' and len(parts) > 1 else (parts[0] if parts and parts[0] in titles else None)
            kind = 'otomatik' if prov.startswith('auto:') else ('küme' if ':speaker:' in prov else ('bölüm' if len(parts) == 2 and parts[1].isdigit() else 'elle'))
            out.append({'id': r['id'], 'model': r['model'], 'seconds': round(float(r['duration'] or 0), 1), 'kind': kind, 'meeting': mid, 'meeting_title': titles.get(mid), 'provenance': prov})
        return out
    WEAK_FIT = 0.60   # a sample this far from its person's centroid is probably another voice or a bad recording
    def profile_health(self):
        """Per person: how many samples, how much speech, and the weakest sample's fit to the centroid — the
        weekly-maintenance view; nothing is pruned automatically."""
        groups = {}
        for r in self.db.execute('SELECT id,name,model,vector,duration,provenance FROM samples WHERE deleted_by IS NULL ORDER BY id'):
            try: x = unit(json.loads(r['vector']))
            except (ValueError, TypeError): continue
            groups.setdefault((r['name'], r['model']), []).append((r['id'], x, float(r['duration'] or 0), r['provenance'] or ''))
        rejected = {}
        for r in self.db.execute('SELECT name,count(*) FROM rejections GROUP BY name'): rejected[r[0]] = r[1]
        heard = self._last_heard()
        out = []
        for (name, model), xs in groups.items():
            fits = []
            if len(xs) >= 2:
                try:
                    centroid = unit([sum(col)/len(xs) for col in zip(*[x for _, x, _, _ in xs])])
                    fits = [(sid, cosine(x, centroid), prov) for sid, x, _, prov in xs]
                except ValueError: fits = []
            weakest = min(fits, key=lambda f: f[1]) if fits else None
            last = heard.get(name) or {}
            out.append({'name': name, 'model': model, 'samples': len(xs), 'seconds': round(sum(d for _, _, d, _ in xs), 1),
                        'auto_samples': sum(1 for _, _, _, p in xs if p.startswith('auto:')), 'rejections': rejected.get(name, 0),
                        'weakest_fit': round(weakest[1], 3) if weakest else None, 'weakest_sample': weakest[0] if weakest else None,
                        'weak': bool(weakest and weakest[1] < self.WEAK_FIT),
                        'last_meeting': last.get('meeting'), 'last_meeting_title': last.get('title'), 'last_heard': last.get('created')})
        return sorted(out, key=lambda p: (not p['weak'], -p['samples'], p['name']))
    def _last_heard(self):
        """Newest meeting each person was heard in. SQLite hands back the row that produced max(created)."""
        return {r['speaker_name']: {'meeting': r['id'], 'title': r['title'], 'created': r['created']} for r in self.db.execute(
            "SELECT s.speaker_name,m.id,m.title,max(m.created) created FROM segments s JOIN meetings m ON m.id=s.meeting "
            "WHERE s.speaker_name IS NOT NULL AND s.speaker_name<>'' GROUP BY s.speaker_name")}
    def delete_sample(self, sample_id):
        with self.db:
            cur = self.db.execute('DELETE FROM samples WHERE id=?', (int(sample_id),))
            if not cur.rowcount: raise ValueError('Örnek bulunamadı')
    def rename_profile(self, name, new_name):
        """Rename a person; renaming onto an existing person merges the samples. Segment names follow."""
        new_name = (new_name or '').strip()
        if not new_name: raise ValueError('Yeni isim boş olamaz')
        if new_name == name: return {'renamed': 0, 'merged': False}
        merged = bool(self.db.execute('SELECT 1 FROM samples WHERE name=? AND deleted_by IS NULL', (new_name,)).fetchone())
        with self.db:
            self.db.execute('DELETE FROM samples WHERE name=? AND deleted_by IS NOT NULL', (name,))   # hidden rows must not resurface under the merged person
            n = self.db.execute('UPDATE samples SET name=? WHERE name=? AND deleted_by IS NULL', (new_name, name)).rowcount
            self.db.execute('UPDATE rejections SET name=? WHERE name=?', (new_name, name))
            self.db.execute('UPDATE segments SET speaker_name=? WHERE speaker_name=?', (new_name, name))
            for column in ('confirmed', 'wrong'):   # undo reads these names back, so they follow the person too
                self.db.execute(f"UPDATE corrections SET feedback=json_set(feedback,'$.{column}',?) WHERE json_extract(feedback,'$.{column}')=?", (new_name, name))
            old = self.db.execute('SELECT confirmed,wrong FROM profile_stats WHERE name=?', (name,)).fetchone()
            if old:   # the evidence belongs to the person, so it survives a rename and adds up on a merge
                self.db.execute('INSERT OR IGNORE INTO profile_stats(name,confirmed,wrong) VALUES(?,0,0)', (new_name,))
                self.db.execute('UPDATE profile_stats SET confirmed=confirmed+?,wrong=wrong+? WHERE name=?', (old['confirmed'] or 0, old['wrong'] or 0, new_name))
                self.db.execute('DELETE FROM profile_stats WHERE name=?', (name,))
        return {'renamed': n, 'merged': merged}
    def _scores(self, vector, model, exclude=None):
        """Every person's blended score for one voice: mean of centroid similarity and best single-sample similarity.
        `exclude` drops the samples that came from one meeting (replay: a meeting must not vouch for itself)."""
        v = unit(vector); groups = {}
        sql = 'SELECT name,vector FROM samples WHERE model=? AND deleted_by IS NULL'; args = [model]   # a naming's rejected samples are hidden, not gone; they must not identify anyone
        if exclude: sql += ' AND provenance NOT LIKE ? AND provenance NOT LIKE ?'; args += [f'{exclude}:%', f'auto:{exclude}:%']
        for row in self.db.execute(sql, args):
            x = json.loads(row['vector'])
            if len(x) == len(v): groups.setdefault(row['name'], []).append(x)
        vetoed = set()
        rsql = 'SELECT name,vector FROM rejections WHERE model=?'; rargs = [model]
        if exclude: rsql += ' AND provenance NOT LIKE ?'; rargs.append(f'{exclude}:%')
        for row in self.db.execute(rsql, rargs):
            x = json.loads(row['vector'])
            if row['name'] in groups and len(x) == len(v) and cosine(v, unit(x)) >= self.REJECT_SIMILARITY: vetoed.add(row['name'])
        scores = []
        for name, xs in groups.items():
            if name in vetoed: continue
            try: centroid = unit([sum(col)/len(xs) for col in zip(*xs)])
            except ValueError: continue  # contradictory samples cannot identify anyone
            best = max(cosine(v, unit(x)) for x in xs)
            scores.append({'name': name, 'centroid': round(cosine(v, centroid), 3), 'best_sample': round(best, 3), 'score': (cosine(v, centroid) + best) / 2, 'samples': len(xs)})
        return sorted(scores, key=lambda s: -s['score'])
    def explain_identity(self, vector, model, limit=5, base=None):
        """Why a voice matched: similarity to every person's centroid and to their nearest sample, plus one plain
        sentence about the profile itself — a single sample, a sample that does not fit, or a bar the user's own
        corrections have moved. `base` (the global threshold) turns the personal bar on."""
        weak = {p['name'] for p in self.profile_health() if p['weak']}
        stats = {r['name']: (r['confirmed'] or 0, r['wrong'] or 0) for r in self.db.execute('SELECT name,confirmed,wrong FROM profile_stats')}
        out = []
        for s in self._scores(vector, model)[:limit]:
            bar = self.person_threshold(s['name'], base) if base is not None else None
            notes = []
            if s['samples'] == 1: notes.append('tek örnek — ikinci bir temiz örnek isabeti artırır')
            if s['name'] in weak: notes.append('zayıf örnek var')
            confirmed, wrong = stats.get(s['name'], (0, 0))
            if bar is not None and abs(bar-base) > 1e-9:
                why = [f'{min(confirmed,3)} onaylı öneri'] if confirmed else []
                if wrong: why.append(f'{min(wrong,3)} yanlış eşleşme')
                notes.append(' ve '.join(why)+' → eşik '+f'{bar:.2f}'.replace('.', ','))
            out.append({**s, 'score': round(s['score'], 3), 'threshold_used': round(bar, 3) if bar is not None else None, 'person_note': ' · '.join(notes)})
        return out
    def identify(self, vector, model, threshold=0.80, margin=0.08, exclude=None):
        """Score = mean of centroid similarity and best single-sample similarity: the centroid is stable,
        the nearest sample tolerates a person recorded under different conditions. The bar is the top candidate's
        own (Q5): the global one until the user has confirmed or overruled that person."""
        scores = self._scores(vector, model, exclude)
        if not scores: return {'name': None, 'candidate': None, 'similarity': None, 'margin': None, 'threshold_used': threshold}
        score, name = scores[0]['score'], scores[0]['name']
        gap = score - scores[1]['score'] if len(scores) > 1 else score + 1
        bar = self.person_threshold(name, threshold, exclude)
        return {'name': name if score >= bar and gap >= margin else None, 'candidate': name, 'similarity': score, 'margin': gap, 'threshold_used': bar}
    def add_sample_if_new(self, name, vector, model, duration, provenance, cap=8):
        """Self-feeding profiles: one more sample per meeting for a confident match, bounded per person."""
        if self.db.execute('SELECT 1 FROM samples WHERE name=? AND model=? AND provenance=? AND deleted_by IS NULL',(name,model,provenance)).fetchone(): return False
        if self.db.execute('SELECT count(*) FROM samples WHERE name=? AND model=? AND deleted_by IS NULL',(name,model)).fetchone()[0] >= cap: return False
        self.enroll(name, vector, model, duration, provenance); return True
    def resuggest(self, mid):
        """Q9 in-session adaptation. The moment the user names one cluster, the meeting's other still-unnamed
        linked speakers are scored again: the person he just named now exists, and the sample his correction
        rejected is gone. Same thresholds as finalize, so a name is written only where finalize would have written
        one; a cluster the user has already named is never re-scored and never overwritten. Cheap — the voice
        vectors are already in SQLite, no embedder runs — and only ever triggered by a user action.
        Counts are people (linked clusters), not segments."""
        from .cloud_finalize import IDENTITY_THRESHOLD, IDENTITY_MARGIN, SUGGEST_THRESHOLD, linked_centroid, assign_identities
        speakers={}
        for r in self.segments(mid):
            if (r.get('metrics') or {}).get('cluster') is not None: speakers.setdefault((r['source'],r['speaker']),[]).append(r)
        scored=[]
        for members in speakers.values():
            if any(r.get('speaker_name') for r in members): continue
            model=next((r['embedding_model'] for r in members if r.get('embedding')),None)
            centroid=linked_centroid(members,model) if model else None
            if centroid is not None: scored.append((members,self.identify(centroid,model,IDENTITY_THRESHOLD,IDENTITY_MARGIN)))
        assignment=assign_identities(scored)
        renamed=suggested=0
        for members,identity in scored:
            name=assignment.get(id(members))
            sim=identity.get('similarity') or 0;gap=identity.get('margin') or 0
            suggestion=identity.get('candidate') if (not name and sim>=SUGGEST_THRESHOLD and gap>=IDENTITY_MARGIN) else None
            for r in members:
                r.setdefault('metrics',{})['identity']={**identity,'name':name,'suggested':suggestion}
                with self.db: self.db.execute('UPDATE segments SET speaker_name=?,payload=? WHERE id=? AND meeting=?',(name,json.dumps(r,ensure_ascii=False),r['id'],mid))
            if name: renamed+=1
            elif suggestion: suggested+=1
        return {'renamed':renamed,'suggested':suggested}
