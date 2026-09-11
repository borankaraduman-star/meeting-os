"""Team-shared knowledge: the words this team taught and the voices it named, in the folder every Mac reads.

The glossary was already shared (`glossary.shared_path`, `glossary.merge_into`). The two things that were not
are the words a person taught by hand (`taught_words`) and the voice profiles they enrolled (`samples`): they
stayed on the Mac that learned them, so three people using this app corrected the same word three times and
named the same colleague three times. The team folder is one knowledge base: every Mac writes what it learned
into it and reads back what the others learned.

Two files, both JSON Lines, both under the same shared root the glossary uses — `team_dir` when the user picked
a team folder, otherwise the iCloud `MeetingOS-Shared` folder, and iCloud only for the REAL data folder so that
tests and private copies never touch it:

    team-words.jsonl        one line per (host, taught word): original, replacement, host, created, updated
    profiles/<host>.jsonl   one line per published voice sample: name, model, vector, duration, created, host

Neither file ever carries audio, transcript text, meeting ids or meeting titles. A vector is a unit embedding:
it tells one voice from another, it does not play back and it cannot be turned into speech.

Conflicts. Words are keyed by (host, folded original), so two Macs never overwrite each other's line and a
publish never drops a teammate's. When two hosts teach the same word differently the local Mac's own rule wins
silently. When there is no local rule, neither teammate wins: the newest line used to, which let one Mac's clock
decide how a colleague's name is written here, so the disagreement is now a Kontrol question ("Ekipte iki yazım:
X / Y — hangisi?") and the answer is taught locally. Both are still listed in Ayarlar → Sesler ve sözlük with the
Mac that taught them, and either can be switched off row by row (`team_words.enabled`) without changing what the
other Mac shares. A voice sample is keyed by its own content hash, so importing the same file twice adds
nothing, and a local sample is never overwritten — the per-person cap is filled by this Mac's own samples first.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .correction_memory import _fold, taught_rules
from .glossary import ICLOUD, SHARED_DIR, REAL_DATA_DIR
from .reports import host_name, publish, team_dir, SHARED_DIR_MODE
from .store import cosine, fold_name, unit

WORDS_FILE = 'team-words.jsonl'
PROFILES_DIR = 'profiles'
MAX_WORDS = 2000          # a whole team's taught vocabulary; past this the file is somebody's export, not a habit
PROFILE_CAP = 8           # samples per person, the same bound `add_sample_if_new` keeps locally
MIN_DURATION = 3.0        # `store.enroll` refuses anything shorter, so publishing it would only create dead lines
VECTOR_DIGITS = 6         # rounded so the same sample hashes the same on every Mac and the file stays small
NAME_LIMIT = 80


def _now():
    return datetime.now(timezone.utc).isoformat()


def shared_root(settings, data_dir=None):
    """Where the team's shared files live, or None. Same resolution as the shared glossary: the team folder the
    user picked, otherwise iCloud Drive — and iCloud only when this really is the app's data folder, so a test
    or a private copy of the database never writes into the user's own iCloud."""
    team = team_dir(settings)
    if team: return team
    if data_dir is None: return None
    try: is_real = Path(data_dir).resolve() == REAL_DATA_DIR.resolve()
    except OSError: is_real = False
    return SHARED_DIR if is_real and ICLOUD.is_dir() else None


def words_path(settings, data_dir=None):
    root = shared_root(settings, data_dir)
    return root / WORDS_FILE if root else None


def profiles_dir(settings, data_dir=None):
    root = shared_root(settings, data_dir)
    return root / PROFILES_DIR if root else None


def profile_path(settings, data_dir=None, host=None):
    directory = profiles_dir(settings, data_dir)
    return directory / f'{host or host_name()}.jsonl' if directory else None


def _write(path, lines, root=None):
    """Atomic, teammate-readable write. The file lands through a temp file + rename, so a teammate reading at that
    moment never sees half a file, and at mode 0644, so they can open it at all. A folder this module CREATES
    (`profiles/`) is made listable too — the bridge runs under umask 077, which would otherwise leave it 0700 and
    no teammate could list it. The team folder the user picked is never chmod'ed: its permissions are theirs."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if root is None or path.parent != Path(root):
        try: path.parent.chmod(SHARED_DIR_MODE)
        except OSError: pass   # a network volume or a synced folder may refuse; sharing still works
    publish(path, ''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in lines), shared=True)
    return path


def _clean(value, limit=120):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


# ---------------------------------------------------------------- words

def parse_word(line):
    """One line of team-words.jsonl, or None. Everything an outsider to this Mac writes goes through here."""
    try: d = json.loads(line)
    except ValueError: return None
    if not isinstance(d, dict): return None
    original = _clean(d.get('original')); replacement = _clean(d.get('replacement')); host = _clean(d.get('host'), 64)
    if not original or not replacement or not host: return None
    return {'original': original, 'replacement': replacement, 'host': host,
            'created': _clean(d.get('created'), 40) or '', 'updated': _clean(d.get('updated'), 40) or ''}


def read_words(path):
    path = Path(path)
    if not path.is_file(): return []
    out = []; seen = set()
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        e = parse_word(line)
        if not e: continue
        key = (e['host'], _fold(e['original']))
        if key in seen: continue
        seen.add(key); out.append(e)
    return out[:MAX_WORDS]


def _ensure_words(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS team_words(host TEXT, folded TEXT, original TEXT, replacement TEXT,'
                     ' created TEXT, updated TEXT, enabled INTEGER DEFAULT 1, PRIMARY KEY(host,folded))')


def publish_words(store, settings, data_dir=None):
    """Write this Mac's taught words into the shared file. Every other host's line is read back first and kept
    exactly as it was: a publish here must never delete what a teammate taught. A word this Mac has forgotten is
    simply no longer among its taught rules, so the same pass takes its own line out."""
    path = words_path(settings, data_dir)
    if path is None or settings.get('share_words') is False: return {'published': 0, 'path': None}
    host = host_name()
    others = []; mine = {}
    for e in read_words(path):
        if e['host'] == host: mine[_fold(e['original'])] = e
        else: others.append(e)
    now = _now(); lines = []
    for r in taught_rules(store):
        key = _fold(r['original']); previous = mine.get(key)
        # `updated` only moves when the rule actually changed: an hourly publish that rewrites every timestamp
        # would make the file look new to every teammate on every pass.
        changed = previous is None or previous['replacement'] != r['replacement']
        lines.append({'original': r['original'], 'replacement': r['replacement'], 'host': host,
                      'created': (previous or {}).get('created') or r.get('created') or now,
                      'updated': now if changed else previous['updated']})
    entries = (lines + others)[:MAX_WORDS]
    # Nothing changed → nothing is written: an hourly publish that rewrites an unchanged file wakes every
    # teammate's sync client for no reason. Order is not content here, so the comparison is by key.
    if _by_key(read_words(path)) == _by_key(entries): return {'published': len(lines), 'path': str(path), 'unchanged': True}
    _write(path, entries, root=shared_root(settings, data_dir))
    return {'published': len(lines), 'path': str(path), 'total': len(entries)}


def _by_key(entries):
    return {(e['host'], _fold(e['original'])): (e['replacement'], e['created'], e['updated']) for e in entries}


def pull_words(store, settings, data_dir=None):
    """Import the other Macs' taught words into `team_words`. A row the user switched off stays off, and a word a
    teammate has forgotten (their line is gone) is dropped here too — their file is the truth about their words."""
    path = words_path(settings, data_dir)
    if path is None or settings.get('share_words') is False or not path.is_file(): return {'imported': 0, 'hosts': 0}
    host = host_name()
    entries = [e for e in read_words(path) if e['host'] != host]
    _ensure_words(store)
    existing = {(r['host'], r['folded']): r for r in store.db.execute('SELECT * FROM team_words')}
    seen = set(); imported = 0
    with store.db:
        for e in entries:
            key = (e['host'], _fold(e['original'])); seen.add(key)
            previous = existing.get(key)
            enabled = 1 if previous is None else (previous['enabled'] if previous['enabled'] is not None else 1)
            if previous and previous['replacement'] == e['replacement'] and previous['original'] == e['original']: continue
            store.db.execute('INSERT OR REPLACE INTO team_words(host,folded,original,replacement,created,updated,enabled) VALUES(?,?,?,?,?,?,?)',
                             (e['host'], key[1], e['original'], e['replacement'], e['created'] or _now(), e['updated'] or _now(), enabled))
            imported += 1
        # One file holds every host's words, so a word that is not in it is a word nobody shares any more —
        # that is how a teammate's `forget` reaches this Mac. A file that is missing entirely deletes nothing
        # (the branch above returns before this), so an unmounted share never wipes what the team taught.
        for key in existing:
            if key not in seen and key[0] != host: store.db.execute('DELETE FROM team_words WHERE host=? AND folded=?', key)
    return {'imported': imported, 'hosts': len({e['host'] for e in entries})}


def team_rules(store):
    """Every team word this Mac knows about, including the ones it is not applying. `active` says which rule is
    the one that actually rewrites text; the loser is still listed — otherwise "why is it writing Ayşen?" has no
    answer on screen.

    Who wins:

    * **This Mac's own rule always wins, silently.** A word the user taught here is not a vote; nothing a
      teammate publishes overrules what the person sitting in front of this screen typed.
    * **Two teammates, two different spellings, nothing local → nobody wins.** Picking the newest line was one
      Mac's clock deciding how this Mac writes a colleague's name, and the loser was invisible unless the user
      went looking in Ayarlar. Both rows are marked `conflict` and neither rewrites anything; the question goes
      to Kontrol as "Ekipte iki yazım: X / Y — hangisi?" and the answer teaches a local rule, which then wins
      by the first bullet (Codex, 11 Sep 2026, #7).
    * **Two teammates who agree** are not a conflict: the same spelling from two Macs still applies, newest line
      first, exactly as before."""
    _ensure_words(store)
    local = {_fold(r['original']) for r in taught_rules(store)}
    rows = []
    for r in store.db.execute('SELECT * FROM team_words ORDER BY original,host'):
        rows.append({'original': r['original'], 'replacement': r['replacement'], 'source': 'team', 'host': r['host'],
                     'folded': r['folded'], 'created': r['created'], 'updated': r['updated'],
                     'enabled': bool(r['enabled'] if r['enabled'] is not None else 1), 'count': 1, 'meetings': 0,
                     'vocabulary_added': False, 'active': False, 'conflict': False})
    groups = {}
    for r in rows:
        if not r['enabled'] or r['folded'] in local: continue
        groups.setdefault(r['folded'], []).append(r)
    for group in groups.values():
        if len({r['replacement'] for r in group}) > 1:
            for r in group: r['conflict'] = True
            continue
        max(group, key=lambda r: (r['updated'] or '', r['host']))['active'] = True
    return rows


def team_conflicts(store):
    """The words two teammates spell differently and this Mac has no rule of its own for. One entry per word,
    with every spelling on offer and the Mac behind it, and a `version` that changes when the offers do — so an
    answered question stays answered until the team actually changes its mind (`review.resolve_review` keys on
    it). Nothing here is a ban and nothing here is published: the answer becomes a LOCAL taught rule."""
    groups = {}
    for r in team_rules(store):
        if r.get('conflict'): groups.setdefault(r['folded'], []).append(r)
    out = []
    for folded, group in sorted(groups.items()):
        options = sorted(({'replacement': r['replacement'], 'host': r['host'], 'updated': r['updated'] or ''} for r in group),
                         key=lambda o: (o['replacement'], o['host']))
        out.append({'original': group[0]['original'], 'folded': folded, 'options': options,
                    'version': 'w:' + '|'.join(_fold(o['replacement']) for o in options)})
    return out


def applied_team_rules(store):
    """The team words that rewrite text on this Mac — exact spelling only, like every taught rule."""
    return [r for r in team_rules(store) if r['active']]


def team_word_toggle(store, original, host, enabled=True):
    """Switch one teammate's word off (or back on) for this Mac only. Their file is not touched: the user is
    saying "not here", not "unteach it for everyone"."""
    original = (original or '').strip(); host = (host or '').strip()
    if not original or not host: raise ValueError('Kelime ve Mac adı gerekli')
    _ensure_words(store)
    with store.db:
        cur = store.db.execute('UPDATE team_words SET enabled=? WHERE host=? AND folded=?', (1 if enabled else 0, host, _fold(original)))
    if not cur.rowcount: raise ValueError('Ekip kelimesi bulunamadı')
    return {'original': original, 'host': host, 'enabled': bool(enabled)}


def hint_terms(store):
    """The right spellings the team taught, for the ASR hint list. A word the team disagrees about is not in
    it: an unresolved conflict has no team spelling yet, only a question in Kontrol. Appended to the hint at load time and never
    written into `vocabulary.txt`: the file on this disk is the user's own list, not a copy of everyone else's."""
    try: return [r['replacement'] for r in applied_team_rules(store)]
    except Exception: return []


# ---------------------------------------------------------------- profiles

def _vector(values):
    return [round(v, VECTOR_DIGITS) for v in unit(values)]


def sample_hash(name, model, vector):
    """A voice sample's identity: who, which embedding model, and the rounded vector itself. Same sample, same
    hash on every Mac — that is what makes importing the same file twice add nothing."""
    body = f"{name}\n{model}\n" + ','.join(f'{v:.6f}' for v in vector)
    return hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]


def parse_profile(line):
    try: d = json.loads(line)
    except ValueError: return None
    if not isinstance(d, dict): return None
    name = _clean(d.get('name'), NAME_LIMIT); model = _clean(d.get('model'), 120); host = _clean(d.get('host'), 64)
    vector = d.get('vector'); duration = d.get('duration')
    if not name or not model or not isinstance(vector, list) or len(vector) < 8: return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vector): return None
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < MIN_DURATION: return None
    return {'name': name, 'model': model, 'vector': [float(v) for v in vector], 'duration': float(duration),
            'created': _clean(d.get('created'), 40) or '', 'host': host or ''}


def read_profiles(path):
    path = Path(path)
    if not path.is_file(): return []
    out = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        e = parse_profile(line)
        if e: out.append(e)
    return out


def publish_profiles(store, settings, data_dir=None):
    """Publish the voice samples this Mac made: a name, an embedding model, a unit vector and how many seconds of
    speech it came from. Never the audio, never the meeting it was cut from, never a title — a teammate gets the
    fingerprint that recognises the person and nothing that says where they were heard.

    Samples that arrived FROM the team (`provenance` starting with `team:`) are not re-published: every Mac
    publishes only what it learned itself, so a person's line has one owner and cannot echo around the folder.
    Samples the app produced by itself (`auto:`) are not published either: an automatic match is a guess this
    Mac was confident about, not a person saying "yes, that is her". Publishing guesses is how one Mac's wrong
    label becomes the team's: the other Macs import it, match more speech to it and publish that in turn. What
    travels is what a human named or confirmed; the automatic ones keep working locally, where they can be
    corrected by the person who can hear the difference."""
    if settings.get('share_profiles') is False: return {'published': 0, 'path': None}
    path = profile_path(settings, data_dir)
    if path is None: return {'published': 0, 'path': None}
    created = {sample_hash(e['name'], e['model'], e['vector']): e['created'] for e in read_profiles(path)}
    host = host_name(); now = _now()
    people = {}
    for r in store.db.execute('SELECT name,model,vector,duration,provenance FROM samples WHERE deleted_by IS NULL ORDER BY id'):
        if (r['provenance'] or '').startswith(('team:', 'auto:')): continue
        name = (r['name'] or '').strip(); duration = float(r['duration'] or 0)
        if not name or duration < MIN_DURATION: continue
        try: vector = _vector(json.loads(r['vector']))
        except (ValueError, TypeError, ZeroDivisionError): continue
        people.setdefault((name, r['model']), []).append({'name': name, 'model': r['model'], 'vector': vector,
                                                          'duration': round(duration, 1), 'host': host})
    lines = []
    for group in people.values():
        # The longest samples are the ones worth sharing: a teammate gets the clearest version of this voice.
        for e in sorted(group, key=lambda e: -e['duration'])[:PROFILE_CAP]:
            digest = sample_hash(e['name'], e['model'], e['vector'])
            lines.append({**e, 'created': created.get(digest) or now})
    if read_profiles(path) == lines: return {'published': len(lines), 'path': str(path), 'unchanged': True}
    _write(path, lines, root=shared_root(settings, data_dir))
    return {'published': len(lines), 'path': str(path), 'people': len(people)}


def forget_team_imports(store, reason='team-join'):
    """Everything a team's pulls put into THIS database, put away. Called when the Mac joins another team: what
    the old team taught must not follow it there, and must not be re-published to the new team as this Mac's
    own knowledge.

    Samples are soft-deleted (`deleted_by='<reason>:<utc>'`) — hidden from recognition, from the profile screen
    and from publishing, but not destroyed; a wrong `join` costs nothing that cannot be looked at again. Team
    words are deleted outright: `team_words` is a copy of a teammate's file, and the next pull rebuilds it.
    Local samples and locally taught words are never touched — they are this Mac's, not any team's."""
    mark = f'{reason}:{_now()}'
    _ensure_words(store)
    with store.db:
        samples = store.db.execute("UPDATE samples SET deleted_by=? WHERE deleted_by IS NULL AND provenance LIKE 'team:%'",
                                   (mark,)).rowcount
        words = store.db.execute('DELETE FROM team_words').rowcount
    return {'forgotten_samples': max(samples, 0), 'forgotten_words': max(words, 0)}


def _ensure_blocks(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS team_profile_blocks(name TEXT PRIMARY KEY, created TEXT)')


def blocked_profiles(store):
    """Folded names whose team samples this Mac has thrown away. Deleting a person has to survive the next pull,
    or the profile the user just deleted comes back an hour later."""
    _ensure_blocks(store)
    return {fold_name(r[0]) for r in store.db.execute('SELECT name FROM team_profile_blocks')}


def block_profile(store, name):
    name = (name or '').strip()
    if not name: return {'blocked': False}
    _ensure_blocks(store)
    with store.db: store.db.execute('INSERT OR REPLACE INTO team_profile_blocks VALUES(?,?)', (name, _now()))
    return {'blocked': True, 'name': name}


def unblock_profile(store, name):
    """Let the team's samples of this person in again; the next pull re-imports them."""
    _ensure_blocks(store)
    key = fold_name((name or '').strip())
    with store.db:
        for r in store.db.execute('SELECT name FROM team_profile_blocks').fetchall():
            if fold_name(r[0]) == key: store.db.execute('DELETE FROM team_profile_blocks WHERE name=?', (r[0],))
    return {'blocked': False, 'name': name}


def _rejection_vectors(store):
    """"That voice is not X", by folded name and embedding model. A rejection is about a VOICE — the user heard
    one sample and said it was somebody else — so it is stored, and has to be read back, as a vector."""
    out = {}
    for r in store.db.execute('SELECT name,model,vector FROM rejections'):
        try: vector = unit(json.loads(r['vector']))
        except (ValueError, TypeError, ZeroDivisionError): continue
        out.setdefault((fold_name(r['name']), r['model']), []).append(vector)
    return out


def _rejected(store, rejections, key, entry):
    """True when THIS sample is the voice the user said is not this person: same name, same model, and within
    `Store.REJECT_SIMILARITY` — the same bar local recognition uses (`store._scores`). A different voice under
    the same name is a different question, and the answer to it is not "no"."""
    vetoes = rejections.get((key, entry['model']))
    if not vetoes: return False
    try: vector = unit(entry['vector'])
    except (ValueError, TypeError, ZeroDivisionError): return False
    return any(len(v) == len(vector) and cosine(vector, v) >= store.REJECT_SIMILARITY for v in vetoes)


def _published_by_host(directory, host):
    """{publishing host: {sample hash: entry}} for every teammate file that could be READ. A file that is
    missing or unreadable is not in the result at all, so it cannot be mistaken for "that Mac published
    nothing" — an unmounted share must never look like a team that deleted everything."""
    published = {}
    for path in sorted(directory.glob('*.jsonl')):
        if path.stem == host: continue
        try: entries = read_profiles(path)
        except OSError: continue   # cannot read it → it says nothing → it removes nothing
        published.setdefault(path.stem, {})
        for e in entries:
            owner = e['host'] or path.stem
            published.setdefault(owner, {})[sample_hash(e['name'], e['model'], e['vector'])] = e
    return published


def _reconcile_profiles(store, published):
    """A host's file is the whole truth about what that host publishes, so a `team:<that host>:<hash>` sample
    this Mac holds and that host no longer lists is soft-deleted here. That is how a correction, a deletion or
    a ⌘Z on the Mac that taught the voice reaches everybody else — until this existed, one wrong "that is Ayşe"
    spread through the team and could never be taken back.

    Soft, never destructive (`deleted_by='team-sync:<utc>'`), and only ever `team:` rows: a sample this Mac
    recorded itself is its own, whatever any teammate's file says."""
    if not published: return 0
    mark = f'team-sync:{_now()}'
    removed = 0
    with store.db:
        for owner, digests in published.items():
            like = owner.replace('\\', '\\\\').replace('_', '\\_').replace('%', '\\%')
            rows = store.db.execute("SELECT id,provenance FROM samples WHERE deleted_by IS NULL"
                                    " AND provenance LIKE ? ESCAPE '\\'", (f'team:{like}:%',)).fetchall()
            gone = [(mark, r['id']) for r in rows if r['provenance'].split(':', 2)[-1] not in digests]
            if gone:
                store.db.executemany('UPDATE samples SET deleted_by=? WHERE id=?', gone)
                removed += len(gone)
    return removed


def pull_profiles(store, settings, data_dir=None):
    """Import the other Macs' voice samples, and RECONCILE with them. Idempotent by content hash, capped per
    person like any self-fed profile, and it never overwrites a local sample: `add_sample_if_new` only ever
    inserts, and the cap is filled by this Mac's own samples first.

    Reconciliation first, import second. A sample that left a teammate's file leaves this database too (see
    `_reconcile_profiles`), and doing it BEFORE the import is what makes a correction land: a person already at
    the cap would otherwise refuse the corrected sample and then lose the wrong one, ending up with one sample
    fewer and the fix arriving an hour late. A person RENAMED on the source Mac is the same story told twice —
    the vector's hash changes with the name, so the old line is gone (deleted here) and the new one is new
    (imported here).

    Two different refusals, deliberately not the same thing. `team_profile_blocks` is "never import this
    person": the user deleted the profile and it must not come back. A `rejection` is "that VOICE is not this
    person", so it only stops a sample close enough to the rejected one to BE it — correcting one wrong match
    must not cost the user every clean sample of the real person the rest of the team has."""
    empty = {'imported': 0, 'hosts': 0, 'skipped': 0, 'removed': 0}
    if settings.get('share_profiles') is False: return empty
    directory = profiles_dir(settings, data_dir)
    if directory is None or not directory.is_dir(): return empty
    host = host_name()
    published = _published_by_host(directory, host)
    removed = _reconcile_profiles(store, published)
    blocked = blocked_profiles(store)
    rejections = _rejection_vectors(store)
    imported = skipped = 0
    for owner in sorted(published):
        for digest, e in published[owner].items():
            key = fold_name(e['name'])
            if key in blocked or _rejected(store, rejections, key, e): skipped += 1; continue
            try:
                if store.add_sample_if_new(e['name'], e['vector'], e['model'], e['duration'],
                                           f'team:{owner}:{digest}', cap=PROFILE_CAP): imported += 1
                else: skipped += 1
            except ValueError: skipped += 1   # a line this Mac's `enroll` refuses is one line, not a failed import
    return {'imported': imported, 'hosts': len(published), 'skipped': skipped, 'removed': removed}


def team_summary(store):
    """How much of what this Mac knows came from the team, and how much of it this Mac contributes back.

    Both directions in one place: Ayarlar shows the incoming half ("ekipten 3 profil, 5 kelime") so a shared
    correction is visible as somebody else's work rather than magic, and the heartbeat carries both halves so
    the shared folder can say what each Mac is putting in."""
    _ensure_words(store)
    words = store.db.execute('SELECT count(*) FROM team_words WHERE enabled=1').fetchone()[0]
    rows = store.db.execute("SELECT name FROM samples WHERE deleted_by IS NULL AND provenance LIKE 'team:%'").fetchall()
    people = {fold_name(r[0]) for r in rows}
    shared_words = len(taught_rules(store))
    shared_profiles = store.db.execute("SELECT count(*) FROM samples WHERE deleted_by IS NULL AND (provenance IS NULL OR provenance NOT LIKE 'team:%')").fetchone()[0]
    parts = []
    if people: parts.append(f'{len(people)} profil')
    if words: parts.append(f'{words} kelime')
    return {'profiles': len(rows), 'people': len(people), 'words': words,
            'shared_profiles': shared_profiles, 'shared_words': shared_words,
            'line': ('ekipten ' + ', '.join(parts)) if parts else ''}


# ---------------------------------------------------------------- one call for the app

def sync(store, data_dir, words=True, profiles=True, settings=None, cloud=True):
    """Publish what this Mac learned, then read back what the others did — in that order, and pulling right after
    publishing, so two people correcting the same meeting at the same time converge inside one pass instead of
    waiting an hour. Never raises: a share on an unmounted folder must not fail the teach the user just did.

    With the team cloud the shared folder is a local mirror, so the network pass belongs exactly in the middle:
    publish writes this Mac's files into the mirror, `team_cloud.sync` exchanges them with the team, and pull
    reads back a mirror that already carries what the others learned. `cloud=False` skips the network entirely —
    the fast bridge hooks (naming a voice) do their own `sync_async` instead of waiting for a round trip."""
    from .reports import load_settings
    if settings is None: settings = load_settings(data_dir)
    out = {}
    if words:
        try: out['words'] = publish_words(store, settings, data_dir)
        except (OSError, ValueError) as exc: out['words_error'] = type(exc).__name__
    if profiles:
        try: out['profiles'] = publish_profiles(store, settings, data_dir)
        except (OSError, ValueError) as exc: out['profiles_error'] = type(exc).__name__
    if cloud:
        try:
            from . import team_cloud
            if team_cloud.configured(settings, data_dir): out['cloud'] = team_cloud.sync(data_dir, settings)
        except Exception as exc: out['cloud_error'] = type(exc).__name__   # `sync` swallows its own; this is belt and braces
    if words and 'words' in out:
        try: out['words'] = {**out['words'], **pull_words(store, settings, data_dir)}
        except (OSError, ValueError) as exc: out['words_error'] = type(exc).__name__
    if profiles and 'profiles' in out:
        try: out['profiles'] = {**out['profiles'], **pull_profiles(store, settings, data_dir)}
        except (OSError, ValueError) as exc: out['profiles_error'] = type(exc).__name__
    return out
