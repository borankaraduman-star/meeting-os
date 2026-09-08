"""Internal transactional retry storage. Not yet connected to inference or UI."""
import hashlib,json,uuid
from contextlib import contextmanager
from .recovery import classify,metadata,process_identity,valid_identity

MAX_STAGE_BYTES=32*1024*1024

class RetryStore:
    def __init__(self,store,inspect=process_identity):
        self.store=store;self.db=store.db;self.inspect=inspect
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS retry_attempts(id TEXT PRIMARY KEY,meeting TEXT REFERENCES meetings(id),owner TEXT,baseline TEXT,state TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS retry_one_running ON retry_attempts(meeting) WHERE state='running';
        CREATE TABLE IF NOT EXISTS retry_segments(attempt TEXT REFERENCES retry_attempts(id),sequence INTEGER,payload TEXT,PRIMARY KEY(attempt,sequence));
        ''')
    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:yield;self.db.commit()
        except BaseException:self.db.rollback();raise
    def meeting(self,mid):
        row=self.db.execute('SELECT * FROM meetings WHERE id=?',(mid,)).fetchone()
        if row is None:raise ValueError('Meeting missing')
        return row
    def protected(self,mid):
        tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('corrections','text_edits','analyses','tasks'):
            if table in tables and self.db.execute(f'SELECT 1 FROM {table} WHERE meeting=? LIMIT 1',(mid,)).fetchone():
                raise ValueError('Retry would invalidate corrections or linked records')
        for row in self.db.execute('SELECT payload FROM segments WHERE meeting=?',(mid,)):
            payload=json.loads(row[0])
            if payload.get('edited') or 'provisional' not in payload.get('flags',[]):
                raise ValueError('Retry cannot replace final or edited segments')
    def snapshot(self,mid):
        h=hashlib.sha256();row=self.meeting(mid)
        h.update(json.dumps([row['title'],row['metadata']],ensure_ascii=False).encode())
        for row in self.db.execute('SELECT * FROM segments WHERE meeting=? ORDER BY id',(mid,)):
            h.update(json.dumps(list(row),ensure_ascii=False).encode())
        return h.hexdigest()
    def begin(self,mid,owner):
        if not valid_identity(owner) or classify(owner,self.inspect)!='active':raise ValueError('Retry owner unavailable')
        with self.transaction():
            row=self.meeting(mid);meta=metadata(row)
            running=self.db.execute("SELECT * FROM retry_attempts WHERE meeting=? AND state='running'",(mid,)).fetchone()
            if running:
                if classify(json.loads(running['owner']),self.inspect)!='interrupted':raise ValueError('Retry still active or unknown')
                self.db.execute("UPDATE retry_attempts SET state='aborted' WHERE id=?",(running['id'],))
                self.db.execute('DELETE FROM retry_segments WHERE attempt=?',(running['id'],))
            if row['status']=='processing':
                if classify(meta.get('worker_identity'),self.inspect)!='interrupted':raise ValueError('Meeting still active or unknown')
            elif row['status'] not in ('incomplete','provisional','failed'):raise ValueError('Meeting cannot be retried')
            self.protected(mid);attempt=uuid.uuid4().hex
            meta.update(worker_pid=owner['pid'],worker_identity=owner,retry_attempt=attempt)
            self.db.execute("UPDATE meetings SET status='processing',metadata=? WHERE id=?",(json.dumps(meta),mid))
            self.db.execute('INSERT INTO retry_attempts VALUES(?,?,?,?,?)',(attempt,mid,json.dumps(owner),self.snapshot(mid),'running'))
            return attempt
    def active(self,attempt):
        row=self.db.execute('SELECT * FROM retry_attempts WHERE id=?',(attempt,)).fetchone()
        if row is None or row['state']!='running':raise ValueError('Retry is not running')
        meeting=self.meeting(row['meeting'])
        if meeting['status']!='processing' or metadata(meeting).get('retry_attempt')!=attempt:raise ValueError('Retry no longer owns meeting')
        if classify(json.loads(row['owner']),self.inspect)!='active':raise ValueError('Retry owner unavailable')
        return row
    def stage(self,attempt,sequence,segment):
        if type(sequence)!=int or not 0<=sequence<10000:raise ValueError('Invalid stage sequence')
        payload=json.dumps(segment.to_dict(),ensure_ascii=False,allow_nan=False)
        if len(payload.encode())>1024*1024 or 'provisional' in segment.flags:raise ValueError('Invalid final segment')
        with self.transaction():
            self.active(attempt)
            old=self.db.execute('SELECT payload FROM retry_segments WHERE attempt=? AND sequence=?',(attempt,sequence)).fetchone()
            if old:
                if old[0]!=payload:raise ValueError('Conflicting staged segment')
                return
            used=self.db.execute('SELECT COALESCE(SUM(length(CAST(payload AS BLOB))),0) FROM retry_segments WHERE attempt=?',(attempt,)).fetchone()[0]
            if used+len(payload.encode())>MAX_STAGE_BYTES:raise ValueError('Retry staging budget exceeded')
            self.db.execute('INSERT INTO retry_segments VALUES(?,?,?)',(attempt,sequence,payload))
    def finish(self,attempt,expected_count,source_digest=None):
        if source_digest is not None and (not isinstance(source_digest,str) or len(source_digest)!=64 or any(c not in '0123456789abcdef' for c in source_digest)):raise ValueError('Invalid retry source digest')
        if type(expected_count)!=int or not 1<=expected_count<=10000:raise ValueError('Explicit complete segment count required')
        with self.transaction():
            old=self.db.execute('SELECT state FROM retry_attempts WHERE id=?',(attempt,)).fetchone()
            if old and old[0]=='complete':return False
            row=self.active(attempt);mid=row['meeting'];self.protected(mid)
            if self.snapshot(mid)!=row['baseline']:raise ValueError('Meeting changed during retry')
            count,minimum,maximum=self.db.execute('SELECT COUNT(*),MIN(sequence),MAX(sequence) FROM retry_segments WHERE attempt=?',(attempt,)).fetchone()
            if (count,minimum,maximum)!=(expected_count,0,expected_count-1):raise ValueError('Staged result is incomplete')
            self.db.execute('DELETE FROM segments WHERE meeting=?',(mid,))
            for staged in self.db.execute('SELECT payload FROM retry_segments WHERE attempt=? ORDER BY sequence',(attempt,)):
                data=json.loads(staged[0])
                self.db.execute('INSERT INTO segments(meeting,start,end,source,speaker,speaker_name,payload) VALUES(?,?,?,?,?,?,?)',
                    (mid,data['start'],data['end'],data['source'],data['speaker'],data['speaker_name'],staged[0]))
            meta=metadata(self.meeting(mid));meta.pop('retry_attempt',None);meta['provisional']=False
            if source_digest is not None:meta['retry_source_digest']=source_digest
            self.db.execute("UPDATE meetings SET status='complete',metadata=? WHERE id=?",(json.dumps(meta),mid))
            self.db.execute("UPDATE retry_attempts SET state='complete' WHERE id=?",(attempt,))
            self.db.execute('DELETE FROM retry_segments WHERE attempt=?',(attempt,));return True
    def abort(self,attempt):
        with self.transaction():
            row=self.db.execute('SELECT * FROM retry_attempts WHERE id=?',(attempt,)).fetchone()
            if row is None or row['state']!='running':return False
            meeting=self.meeting(row['meeting']);meta=metadata(meeting)
            if meta.get('retry_attempt')==attempt and meeting['status']=='processing':
                meta.pop('retry_attempt',None)
                self.db.execute("UPDATE meetings SET status='incomplete',metadata=? WHERE id=?",(json.dumps(meta),row['meeting']))
            self.db.execute("UPDATE retry_attempts SET state='aborted' WHERE id=?",(attempt,))
            self.db.execute('DELETE FROM retry_segments WHERE attempt=?',(attempt,));return True
