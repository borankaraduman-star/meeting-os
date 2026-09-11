"""In-app updates, two channels.

* git checkout (a developer Mac): the check is a `git fetch`, the update runs in scripts/update.sh, detached.
* app bundle (docs/BUNDLE.md): the check is `latest.json` over the download channel, the update downloads a
  signed zip, verifies it, unpacks it and hands over to scripts/swap-update.sh, detached.

`check(root)` and `start(root, data_dir)` pick the channel from `root` alone (desktop.py passes cli.ROOT):
inside a bundle that path is `Meeting OS.app/Contents/Resources/repo`, with `runtime.json` one level up.
Both channels write the SAME `update-status.json` the app already polls (state/from/to/message/time), with
one added key: `percent` while downloading.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

BRANCH = 'v0.1'
# A repository that lost its credentials must fail, not sit on an invisible username prompt: the check runs
# inside the app, where nobody can answer one, and a blocked fetch would hang the update card for its timeout.
NO_PROMPT = {'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': '/usr/bin/true'}
VERSION_TAG = re.compile(r'^v(\d+)\.(\d+)\.(\d+)$')
DIVERGED_ERROR = 'Dal ayrışmış · yeni sürüm kurulamıyor'
DIVERGED_HINT = 'Bu Mac’in deposunda yayınlanmamış commit’ler var; ileri sarılamaz · Boran’a bildirin'


def _git(root, *args, timeout=25):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, **NO_PROMPT})


def _version(tag):
    m = VERSION_TAG.match(tag.strip())
    return tuple(int(p) for p in m.groups()) if m else None


def release_target(root):
    """HIGHEST release tag reachable from origin/<branch> (vX.Y.Z); the branch tip itself when nothing is tagged
    or MEETING_OS_UPDATE_UNTAGGED=1 (a dev Mac following every commit).

    Not `describe --tags --abbrev=0`: that walks backwards from the tip and stops at the first tag it meets, so a
    branch carrying several tags can resolve to an OLDER release than the one already installed — a silent
    downgrade. Ordering the reachable tags by version says what the newest release actually is."""
    if os.environ.get('MEETING_OS_UPDATE_UNTAGGED'): return f'origin/{BRANCH}'
    listing = _git(root, 'tag', '--merged', f'origin/{BRANCH}', 'v[0-9]*.[0-9]*.[0-9]*').stdout.splitlines()
    tags = sorted(((_version(t), t.strip()) for t in listing if _version(t)), key=lambda p: p[0])
    return tags[-1][1] if tags else None   # None = nothing released: update.sh refuses too, so the app must not offer


def check_git(root):
    root = Path(root)
    try:
        # --force: a tag that moved on the server (a re-cut release) otherwise fails the fetch and freezes this
        # Mac on the tag it already has.
        fetch = _git(root, 'fetch', '--quiet', '--tags', '--force', 'origin', BRANCH)
        if fetch.returncode: return {'available': False, 'error': 'GitHub’a ulaşılamadı', 'local': _git(root, 'rev-parse', '--short', 'HEAD').stdout.strip()}
        local = _git(root, 'rev-parse', '--short', 'HEAD').stdout.strip()
        target = release_target(root)   # the newest vX.Y.Z tag on the branch: only released states are offered
        if target is None:
            return {'available': False, 'behind': 0, 'ahead': 0, 'target': None, 'no_tag': True,
                    'error': 'GitHub’da yayınlanmış sürüm etiketi bulunamadı; güncelleme bekletildi',
                    'local': _git(root, 'rev-parse', '--short', 'HEAD').stdout.strip()}
        remote = _git(root, 'rev-parse', '--short', target).stdout.strip()
        behind = int(_git(root, 'rev-list', '--count', f'HEAD..{target}').stdout.strip() or 0)
        ahead = int(_git(root, 'rev-list', '--count', f'{target}..HEAD').stdout.strip() or 0)
        subjects = [s for s in _git(root, 'log', '--format=%s', f'HEAD..{target}', '-n', '5').stdout.splitlines() if s]
        dirty = bool(_git(root, 'status', '--porcelain').stdout.strip())
        # Ahead AND behind: this Mac carries commits the release does not, so `merge --ff-only` in update.sh will
        # refuse. Saying "güncel değil" and offering a button that always fails is worse than saying why.
        diverged = behind > 0 and ahead > 0
        out = {'available': behind > 0 and ahead == 0 and not dirty, 'behind': behind, 'ahead': ahead, 'dirty': dirty,
               'local': local, 'remote': remote, 'target': target, 'subjects': subjects[:5]}
        if diverged: out.update({'diverged': True, 'error': DIVERGED_ERROR, 'hint': DIVERGED_HINT})
        return out
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {'available': False, 'error': f'Güncelleme kontrolü yapılamadı ({type(exc).__name__})'}


def start_git(root, data_dir):
    """Launch the detached updater; the app quits right after so the build can replace it."""
    script = Path(root) / 'scripts' / 'update.sh'
    if not script.is_file(): raise ValueError('update.sh bulunamadı')
    log = open(Path(data_dir) / 'update.log', 'a')
    subprocess.Popen(['/bin/sh', str(script)], cwd=root, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True, env={k: v for k, v in os.environ.items() if k != 'OPENROUTER_API_KEY'})
    return {'started': True}


def status(data_dir):
    path = Path(data_dir) / 'update-status.json'
    try: return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    except ValueError: return {}


# ---- bundle channel (docs/BUNDLE.md) --------------------------------------------------------------------

BUNDLE_HOST = 'https://hermes-vps.tail2d8c7e.ts.net/meetingos/dl'
USER_AGENT = 'MeetingOS-updater/1'
CHECK_TIMEOUT = 5          # the check runs on the main thread of the app's card: it may never hang it
DOWNLOAD_TIMEOUT = 60      # per read, not for the whole 1,3 GB
CHUNK = 512 * 1024
SECRET_RE = re.compile(r'^[0-9a-fA-F]{32,128}$')
PLAIN_VERSION = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)$')
NO_SECRET_ERROR = 'Güncelleme adresi bu pakette yok · Boran’a bildirin'
UNREACHABLE_ERROR = 'Güncelleme sunucusuna ulaşılamadı'
SHA_ERROR = 'İndirilen paket doğrulanamadı (sha256); yeniden deneyin'


def cache_dir():
    """Where the downloaded zip waits. Caches, not Application Support: a half-finished download is exactly
    what the system may throw away, and it is re-fetched with a Range request anyway."""
    return Path(os.environ.get('MEETING_OS_UPDATE_CACHE') or (Path.home()/'Library/Caches/MeetingOS/update'))


def vkey(value):
    """(major, minor, patch) for '1.2.72' and 'v1.2.72'; None for anything that is not a release version."""
    m = PLAIN_VERSION.match(str(value or '').strip())
    return tuple(int(p) for p in m.groups()) if m else None


def bundle_runtime(root=None, runtime_json=None):
    """The bundle's `runtime.json` as a dict (plus `_path`), or None for a git checkout.

    Inside the app, `root` (cli.ROOT) is `Meeting OS.app/Contents/Resources/repo`, so the file sits one level
    up and says `"bundled": true`. An explicit path — argument or MEETING_OS_RUNTIME_JSON — wins, which is
    what the tests use and what any future layout would use.
    """
    if runtime_json is None:
        runtime_json = os.environ.get('MEETING_OS_RUNTIME_JSON') or None
    if runtime_json is None:
        if root is None: return None
        p = Path(root).resolve()
        if p.name != 'repo': return None
        runtime_json = p.parent/'runtime.json'
    path = Path(runtime_json)
    try: data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return None
    if not isinstance(data, dict) or data.get('bundled') is not True: return None
    data['_path'] = str(path)
    return data


def bundled(root):
    """True when this copy of the repo is running from inside an app bundle."""
    return bundle_runtime(root) is not None


def bundle_secret(rt):
    """The download-path secret: `Resources/download.secret` next to runtime.json first, then runtime.json's
    own `download_secret` key. The separate file is the one Boran drops in when signing, so the secret never
    has to live in a file that build-bundle.sh writes."""
    side = Path(rt.get('_path', '.')).parent/'download.secret'
    try:
        raw = side.read_text(encoding='utf-8').strip()
        if SECRET_RE.match(raw): return raw
    except OSError:
        pass
    raw = str(rt.get('download_secret') or '').strip()
    return raw if SECRET_RE.match(raw) else ''


def bundle_base(rt):
    """`https://…/meetingos/dl/<secret>`, or '' when this bundle carries no secret. `download_base` in
    runtime.json overrides the whole thing (a moved host, and the tests' local server)."""
    explicit = str(rt.get('download_base') or '').strip().rstrip('/')
    if explicit: return explicit
    secret = bundle_secret(rt)
    return f'{BUNDLE_HOST}/{secret}' if secret else ''


def _get(url, timeout, extra_headers=None):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, **(extra_headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_latest(base, timeout=CHECK_TIMEOUT):
    with _get(base + '/latest.json', timeout) as resp:
        data = json.loads(resp.read(64 * 1024).decode('utf-8'))
    return data if isinstance(data, dict) else {}


def check_bundle(rt):
    """The same answer shape the git channel gives, so every screen keeps reading one dict."""
    local = str(rt.get('version') or '').strip()
    out = {'available': False, 'behind': 0, 'ahead': 0, 'dirty': False, 'bundled': True,
           'local': local, 'remote': local, 'target': local, 'subjects': []}
    base = bundle_base(rt)
    if not base:
        return {**out, 'error': NO_SECRET_ERROR}
    try:
        data = fetch_latest(base)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return {**out, 'error': UNREACHABLE_ERROR}
    remote = str(data.get('version') or '').strip()
    notes = str(data.get('notes') or '').strip()
    rv, lv = vkey(remote), vkey(local)
    # An unreadable local version (a hand-built bundle) counts as older: better one needless update than a
    # Mac that can never be updated again.
    newer = bool(rv and (lv is None or rv > lv))
    ready = bool(data.get('file')) and bool(data.get('sha256'))
    out.update({'available': newer and ready, 'behind': 1 if newer else 0,
                'remote': remote or local, 'target': remote or local,
                'subjects': [notes] if (notes and newer) else [],   # the pending release's line, or nothing
                'file': str(data.get('file') or ''), 'sha256': str(data.get('sha256') or ''),
                'size': int(data.get('size') or 0), 'notes': notes})
    if newer and not ready:
        out['error'] = 'Yayınlanan sürüm eksik (dosya veya sha256 yok)'
    return out


def swap_script(rt, root):
    """`Resources/swap-update.sh` inside the bundle, else the repo's `scripts/swap-update.sh`."""
    inside = Path(rt.get('_path', '.')).parent/'swap-update.sh'
    if inside.is_file(): return inside
    return Path(root)/'scripts'/'swap-update.sh'


def app_bundle_path(rt):
    """`…/Meeting OS.app` from `…/Meeting OS.app/Contents/Resources/runtime.json`."""
    parents = Path(rt.get('_path', '.')).resolve().parents
    return parents[2] if len(parents) > 2 else None


def write_status(data_dir, state, message='', from_version='', to_version='', percent=None, error=''):
    """The file scripts/update.sh has always written, byte-compatible: state/from/to/message/time. `percent`
    is the one addition (the download is minutes long, so the app can show it), and `error` repeats the
    message so a reader can tell a real failure from a Turkish sentence that merely sounds like one."""
    payload = {'state': state, 'from': from_version, 'to': to_version, 'message': message or error,
               'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    if percent is not None: payload['percent'] = max(0, min(100, int(percent)))
    if error: payload['error'] = error
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    tmp = base/f'update-status.json.tmp.{os.getpid()}'
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False) + '\n', encoding='utf-8')
        os.replace(tmp, base/'update-status.json')
    except OSError:
        try: tmp.unlink()
        except OSError: pass
    return payload


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def download_resumable(url, dest, total_hint=0, on_progress=None, timeout=DOWNLOAD_TIMEOUT):
    """Fetch `url` into `dest`, continuing a partial file with a Range request.

    A server that ignores the Range header answers 200 with the whole body; that restarts the file instead of
    appending to it, which is the only way to avoid silently concatenating two halves into garbage.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    have = dest.stat().st_size if dest.exists() else 0
    headers = {'Range': f'bytes={have}-'} if have else None
    try:
        resp_cm = _get(url, timeout, headers)
    except urllib.error.HTTPError as exc:
        # 416: we already hold every byte the server has. The sha256 check right after this is what decides
        # whether those bytes are the right ones, so there is nothing to do here but stop.
        if exc.code == 416 and have: return have
        raise
    with resp_cm as resp:
        resumed = resp.status == 206 and have > 0
        if not resumed: have = 0
        length = int(resp.headers.get('Content-Length') or 0)
        total = total_hint or (length + have)
        done = have
        if on_progress: on_progress(done, total)
        with open(dest, 'ab' if resumed else 'wb') as fh:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk: break
                fh.write(chunk)
                done += len(chunk)
                if on_progress: on_progress(done, total)
    return done


def run_download(base, data_dir, app_path, pid, swap, from_version='', cache=None):
    """The detached worker: latest.json → zip → sha256 → ditto → swap-update.sh. Writes every step into
    update-status.json; the app is usually gone by now, so this file is the only thing that can explain a
    failure afterwards."""
    data_dir = Path(data_dir)
    cache = Path(cache) if cache else cache_dir()
    zip_path = None
    sha_known_bad = False
    try:
        info = fetch_latest(base, timeout=DOWNLOAD_TIMEOUT)
        name, sha = str(info.get('file') or ''), str(info.get('sha256') or '').lower()
        to_version = str(info.get('version') or '')
        try: size = int(info.get('size') or 0)
        except (TypeError, ValueError): size = 0
        # The name comes from the server and becomes a path here: the same character class the download route
        # enforces, checked again on this side.
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,120}', name) or name.startswith('.') \
                or not re.fullmatch(r'[0-9a-f]{64}', sha):
            raise ValueError('latest.json eksik veya bozuk')
        zip_path = cache/name
        state = {'pct': -1}

        def progress(done, total):
            pct = int(done * 100 / total) if total else 0
            if pct != state['pct']:
                state['pct'] = pct
                write_status(data_dir, 'downloading', f'Yeni sürüm indiriliyor · %{pct}',
                             from_version, to_version, percent=pct)

        write_status(data_dir, 'downloading', 'Yeni sürüm indiriliyor · %0', from_version, to_version, percent=0)
        # A finished download from an earlier, interrupted run is reused as is.
        if not (zip_path.exists() and size and zip_path.stat().st_size == size):
            download_resumable(f'{base}/{name}', zip_path, total_hint=size, on_progress=progress)

        write_status(data_dir, 'verifying', 'Paket doğrulanıyor', from_version, to_version, percent=100)
        if sha256_file(zip_path) != sha:
            sha_known_bad = True
            raise ValueError(SHA_ERROR)

        write_status(data_dir, 'extracting', 'Paket açılıyor', from_version, to_version, percent=100)
        staging = Path(tempfile.mkdtemp(prefix='meeting-os-update.', dir=str(cache)))
        subprocess.run(['/usr/bin/ditto', '-x', '-k', str(zip_path), str(staging)],
                       check=True, capture_output=True, timeout=900)
        apps = sorted(p for p in staging.iterdir() if p.name.endswith('.app'))
        if not apps:
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError('Pakette uygulama bulunamadı')

        # `swapping` goes in BEFORE the script starts: swap-update.sh writes `done` into the same file when
        # it finishes, and with a pid that has already exited that can be a second later. Writing afterwards
        # would sometimes overwrite `done` with `swapping` and leave the app looking stuck forever.
        write_status(data_dir, 'swapping', 'Yeni sürüm yerine konuyor · uygulama yeniden açılacak',
                     from_version, to_version, percent=100)
        with open(data_dir/'update.log', 'a') as log:   # Popen dups the fd; closing ours changes nothing for it
            subprocess.Popen(['/bin/sh', str(swap), str(apps[0]), str(app_path), str(pid)],
                             stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        return 0
    except Exception as exc:      # noqa: BLE001 - the worker is detached; every failure must reach the file
        reason = str(exc) if isinstance(exc, ValueError) else f'Güncelleme indirilemedi ({type(exc).__name__})'
        # A partial zip is worth keeping: the next run resumes it with a Range request. A zip whose sha256 is
        # WRONG is worth nothing and would poison every retry, so it goes.
        if sha_known_bad and zip_path is not None:
            try: zip_path.unlink()
            except OSError: pass
        for leftover in sorted(cache.glob('meeting-os-update.*')):
            if leftover.is_dir(): shutil.rmtree(leftover, ignore_errors=True)
        write_status(data_dir, 'failed', reason, from_version, error=reason)
        return 1


def start_bundle(rt, root, data_dir, app_path=None, pid=None):
    """Spawn the detached download worker. The app may quit at any moment after this returns."""
    base = bundle_base(rt)
    if not base: raise ValueError(NO_SECRET_ERROR)
    swap = swap_script(rt, root)
    if not Path(swap).is_file(): raise ValueError('swap-update.sh bulunamadı')
    target = str(app_path or app_bundle_path(rt) or '')
    if not target: raise ValueError('Uygulama yolu bulunamadı')
    # The app's pid, not this bridge's: swap-update.sh waits for the app to quit before it moves the bundle.
    # Swift sends it; the fallback is the process that spawned this bridge, which IS the app.
    worker_pid = int(pid or os.getppid())
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != 'OPENROUTER_API_KEY'}
    env['PYTHONPATH'] = str(root) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    cmd = [sys.executable, '-m', 'meeting_os.updater', '--bundle-download', '--base', base,
           '--data-dir', str(data_dir), '--app', target, '--pid', str(worker_pid), '--swap', str(swap),
           '--from-version', str(rt.get('version') or '')]
    with open(data_dir/'update.log', 'a') as log:
        subprocess.Popen(cmd, cwd=str(root), stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                         start_new_session=True, env=env)
    write_status(data_dir, 'downloading', 'Yeni sürüm indiriliyor · %0', str(rt.get('version') or ''), percent=0)
    return {'started': True, 'bundled': True, 'app': target, 'pid': worker_pid}


# ---- channel selection -----------------------------------------------------------------------------------

def check(root):
    rt = bundle_runtime(root)
    return check_bundle(rt) if rt is not None else check_git(root)


def start(root, data_dir, request=None):
    rt = bundle_runtime(root)
    if rt is None: return start_git(root, data_dir)
    sent = request if isinstance(request, dict) else {}
    return start_bundle(rt, root, data_dir, app_path=sent.get('app_path'), pid=sent.get('pid'))


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog='meeting_os.updater', description='Meeting OS bundle updater worker')
    ap.add_argument('--bundle-download', action='store_true', required=True)
    ap.add_argument('--base', required=True)
    ap.add_argument('--data-dir', required=True)
    ap.add_argument('--app', required=True)
    ap.add_argument('--pid', type=int, required=True)
    ap.add_argument('--swap', required=True)
    ap.add_argument('--from-version', default='')
    ap.add_argument('--cache', default=None)
    args = ap.parse_args(argv)
    return run_download(args.base, args.data_dir, args.app, args.pid, args.swap,
                        from_version=args.from_version, cache=args.cache)


if __name__ == '__main__':
    raise SystemExit(_main())
