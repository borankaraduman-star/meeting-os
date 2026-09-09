"""Versioned analysis and durable task state on the existing local SQLite store."""
import json
from datetime import datetime,timezone
from .intelligence import fingerprint
from .metrics import normalize

STOPWORDS={'ve','bir','bu','şu','o','ne','kaç','mi','mı','mu','mü','ile','için','de','da','ki','ama','veya','ya','gibi','çok','daha','en','var','yok','mi','nasıl','neden','hangi','kim','nerede','zaman','olan','oldu','olduğu','söylendi','söyledi','söylemiş','dedi','diye','ise','hakkında','bana','bize','şey'}

def query_terms(query,limit=12):
    """Content words of a question, without Turkish function words; short tokens are kept only when nothing else remains."""
    tokens=normalize(query).split()
    content=[t for t in tokens if t not in STOPWORDS and len(t)>=3]
    return (content or tokens)[:limit]

def _stem_match(term,word):
    """Turkish suffixes stack (modül → modülleri, eğitim → eğitimlerinin): count a hit when the shared prefix covers
    most of the shorter form. Exact substring stays a full hit; a stem hit is worth a little less to keep ranking stable."""
    if term in word:return 1.0
    shorter=min(len(term),len(word))
    if shorter<4:return 0.0
    common=0
    for a,b in zip(term,word):
        if a!=b:break
        common+=1
    return 0.8 if common>=max(4,-(-shorter*6//10)) else 0.0

def match_score(terms,text):
    words=normalize(text).split()
    if not words:return 0.0
    total=0.0
    for term in terms:
        total+=max((_stem_match(term,w) for w in words),default=0.0)
    return total

def now():return datetime.now(timezone.utc).isoformat()
class Memory:
    def __init__(self,store):
        self.store=store;self.db=store.db
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY,meeting TEXT REFERENCES meetings(id),input_hash TEXT,model TEXT,payload TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,meeting TEXT REFERENCES meetings(id),analysis INTEGER REFERENCES analyses(id),input_hash TEXT,title TEXT,owner TEXT,due_text TEXT,state TEXT,payload TEXT,user_edited INTEGER DEFAULT 0,created TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS task_edits(id INTEGER PRIMARY KEY,task TEXT,previous TEXT,replacement TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS draft_edits(id INTEGER PRIMARY KEY,draft TEXT,previous TEXT,replacement TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,task TEXT,input_hash TEXT,task_hash TEXT,kind TEXT,text TEXT,created TEXT);
        CREATE INDEX IF NOT EXISTS analyses_meeting ON analyses(meeting,id);
        CREATE INDEX IF NOT EXISTS tasks_meeting ON tasks(meeting,updated);
        CREATE INDEX IF NOT EXISTS drafts_task ON drafts(task);
        ''')
        self._hashes={};self._analyses={};self._writes=self.db.total_changes
    def _memo(self):
        """One report asks for the same meeting again and again, and each ask used to reread the whole transcript.
        The answers are kept until anything is written through this connection — a correction, a new segment,
        a saved analysis — which is what would change them."""
        if self._writes!=self.db.total_changes:
            self._writes=self.db.total_changes;self._hashes.clear();self._analyses.clear()
        return self._hashes,self._analyses
    def current_hash(self,mid):
        hashes,_=self._memo()
        if mid not in hashes:hashes[mid]=fingerprint(self.store.display_segments(mid))
        return hashes[mid]
    def latest(self,mid):
        _,analyses=self._memo()
        if mid not in analyses:analyses[mid]=self._read_latest(mid)
        return analyses[mid]
    def _read_latest(self,mid):
        row=self.db.execute('SELECT * FROM analyses WHERE meeting=? ORDER BY id DESC LIMIT 1',(mid,)).fetchone()
        if not row:return None
        d=dict(row);d['payload']=json.loads(d['payload']);d['stale']=d['input_hash']!=self.current_hash(mid);return d
    def save_analysis(self,mid,input_hash,model,record):
        import hashlib   # only a save needs it; every report imports this module and none of them do
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.current_hash(mid)!=input_hash:raise ValueError('Transkript analiz sırasında değişti; yeniden analiz edin')
            aid=self.db.execute('INSERT INTO analyses(meeting,input_hash,model,payload,created) VALUES(?,?,?,?,?)',(mid,input_hash,model,json.dumps(record,ensure_ascii=False),now())).lastrowid
            for item in record['actions']:
                stable=json.dumps([mid,normalize(item['title']),[(e['segment_id'],e['quote']) for e in item['evidence']]],ensure_ascii=False,sort_keys=True)
                tid=hashlib.sha256(stable.encode()).hexdigest()[:20]
                self.db.execute('''INSERT INTO tasks(id,meeting,analysis,input_hash,title,owner,due_text,state,payload,created,updated) VALUES(?,?,?,?,?,?,?,'open',?,?,?)
                ON CONFLICT(id) DO UPDATE SET analysis=excluded.analysis,input_hash=excluded.input_hash,payload=excluded.payload,title=CASE WHEN tasks.user_edited=1 THEN tasks.title ELSE excluded.title END,owner=CASE WHEN tasks.user_edited=1 THEN tasks.owner ELSE excluded.owner END,due_text=CASE WHEN tasks.user_edited=1 THEN tasks.due_text ELSE excluded.due_text END''',(tid,mid,aid,input_hash,item['title'],item.get('owner'),item.get('due_text'),json.dumps(item,ensure_ascii=False),now(),now()))
        return self.latest(mid)
    def set_due_date(self,tid,due_date):
        """Store an approved calendar date (ISO, or None to clear) inside the task payload; due_text stays as the source said it."""
        row=self.db.execute('SELECT payload FROM tasks WHERE id=?',(tid,)).fetchone()
        if not row:raise ValueError('Görev bulunamadı')
        payload=json.loads(row['payload'] or '{}')
        if due_date: payload['due_date']=str(due_date)[:10]
        else: payload.pop('due_date',None)
        with self.db:self.db.execute('UPDATE tasks SET payload=?,user_edited=1,updated=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),now(),tid))
        return payload.get('due_date')
    def actions(self,owner=None,meeting=None):
        result=[];latest_ids={r['meeting']:r['id'] for r in self.db.execute('SELECT meeting,MAX(id) AS id FROM analyses GROUP BY meeting')}
        for row in self.db.execute('SELECT tasks.*,meetings.title AS meeting_title FROM tasks JOIN meetings ON meetings.id=tasks.meeting ORDER BY tasks.created DESC'):
            d=dict(row)
            if owner and normalize(d['owner'] or '')!=normalize(owner):continue
            if meeting and d['meeting']!=meeting:continue
            d['payload']=json.loads(d['payload'])
            d['stale']=d['input_hash']!=self.current_hash(d['meeting']) or d['analysis']!=latest_ids.get(d['meeting']);result.append(d)
        return result
    def task(self,tid):
        rows=[r for r in self.actions() if r['id']==tid]
        if not rows:raise ValueError('Görev bulunamadı')
        return rows[0]
    def update_action(self,tid,changes):
        if not changes or set(changes)-{'state','title','owner','due_text'}:raise ValueError('Geçersiz görev değişikliği')
        if 'state' in changes and changes['state'] not in ('open','in_progress','done','dismissed'):raise ValueError('Geçersiz görev durumu')
        for key in ('title','owner','due_text'):
            if key in changes:
                if changes[key] is not None and (not isinstance(changes[key],str) or len(changes[key])>1600):raise ValueError('Geçersiz görev alanı')
                if key=='title' and not (changes[key] or '').strip():raise ValueError('Görev başlığı boş olamaz')
        old=self.task(tid)
        with self.db:
            self.db.execute('UPDATE tasks SET '+','.join(k+'=?' for k in changes)+',user_edited=1,updated=? WHERE id=?',(*changes.values(),now(),tid))
            self.db.execute('INSERT INTO task_edits(task,previous,replacement,created) VALUES(?,?,?,?)',(tid,json.dumps(old,ensure_ascii=False),json.dumps(changes,ensure_ascii=False),now()))
        return self.task(tid)
    def search(self,query,limit=20,speaker=None):
        tokens=query_terms(query)
        if not tokens:return []
        rows=self.db.execute("SELECT segments.id,meeting,meetings.title AS meeting_title,start,end,speaker,speaker_name,json_extract(payload,'$.text') AS text FROM segments JOIN meetings ON meetings.id=segments.meeting WHERE meetings.status='complete' ORDER BY meetings.created DESC,start")
        found=[]
        for r in rows:
            d=dict(r)
            if speaker and normalize(d['speaker_name'] or '')!=normalize(speaker):continue
            score=match_score(tokens,d['text'] or '')
            if score:d['score']=score;found.append(d)
        return sorted(found,key=lambda x:x['score'],reverse=True)[:min(max(1,limit),50)]
