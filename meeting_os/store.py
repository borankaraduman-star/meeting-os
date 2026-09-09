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
        self.path = path
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
        CREATE TABLE IF NOT EXISTS rejections(id INTEGER PRIMARY KEY, name TEXT, model TEXT, vector TEXT, provenance TEXT, created TEXT);
        CREATE INDEX IF NOT EXISTS segment_meeting ON segments(meeting,start);
        ''')
        if 'previous_name' not in {r[1] for r in self.db.execute('PRAGMA table_info(corrections)')}:
            self.db.execute('ALTER TABLE corrections ADD COLUMN previous_name TEXT')
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
        with self.db:
            previous=self._reject_previous(mid, speaker, rows, name)
            self.db.execute('UPDATE segments SET speaker_name=? WHERE meeting=? AND speaker=?', (name, mid, speaker))
            self.db.execute('INSERT INTO corrections(meeting,speaker,name,created,previous_name) VALUES(?,?,?,?,?)', (mid, speaker, name, datetime.now(timezone.utc).isoformat(), previous))
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
    def _reject_previous(self, mid, speaker, rows, name):
        """Negative feedback (must run inside the caller's transaction): renaming a cluster away from a person
        drops the samples that cluster fed into that person and remembers the voice as rejected for them."""
        wrong=[n for n in self._previous_names(rows) if n!=name]
        if not wrong: return None
        clusters={(r.get('metrics') or {}).get('cluster') for r in rows} - {None}
        provenances=[f'auto:{mid}:{c}' for c in clusters]+[f'{mid}:speaker:{speaker}']
        vector,model=self._cluster_vector(rows)
        for prev in wrong:
            self.db.executemany('DELETE FROM samples WHERE name=? AND provenance=?',[(prev,p) for p in provenances])
            if vector is not None and not self.db.execute('SELECT 1 FROM rejections WHERE name=? AND provenance=?',(prev,f'{mid}:speaker:{speaker}')).fetchone():
                self.db.execute('INSERT INTO rejections(name,model,vector,provenance,created) VALUES(?,?,?,?,?)',(prev,model,json.dumps(vector),f'{mid}:speaker:{speaker}',datetime.now(timezone.utc).isoformat()))
        return wrong[0]
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
        voiced=[r for r in rows if r.get('embedding') and (r['end']-r['start']>=3 or (r.get('metrics') or {}).get('cluster_embedding')) and 'speaker_ambiguous' not in r['flags']]
        model=voiced[0]['embedding_model'] if voiced else None
        vectors=[unit(r['embedding']) for r in voiced if r['embedding_model']==model]
        duration=sum(r['end']-r['start'] for r in rows if 'speaker_ambiguous' not in r['flags'])  # cluster-level samples pool every short turn
        provenance=f'{mid}:speaker:{speaker}'
        with self.db:
            previous=self._reject_previous(mid, speaker, rows, name)
            self.db.execute('UPDATE segments SET speaker_name=? WHERE meeting=? AND speaker=?',(name,mid,speaker))
            self.db.execute('INSERT INTO corrections(meeting,speaker,name,created,previous_name) VALUES(?,?,?,?,?)',(mid,speaker,name,datetime.now(timezone.utc).isoformat(),previous))
            if vectors and duration>=3 and not self.db.execute('SELECT 1 FROM samples WHERE name=? AND model=? AND provenance=?',(name,model,provenance)).fetchone():
                centroid=unit([sum(col)/len(vectors) for col in zip(*vectors)])
                self.db.execute('INSERT INTO samples(name,model,vector,duration,provenance) VALUES(?,?,?,?,?)',(name,model,json.dumps(centroid),duration,provenance))
                return {'labeled':len(rows),'profile_saved':True,'seconds':duration}
        return {'labeled':len(rows),'profile_saved':False,'seconds':duration}
    def undo_correction(self, mid):
        """Take back the newest cluster naming of a meeting: labels return to what they were, the sample and the
        rejection that naming created disappear, and the correction row is removed so quality stats do not count it."""
        row=self.db.execute("SELECT * FROM corrections WHERE meeting=? AND speaker NOT LIKE 'segment:%' ORDER BY id DESC LIMIT 1",(mid,)).fetchone()
        if not row: raise ValueError('Geri alınacak adlandırma yok')
        speaker,name,previous=row['speaker'],row['name'],row['previous_name']
        with self.db:
            self.db.execute('UPDATE segments SET speaker_name=? WHERE meeting=? AND speaker=?',(previous,mid,speaker))
            self.db.execute('DELETE FROM samples WHERE name=? AND provenance=?',(name,f'{mid}:speaker:{speaker}'))
            if previous: self.db.execute('DELETE FROM rejections WHERE name=? AND provenance=?',(previous,f'{mid}:speaker:{speaker}'))
            self.db.execute('DELETE FROM corrections WHERE id=?',(row['id'],))
        return {'speaker':speaker,'name':name,'previous':previous}
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
        with self.db: self.db.execute('DELETE FROM samples WHERE name=?', (name,)); self.db.execute('DELETE FROM rejections WHERE name=?', (name,))
    def profile_samples(self, name):
        """Every stored voice sample of a person with where it came from, for the maintenance screen."""
        titles = {r['id']: r['title'] for r in self.db.execute('SELECT id,title FROM meetings')}
        out = []
        for r in self.db.execute('SELECT id,model,duration,provenance FROM samples WHERE name=? ORDER BY id', (name,)):
            prov = r['provenance'] or ''
            parts = prov.split(':')
            mid = parts[1] if parts[0] == 'auto' and len(parts) > 1 else (parts[0] if parts and parts[0] in titles else None)
            kind = 'otomatik' if prov.startswith('auto:') else ('küme' if ':speaker:' in prov else ('bölüm' if len(parts) == 2 and parts[1].isdigit() else 'elle'))
            out.append({'id': r['id'], 'model': r['model'], 'seconds': round(float(r['duration'] or 0), 1), 'kind': kind, 'meeting': mid, 'meeting_title': titles.get(mid), 'provenance': prov})
        return out
    def delete_sample(self, sample_id):
        with self.db:
            cur = self.db.execute('DELETE FROM samples WHERE id=?', (int(sample_id),))
            if not cur.rowcount: raise ValueError('Örnek bulunamadı')
    def rename_profile(self, name, new_name):
        """Rename a person; renaming onto an existing person merges the samples. Segment names follow."""
        new_name = (new_name or '').strip()
        if not new_name: raise ValueError('Yeni isim boş olamaz')
        if new_name == name: return {'renamed': 0, 'merged': False}
        merged = bool(self.db.execute('SELECT 1 FROM samples WHERE name=?', (new_name,)).fetchone())
        with self.db:
            n = self.db.execute('UPDATE samples SET name=? WHERE name=?', (new_name, name)).rowcount
            self.db.execute('UPDATE rejections SET name=? WHERE name=?', (new_name, name))
            self.db.execute('UPDATE segments SET speaker_name=? WHERE speaker_name=?', (new_name, name))
        return {'renamed': n, 'merged': merged}
    def _scores(self, vector, model, exclude=None):
        """Every person's blended score for one voice: mean of centroid similarity and best single-sample similarity.
        `exclude` drops the samples that came from one meeting (replay: a meeting must not vouch for itself)."""
        v = unit(vector); groups = {}
        sql = 'SELECT name,vector FROM samples WHERE model=?'; args = [model]
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
    def explain_identity(self, vector, model, limit=5):
        """Why a voice matched: similarity to every person's centroid and to their nearest sample."""
        return [{**s, 'score': round(s['score'], 3)} for s in self._scores(vector, model)[:limit]]
    def identify(self, vector, model, threshold=0.80, margin=0.08, exclude=None):
        """Score = mean of centroid similarity and best single-sample similarity: the centroid is stable,
        the nearest sample tolerates a person recorded under different conditions."""
        scores = self._scores(vector, model, exclude)
        if not scores: return {'name': None, 'candidate': None, 'similarity': None, 'margin': None}
        score, name = scores[0]['score'], scores[0]['name']
        gap = score - scores[1]['score'] if len(scores) > 1 else score + 1
        return {'name': name if score >= threshold and gap >= margin else None, 'candidate': name, 'similarity': score, 'margin': gap}
    def add_sample_if_new(self, name, vector, model, duration, provenance, cap=8):
        """Self-feeding profiles: one more sample per meeting for a confident match, bounded per person."""
        if self.db.execute('SELECT 1 FROM samples WHERE name=? AND model=? AND provenance=?',(name,model,provenance)).fetchone(): return False
        if self.db.execute('SELECT count(*) FROM samples WHERE name=? AND model=?',(name,model)).fetchone()[0] >= cap: return False
        self.enroll(name, vector, model, duration, provenance); return True
