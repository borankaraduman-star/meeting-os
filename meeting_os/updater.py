"""Update check against the GitHub branch; the actual update runs in scripts/update.sh, detached."""
import json
import os
import subprocess
from pathlib import Path

BRANCH = 'v0.1'


def _git(root, *args, timeout=25):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, timeout=timeout)


def check(root):
    root = Path(root)
    try:
        fetch = _git(root, 'fetch', '--quiet', 'origin', BRANCH)
        if fetch.returncode: return {'available': False, 'error': 'GitHub’a ulaşılamadı', 'local': _git(root, 'rev-parse', '--short', 'HEAD').stdout.strip()}
        local = _git(root, 'rev-parse', '--short', 'HEAD').stdout.strip()
        remote = _git(root, 'rev-parse', '--short', f'origin/{BRANCH}').stdout.strip()
        behind = int(_git(root, 'rev-list', '--count', f'HEAD..origin/{BRANCH}').stdout.strip() or 0)
        ahead = int(_git(root, 'rev-list', '--count', f'origin/{BRANCH}..HEAD').stdout.strip() or 0)
        subjects = [s for s in _git(root, 'log', '--format=%s', f'HEAD..origin/{BRANCH}', '-n', '5').stdout.splitlines() if s]
        dirty = bool(_git(root, 'status', '--porcelain').stdout.strip())
        return {'available': behind > 0 and ahead == 0 and not dirty, 'behind': behind, 'ahead': ahead, 'dirty': dirty, 'local': local, 'remote': remote, 'subjects': subjects[:5]}
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {'available': False, 'error': f'Güncelleme kontrolü yapılamadı ({type(exc).__name__})'}


def start(root, data_dir):
    """Launch the detached updater; the app quits right after so the build can replace it."""
    script = Path(root) / 'scripts' / 'update.sh'
    if not script.is_file(): raise ValueError('update.sh bulunamadı')
    log = open(Path(data_dir) / 'update.log', 'a')
    subprocess.Popen(['/bin/sh', str(script)], cwd=root, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True, env={**os.environ, 'MEETING_OS_UPDATER': '1'})
    return {'started': True}


def status(data_dir):
    path = Path(data_dir) / 'update-status.json'
    try: return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    except ValueError: return {}
