"""Update check against the GitHub branch; the actual update runs in scripts/update.sh, detached."""
import json
import os
import re
import subprocess
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


def check(root):
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


def start(root, data_dir):
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
