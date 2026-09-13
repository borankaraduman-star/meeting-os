"""Versioned analysis and durable task state on the existing local SQLite store."""
import json
from datetime import datetime,timezone
from .intelligence import action_conflict,fingerprint
from .metrics import normalize

STOPWORDS={'ve','bir','bu','şu','o','ne','kaç','mi','mı','mu','mü','ile','için','de','da','ki','ama','veya','ya','gibi','çok','daha','en','var','yok','mi','nasıl','neden','hangi','kim','nerede','zaman','olan','oldu','olduğu','söylendi','söyledi','söylemiş','dedi','diye','ise','hakkında','bana','bize','şey'}


RETIRED=('dismissed','superseded')   # a task the user removed by hand, or one a newer analysis of the same meeting left behind
# The Turkish word for every task state, in one place: the digest, the share preview and the analysis export
# used to keep their own copies, and an export that printed the raw 'in_progress' was the proof they drifted.
STATE_LABELS={'open':'açık','in_progress':'devam ediyor','done':'tamamlandı','dismissed':'kaldırıldı','superseded':'yenilendi'}

def state_label(state):
    return STATE_LABELS.get(state,state)

def owner_key(name):
    """Loose match for a person's name: case, İ/I/ı and diacritics do not separate "İlker", "Ilker" and "ilker".
    `metrics.normalize` keeps ı and i apart (right for word error rates, wrong for a name typed two ways).

    The name this side of the code knows the rule by; `store.fold_name` is the rule."""
    from .store import fold_name
    return fold_name(name)

def rename_task_owners(db,old,new,meeting=None,segments=None):
    """Move the tasks of a person whose label just changed onto the new spelling. Returns how many moved.

    Renaming a speaker used to relabel the transcript only: the tasks kept the old label, so "Bana ait"
    and the waiting board went on answering with a name that no longer exists anywhere in the meeting.
    Only rows the user has never edited by hand are touched — a hand-typed owner outranks any rename —
    and matching is `owner_key`, so 'Ilker'/'İlker' is one person. `meeting` limits it to one meeting
    (a diarized cluster is local to its meeting); `segments` limits it further to tasks whose evidence
    comes only from those segment ids (one pinned piece of a cluster)."""
    old=(old or '').strip();new=(new or '').strip();key=owner_key(old)
    if not key or not new or key==owner_key(new):return 0
    if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone():return 0
    sql='SELECT id,owner,payload FROM tasks WHERE user_edited=0 AND owner IS NOT NULL';args=()
    if meeting is not None:sql+=' AND meeting=?';args=(meeting,)
    moved=0
    for row in db.execute(sql,args).fetchall():
        if owner_key(row['owner'])!=key:continue
        if segments is not None:
            try:evidence=(json.loads(row['payload'] or '{}') or {}).get('evidence') or []
            except ValueError:continue
            ids={e.get('segment_id') for e in evidence if isinstance(e,dict)}
            if not ids or not ids<=set(segments):continue
        db.execute('UPDATE tasks SET owner=?,updated=? WHERE id=?',(new,now(),row['id']));moved+=1
    return moved

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

def score_and_hits(terms,text):
    """(score, how many of the asked terms appear at all). The score is exactly what it always was — the hit
    count is only a tie-break, so among equally scored segments the one that covers two of the asked words
    beats the one that says a single word twice. No pair that was ordered before is reordered by it."""
    words=normalize(text).split()
    if not words:return 0.0,0
    total=0.0;hits=0
    for term in terms:
        best=max((_stem_match(term,w) for w in words),default=0.0)
        total+=best
        if best:hits+=1
    return total,hits

def _title_tokens(text):
    # Short tokens are dropped as noise — except numbers: "10 Ekim" and "15 Ekim" are two different deadlines.
    return {w for w in normalize(text or '').split() if len(w)>2 or any(c.isdigit() for c in w)}

def dedupe_actions(actions,threshold=0.8):
    """One analysis that promised the same thing twice is one commitment, not two.

    Chunks are analysed independently and `duplicate_index` only catches a restatement that contains
    the other; two wordings of the same promise ("Eğitimleri evde çocuklarla vakit geçirirken vermek")
    both survived and the meeting counted the same task twice in the digest and the karne. Near-identical
    titles (normalized token Jaccard) collapse onto the wording with more evidence — the one a reader can
    check against the transcript. Two different people promising a similar thing are two commitments, so
    the owners have to agree (or both be missing). Nothing else about the item is merged.

    One promise carrying two different deadlines is also two promises ("pazartesi" and "cuma"), and so
    is one carrying two different quantities: those stay apart however alike the titles read, and the
    doubt from either of them is carried onto both so the pair stays visible (Codex #5)."""
    kept=[]
    for item in actions:
        tokens=_title_tokens(item.get('title'))
        for index,(other,other_tokens) in enumerate(kept):
            if owner_key(item.get('owner'))!=owner_key(other.get('owner')):continue
            union=tokens|other_tokens
            # A Jaccard verdict over three tokens is a coin toss; short titles must match exactly.
            same=len(tokens&other_tokens)/len(union)>=threshold if len(union)>=4 else normalize(item.get('title') or '')==normalize(other.get('title') or '')
            if not same:continue
            if action_conflict(item,other):
                if item.get('needs_review') or other.get('needs_review'):item['needs_review']=other['needs_review']=True
                continue
            winner,loser=(item,other) if len(item.get('evidence') or [])>len(other.get('evidence') or []) else (other,item)
            # Merge, never drop: the loser's quotes, a deadline the winner lacked, and a trace of what was folded in.
            seen={(e.get('segment_id'),e.get('quote')) for e in winner.get('evidence') or []}
            winner['evidence']=list(winner.get('evidence') or [])+[e for e in loser.get('evidence') or [] if (e.get('segment_id'),e.get('quote')) not in seen]
            if not (winner.get('due_text') or '').strip() and (loser.get('due_text') or '').strip():winner['due_text']=loser['due_text']
            if not (winner.get('owner') or '').strip() and (loser.get('owner') or '').strip():winner['owner']=loser['owner']
            winner.setdefault('merged_from',[]).append(loser.get('title'))
            kept[index]=(winner,tokens|other_tokens)
            break
        else:kept.append((item,tokens))
    return [item for item,_ in kept]

EDIT_REASONS=('inference_error','changed_later')
# Why the user changed a task field, when they said so. "Model yanlış çıkardı" and "iş sonradan devredildi"
# look identical in the data and mean opposite things for learning: one is a model error, the other is the
# meeting doing what meetings do. Unknown stays unknown — a change with no reason is never a training label.

def _edit_reason(reason):
    if reason is None or reason=='':return None
    if reason not in EDIT_REASONS:raise ValueError('Geçersiz düzenleme nedeni')
    return reason


def same_task(a_title,a_owner,b_title,b_owner,threshold=0.8):
    """Is this the same commitment, worded differently? The rule `dedupe_actions` already uses: the owners have
    to agree (or both be missing) and the normalized title tokens have to overlap; a title short enough that a
    Jaccard verdict would be a coin toss has to match exactly."""
    if owner_key(a_owner or '')!=owner_key(b_owner or ''):return False
    a,b=_title_tokens(a_title),_title_tokens(b_title)
    union=a|b
    if len(union)>=4:return len(a&b)/len(union)>=threshold
    return normalize(a_title or '')==normalize(b_title or '') and bool(union)


def decision_restatement(before,after):
    """A title match strong enough to inherit a human edit or dismissal, not just the same topic.
    Reject changed facts, negative imperatives, and added claims. Ordinary inflection may still match."""
    from .intelligence import stems
    from .preferences import classify_edit
    if normalize(before or '')==normalize(after or ''):return True
    if classify_edit(before,after)=='factual':return False
    old_words,new_words=set(normalize(before or '').split()),set(normalize(after or '').split())
    # The style classifier handles finite negation, but "onayla" → "onaylama" / "gönder" →
    # "gönderme" is an imperative. Their five-letter stems are identical and cannot establish identity.
    for old in old_words-new_words:
        for new in new_words-old_words:
            if new in (old+'ma',old+'me') or old in (new+'ma',new+'me'):return False
    old_stems,new_stems=stems(before),stems(after)
    added,removed=new_stems-old_stems,old_stems-new_stems
    # "hemen gönder" is the existing harmless rewording case; a new object or clause is not.
    added-= {'hemen'};removed-= {'hemen'}
    return bool(added)==bool(removed) and len(added)<=1 and len(removed)<=1


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
        -- The user's layer over the model's summary: one row per (item, action). Local only; the wording a
        -- person typed about their own meeting never leaves this Mac.
        CREATE TABLE IF NOT EXISTS insight_edits(id INTEGER PRIMARY KEY,meeting TEXT,item_id TEXT,section TEXT,action TEXT,text TEXT,reason TEXT,created TEXT,analysis_version INTEGER);
        CREATE UNIQUE INDEX IF NOT EXISTS insight_edits_item ON insight_edits(meeting,item_id,action);
        CREATE INDEX IF NOT EXISTS analyses_meeting ON analyses(meeting,id);
        CREATE INDEX IF NOT EXISTS tasks_meeting ON tasks(meeting,updated);
        CREATE INDEX IF NOT EXISTS task_edits_task ON task_edits(task);
        CREATE INDEX IF NOT EXISTS drafts_task ON drafts(task);
        ''')
        # `reason` is the user's own answer to "why did this change?" — 'inference_error' or 'changed_later',
        # and None when they did not say. A change with no reason is never turned into a training label
        # (Codex, 11 Sep 2026, P0 #3). `carried_from` names the task id a history row was copied from when a
        # re-analysis reworded the same commitment into a new id.
        columns={r[1] for r in self.db.execute('PRAGMA table_info(task_edits)')}
        for name in ('reason','carried_from','field'):
            if name in columns: continue
            try:self.db.execute(f'ALTER TABLE task_edits ADD COLUMN {name} TEXT')
            except Exception:pass   # another process migrated first
        self._hashes={};self._analyses={};self._writes=self.db.total_changes
        self._data_version=self.db.execute('PRAGMA data_version').fetchone()[0]
    def _memo(self):
        """One report asks for the same meeting again and again, and each ask used to reread the whole transcript.
        The answers are kept until this connection writes or another connection commits a change. The
        desktop bridge and analysis worker open separate connections to the same database."""
        data_version=self.db.execute('PRAGMA data_version').fetchone()[0]
        if self._writes!=self.db.total_changes or data_version!=self._data_version:
            self._writes=self.db.total_changes;self._hashes.clear();self._analyses.clear()
            self._data_version=data_version
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
        d=dict(row);d['payload']=json.loads(d['payload']);d['stale']=d['input_hash']!=self.current_hash(mid)
        # Everything that reads an analysis — the app, the export, the decision log — reads it through here,
        # so this is the one place the user's corrections and removals have to be laid over the model's
        # output. An analysis saved before item ids existed gets them here, deterministically.
        from .insight_layer import layered
        d['payload'],d['insight_unmatched']=layered(self.store,mid,d['payload'])
        return d
    def raw_payload(self,mid):
        """The model's own output for this meeting, without the user layer — what a re-analysis matches against."""
        row=self.db.execute('SELECT payload FROM analyses WHERE meeting=? ORDER BY id DESC LIMIT 1',(mid,)).fetchone()
        if not row:return None
        from .intelligence import ensure_item_ids
        return ensure_item_ids(json.loads(row['payload'] or '{}'))
    def _task_predecessors(self,fresh,previous):
        """Match only a unique, source-backed restatement, using the model's original fields as well as
        the user's wording. A corrected owner must not prevent us preserving that very correction."""
        from .intelligence import evidence_ids
        candidates={}
        for tid,item in fresh:
            matches=[]
            for old in previous:
                if old['id']==tid or old['state']=='superseded':continue
                model=json.loads(old['payload'] or '{}')
                model.pop('due_date',None)   # approved calendar dates are the user's layer, not source wording
                if not (evidence_ids(item)&evidence_ids(model)):continue
                if action_conflict(item,model):continue
                same_source=(normalize(item.get('title') or '')==normalize(model.get('title') or '') and
                             [(e.get('segment_id'),e.get('quote')) for e in item.get('evidence') or []]==
                             [(e.get('segment_id'),e.get('quote')) for e in model.get('evidence') or []])
                if same_source and owner_key(item.get('owner'))!=owner_key(model.get('owner')):
                    continue   # colliding source commitments remain distinct even if a human later assigns both to one person
                same=any(same_task(item.get('title'),item.get('owner'),title,owner)
                         and decision_restatement(title,item.get('title'))
                         for title in (model.get('title'),old['title'])
                         for owner in (model.get('owner'),old['owner']))
                if same:matches.append(old)
            if len(matches)==1:candidates[tid]=matches[0]
        # One old promise cannot donate its decisions to two new promises.
        uses={}
        for old in candidates.values():uses[old['id']]=uses.get(old['id'],0)+1
        return {tid:old for tid,old in candidates.items() if uses[old['id']]==1}
    def _carry_history(self,matched):
        """A re-analysis that rewords the same commitment writes a NEW task id (the id is the hash of the title
        and its quotes), and the user's edit history stayed behind on the id nobody looks at any more. The
        history follows the task: every `task_edits` row of the closest previous wording is copied onto the new
        id with `carried_from` set, so "this owner was corrected once already" survives a re-analysis.

        Must run inside the caller's transaction, using the same unambiguous match as the field transfer."""
        carried=0
        for tid,match in matched.items():
            for row in self.db.execute('SELECT previous,replacement,created,reason,field FROM task_edits WHERE task=? ORDER BY id',(match['id'],)).fetchall():
                # A previous wording may return later. Do not copy its own earlier events back onto it.
                if self.db.execute('SELECT 1 FROM task_edits WHERE task=? AND previous IS ? AND replacement IS ? AND created IS ? AND reason IS ? AND field IS ? LIMIT 1',
                                   (tid,row['previous'],row['replacement'],row['created'],row['reason'],row['field'])).fetchone():continue
                self.db.execute('INSERT INTO task_edits(task,previous,replacement,created,reason,field,carried_from) VALUES(?,?,?,?,?,?,?)',
                    (tid,row['previous'],row['replacement'],row['created'],row['reason'],row['field'],match['id']))
                carried+=1
        return carried
    def _edited_fields(self,old):
        history=self.db.execute('SELECT field FROM task_edits WHERE task=?',(old['id'],)).fetchall()
        fields={field for row in history for field in (row['field'] or '').split(',')}
        if old['user_edited'] and (not history or any(not row['field'] for row in history)):
            fields.update(('title','owner','due_text','due_date')) # legacy edits did not identify fields
        return fields
    def _carry_decision(self,tid,old):
        """Carry only fields the person actually edited, including an explicitly cleared date, and state.
        Keep the old row for history, retired so the same promise is not displayed twice."""
        fields=self._edited_fields(old)
        changes={key:old[key] for key in ('title','owner','due_text') if key in fields}
        changes['state']=old['state'];changes['user_edited']=old['user_edited']
        if 'due_date' in fields:
            payload=json.loads(self.db.execute('SELECT payload FROM tasks WHERE id=?',(tid,)).fetchone()[0])
            date=json.loads(old['payload'] or '{}').get('due_date')
            if date is None:payload.pop('due_date',None)
            else:payload['due_date']=date
            changes['payload']=json.dumps(payload,ensure_ascii=False)
        self.db.execute('UPDATE tasks SET '+','.join(key+'=?' for key in changes)+' WHERE id=?',(*changes.values(),tid))
        self.db.execute("UPDATE tasks SET state='superseded',updated=? WHERE id=?",(now(),old['id']))
    def _task_ids(self,mid,items,previous):
        """Keep the old title/quote ID unless two commitments collide. Disambiguate by source owner/date,
        reserving a legacy ID for the model fields already stored there, never the human-edited owner.
        Previously allocated alternatives remain stable when only one member appears in a later analysis."""
        import hashlib
        def base(item):
            stable=json.dumps([mid,normalize(item.get('title') or ''),[(e['segment_id'],e['quote']) for e in item.get('evidence') or []]],ensure_ascii=False,sort_keys=True)
            return hashlib.sha256(stable.encode()).hexdigest()[:20]
        def identity(item):return owner_key(item.get('owner')),normalize(item.get('due_text') or '')
        def alternate(key,signature):
            value=json.dumps(['task-collision',key,signature],ensure_ascii=False)
            return hashlib.sha256(value.encode()).hexdigest()[:20]
        groups={}
        for item in items:groups.setdefault(base(item),[]).append(item)
        known={p['id']:p for p in previous};families=set();models={}
        for old in previous:
            model=json.loads(old['payload'] or '{}');models[old['id']]=model
            key=base(model)
            if old['id']==alternate(key,identity(model)):families.add(key)
        out=[]
        for key,group in groups.items():
            signatures={identity(item) for item in group}
            collision=len(signatures)>1 or key in families
            reserved=identity(models[key]) if key in models else min(signatures)
            for item in group:
                signature=identity(item);other=alternate(key,signature)
                tid=other if other in known or (collision and signature!=reserved) else key
                out.append((tid,item))
        return out
    def save_analysis(self,mid,input_hash,model,record):
        from .intelligence import ensure_item_ids
        record={**record,'actions':dedupe_actions(record['actions'])}   # the same promise, worded twice in one analysis, is stored once
        # A summary item the user corrected, removed or approved is identified by `item_id`. Carrying the ids
        # of the analysis this one replaces is what re-attaches those decisions: a bullet that reappears —
        # reworded or not — keeps its identity, and only a genuinely new claim gets a new one.
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.current_hash(mid)!=input_hash:raise ValueError('Transkript analiz sırasında değişti; yeniden analiz edin')
            # merge_records already assigned deterministic IDs. They must be rematched to the previous
            # analysis here, under the same write lock as the transcript/version check.
            ensure_item_ids(record,self.raw_payload(mid),rematch=True)
            previous=[dict(r) for r in self.db.execute('SELECT * FROM tasks WHERE meeting=? ORDER BY created DESC',(mid,))]
            known={p['id']:p for p in previous};fresh=[];restated=set()
            aid=self.db.execute('INSERT INTO analyses(meeting,input_hash,model,payload,created) VALUES(?,?,?,?,?)',(mid,input_hash,model,json.dumps(record,ensure_ascii=False),now())).lastrowid
            for tid,item in self._task_ids(mid,record['actions'],previous):
                restated.add(tid)
                if tid not in known or known[tid]['state']=='superseded':fresh.append((tid,item))
                values={key:item.get(key) for key in ('title','owner','due_text')}
                if tid in known and known[tid]['user_edited']:
                    fields=self._edited_fields(known[tid])
                    values.update({key:known[tid][key] for key in values if key in fields})
                self.db.execute('''INSERT INTO tasks(id,meeting,analysis,input_hash,title,owner,due_text,state,payload,created,updated) VALUES(?,?,?,?,?,?,?,'open',?,?,?)
                ON CONFLICT(id) DO UPDATE SET analysis=excluded.analysis,input_hash=excluded.input_hash,payload=json_patch(excluded.payload,json_object('due_date',json_extract(tasks.payload,'$.due_date'),'superseded_by',json_extract(tasks.payload,'$.superseded_by'),'continues',json_extract(tasks.payload,'$.continues'))),title=excluded.title,owner=excluded.owner,due_text=excluded.due_text,state=CASE WHEN tasks.state='superseded' THEN 'open' ELSE tasks.state END''',(tid,mid,aid,input_hash,values['title'],values['owner'],values['due_text'],json.dumps(item,ensure_ascii=False),now(),now()))
            # A task id is the hash of its title and its quotes, so a re-analysis that words the same commitment
            # differently writes a NEW row and the old one stayed open forever: the same promise counted twice in
            # the digest and the karne. What this analysis did not restate is retired, never deleted — a task the
            # user touched (edited, closed, dismissed) is theirs and survives.
            # …but only when this analysis actually restated the meeting's commitments: an analysis that came back with
            # no actions (a thin model answer, an over-strict quote check) must not sweep every open task out of sight.
            if record.get('actions'):
                self.db.execute("UPDATE tasks SET state='superseded',updated=? WHERE meeting=? AND analysis IS NOT NULL AND analysis<? AND user_edited=0 AND state='open'",(now(),mid,aid))   # in_progress/done: the user touched it, it stays
            matched=self._task_predecessors(fresh,[p for p in previous if p['id'] not in restated])
            for tid,old in matched.items():self._carry_decision(tid,old)
            self._carry_history(matched)
        return self.latest(mid)
    def set_due_date(self,tid,due_date,reason=None):
        """Store an approved calendar date (ISO, or None to clear) inside the task payload; due_text stays as the source said it.

        Approving, changing or clearing the calendar date writes the SAME `task_edits` history row every other
        field writes. It did not before: `set_due_date` moved the date and set `user_edited=1` and left no
        trace, so the one field the user confirms most often was the one field with no history — and "the
        model read the date wrong" could not be told apart from "the deadline moved" (Codex P0 #3)."""
        reason=_edit_reason(reason)
        row=self.db.execute('SELECT payload FROM tasks WHERE id=?',(tid,)).fetchone()
        if not row:raise ValueError('Görev bulunamadı')
        payload=json.loads(row['payload'] or '{}')
        previous=payload.get('due_date')
        if due_date: payload['due_date']=str(due_date)[:10]
        else: payload.pop('due_date',None)
        old=self.task(tid)
        with self.db:
            self.db.execute('UPDATE tasks SET payload=?,user_edited=1,updated=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),now(),tid))
            self.db.execute('INSERT INTO task_edits(task,previous,replacement,created,reason,field) VALUES(?,?,?,?,?,?)',
                (tid,json.dumps({**old,'due_date':previous},ensure_ascii=False),json.dumps({'due_date':payload.get('due_date')},ensure_ascii=False),now(),reason,'due_date'))
        return payload.get('due_date')
    def actions(self,owner=None,meeting=None):
        result=[];latest_ids={r['meeting']:r['id'] for r in self.db.execute('SELECT meeting,MAX(id) AS id FROM analyses GROUP BY meeting')}
        for row in self.db.execute('SELECT tasks.*,meetings.title AS meeting_title FROM tasks JOIN meetings ON meetings.id=tasks.meeting ORDER BY tasks.created DESC'):
            d=dict(row)
            if owner and owner_key(d['owner'] or '')!=owner_key(owner):continue
            if meeting and d['meeting']!=meeting:continue
            d['payload']=json.loads(d['payload'])
            d['stale']=d['input_hash']!=self.current_hash(d['meeting']) or d['analysis']!=latest_ids.get(d['meeting']);result.append(d)
        return result
    def task(self,tid):
        rows=[r for r in self.actions() if r['id']==tid]
        if not rows:raise ValueError('Görev bulunamadı')
        return rows[0]
    def update_action(self,tid,changes,reason=None):
        reason=_edit_reason(reason)
        if not changes or set(changes)-{'state','title','owner','due_text'}:raise ValueError('Geçersiz görev değişikliği')
        if 'state' in changes and changes['state'] not in ('open','in_progress','done','dismissed'):raise ValueError('Geçersiz görev durumu')
        for key in ('title','owner','due_text'):
            if key in changes:
                if changes[key] is not None and (not isinstance(changes[key],str) or len(changes[key])>1600):raise ValueError('Geçersiz görev alanı')
                if key=='title' and not (changes[key] or '').strip():raise ValueError('Görev başlığı boş olamaz')
        old=self.task(tid)
        with self.db:
            # Ticking "tamamlandı" is not an edit: only a changed title/owner/due makes the task the user's own wording
            # (which renames and re-analyses then leave alone). A state change keeps following the transcript.
            edited=1 if set(changes)&{'title','owner','due_text'} else None
            self.db.execute('UPDATE tasks SET '+','.join(k+'=?' for k in changes)+',user_edited=COALESCE(?,user_edited),updated=? WHERE id=?',(*changes.values(),edited,now(),tid))
            self.db.execute('INSERT INTO task_edits(task,previous,replacement,created,reason,field) VALUES(?,?,?,?,?,?)',
                (tid,json.dumps(old,ensure_ascii=False),json.dumps(changes,ensure_ascii=False),now(),reason,','.join(sorted(changes))))
        return self.task(tid)
    def task_history(self,tid):
        """Every recorded change to one task, oldest first — including the rows carried over from the task id a
        re-analysis replaced (`carried_from`)."""
        return [dict(r) for r in self.db.execute('SELECT * FROM task_edits WHERE task=? ORDER BY id',(tid,))]
    def search(self,query,limit=20,speaker=None,owner=None):
        """Segments that answer `query`, best first. `speaker` filters by person the way every other report does
        (`owner_key`, and a microphone row is its label's owner), not by exact spelling of `speaker_name`.
        Ties are broken by how many of the asked words appear and then by the shorter segment: two segments
        with the same score are not equally useful, and the short one is the one a person can read."""
        from .intelligence import row_person
        tokens=query_terms(query)
        if not tokens:return []
        if owner is None:
            from .reports import store_owner
            owner=store_owner(self.store)
        rows=self.db.execute("SELECT segments.id,meeting,meetings.title AS meeting_title,start,end,source,speaker,speaker_name,json_extract(payload,'$.text') AS text FROM segments JOIN meetings ON meetings.id=segments.meeting WHERE meetings.status='complete' ORDER BY meetings.created DESC,start")
        wanted=owner_key(speaker or '')
        found=[]
        for r in rows:
            d=dict(r)
            if wanted and owner_key(row_person(d,owner) or '')!=wanted:continue
            score,hits=score_and_hits(tokens,d['text'] or '')
            if score:d['score']=score;d['hits']=hits;found.append(d)
        return sorted(found,key=lambda x:(-x['score'],-x['hits'],len(x['text'] or ''),x['id']))[:min(max(1,limit),50)]
