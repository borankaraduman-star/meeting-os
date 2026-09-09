"""SQLite speaker memory. Only explicit enrollment changes voice profiles."""
import json
import math
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone

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
        self.db = sqlite3.connect(path)
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS meetings(id TEXT PRIMARY KEY, title TEXT, created TEXT, status TEXT, metadata TEXT);
        CREATE TABLE IF NOT EXISTS segments(id INTEGER PRIMARY KEY, meeting TEXT REFERENCES meetings(id), start REAL, end REAL, source TEXT, speaker TEXT, speaker_name TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, name TEXT, model TEXT, vector TEXT, duration REAL, provenance TEXT);
        CREATE TABLE IF NOT EXISTS corrections(id INTEGER PRIMARY KEY, meeting TEXT, speaker TEXT, name TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS text_edits(id INTEGER PRIMARY KEY, meeting TEXT, segment INTEGER, previous TEXT, replacement TEXT, created TEXT);
        CREATE INDEX IF NOT EXISTS segment_meeting ON segments(meeting,start);
        ''')
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
        rows=self.db.execute("SELECT id,start,end,source,speaker,speaker_name,json_extract(payload,'$.text') AS text,json_extract(payload,'$.flags') AS flags FROM segments WHERE meeting=? ORDER BY CASE WHEN source='chatgpt_manual' THEN id ELSE start END,id",(mid,))
        return [{**dict(r),'flags':json.loads(r['flags'] or '[]')} for r in rows]
    def correct(self, mid, speaker, name):
        name = name.strip()
        if not name: raise ValueError('Name cannot be empty')
        with self.db:
            cur = self.db.execute('UPDATE segments SET speaker_name=? WHERE meeting=? AND speaker=?', (name, mid, speaker))
            if not cur.rowcount: raise ValueError('Speaker not found in meeting')
            self.db.execute('INSERT INTO corrections(meeting,speaker,name,created) VALUES(?,?,?,?)', (mid, speaker, name, datetime.now(timezone.utc).isoformat()))
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
    def enroll_segment(self, mid, sid, name):
        rows=[r for r in self.segments(mid) if r['id']==sid]
        if not rows: raise ValueError('Segment not found')
        r=rows[0]
        forbidden={'speaker_ambiguous','possible_non_speech','repetition','provisional','low_asr_confidence','short_context_diarization'}
        if not r['embedding'] or forbidden.intersection(r['flags']): raise ValueError('Choose clean final speech, at least 3 seconds, without speaker uncertainty')
        duration=r['end']-r['start']; name=name.strip()
        if not name or duration < 3: raise ValueError('Enrollment needs a name and at least 3 seconds')
        vector=unit(r['embedding'])
        provenance=f'{mid}:{sid}'
        if self.db.execute('SELECT 1 FROM samples WHERE name=? AND model=? AND provenance=?',(name,r['embedding_model'],provenance)).fetchone():
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
        voiced=[r for r in rows if r.get('embedding') and r['end']-r['start']>=3 and 'speaker_ambiguous' not in r['flags']]
        model=voiced[0]['embedding_model'] if voiced else None
        vectors=[unit(r['embedding']) for r in voiced if r['embedding_model']==model]
        duration=sum(r['end']-r['start'] for r in voiced)
        provenance=f'{mid}:speaker:{speaker}'
        with self.db:
            self.db.execute('UPDATE segments SET speaker_name=? WHERE meeting=? AND speaker=?',(name,mid,speaker))
            self.db.execute('INSERT INTO corrections(meeting,speaker,name,created) VALUES(?,?,?,?)',(mid,speaker,name,datetime.now(timezone.utc).isoformat()))
            if vectors and duration>=3 and not self.db.execute('SELECT 1 FROM samples WHERE name=? AND model=? AND provenance=?',(name,model,provenance)).fetchone():
                centroid=unit([sum(col)/len(vectors) for col in zip(*vectors)])
                self.db.execute('INSERT INTO samples(name,model,vector,duration,provenance) VALUES(?,?,?,?,?)',(name,model,json.dumps(centroid),duration,provenance))
                return {'labeled':len(rows),'profile_saved':True,'seconds':duration}
        return {'labeled':len(rows),'profile_saved':False,'seconds':duration}
    def delete_meeting(self, mid):
        """Remove one meeting and every row derived from it. Voice profiles are kept. Returns metadata for file cleanup."""
        row=self.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()
        if not row: raise ValueError('Toplantı bulunamadı')
        tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
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
        try: return json.loads(row['metadata']) or {}
        except (TypeError,ValueError): return {}
    def profiles(self):
        return [dict(r) for r in self.db.execute('SELECT name,model,count(*) samples,sum(duration) seconds FROM samples GROUP BY name,model')]
    def delete_profile(self, name):
        with self.db: self.db.execute('DELETE FROM samples WHERE name=?', (name,))
    def identify(self, vector, model, threshold=0.80, margin=0.08):
        v = unit(vector)
        groups = {}
        for row in self.db.execute('SELECT name,vector FROM samples WHERE model=?', (model,)):
            x = json.loads(row['vector'])
            if len(x) == len(v): groups.setdefault(row['name'], []).append(x)
        scores = []
        for name, xs in groups.items():
            try: centroid = unit([sum(col)/len(xs) for col in zip(*xs)])
            except ValueError: continue  # contradictory samples cannot identify anyone
            scores.append((cosine(v, centroid), name))
        scores.sort(reverse=True)
        if not scores: return {'name': None, 'similarity': None, 'margin': None}
        score, name = scores[0]
        gap = score - scores[1][0] if len(scores) > 1 else score + 1
        return {'name': name if score >= threshold and gap >= margin else None, 'similarity': score, 'margin': gap}
