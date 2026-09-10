"""Pin a local signing identity; never silently downgrade an installed build.

No credentials or private keys are read. codesign uses the existing keychain.
An unsigned developer bootstrap requires explicit MEETING_OS_SIGNING_IDENTITY=-.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / 'build' / 'signing-identity.json'


def choose_identity(identities, pinned, requested):
    if pinned == '-' and requested != '-':
        raise ValueError('Ad-hoc builds require explicit opt-in each time. Migrate to a stable certificate; see docs/MACOS_PERMISSIONS.md.'
                         ' — Bu Mac daha önce imzasız (ad-hoc) kurulmuş. İmzasız kuruluma devam etmek için: MEETING_OS_SIGNING_IDENTITY=- sh scripts/install.sh · kalıcı çözüm için sertifikaya geçin, bkz. docs/MACOS_PERMISSIONS.md.')
    if pinned and requested and pinned != requested:
        raise ValueError('Signing identity change refused. Migrate the saved identity explicitly; macOS permissions may need renewal.'
                         ' — Kayıtlı sertifika ile istenen sertifika farklı. Bilerek değiştiriyorsanız build/signing-identity.json dosyasını silin, sonra: sh scripts/install.sh · uygulama yeni sertifikayla imzalanınca macOS mikrofon/ekran izinlerini yeniden soracaktır.')
    selected = requested or pinned
    if selected is None:
        if len(identities) != 1:
            raise ValueError('Select one valid certificate SHA-1 with MEETING_OS_SIGNING_IDENTITY. No automatic ad-hoc fallback. See docs/MACOS_PERMISSIONS.md.'
                             ' — Birden fazla (veya hiç) kod imzalama sertifikası var. Listeyi görmek için: security find-identity -v -p codesigning · sonra: MEETING_OS_SIGNING_IDENTITY=<SHA-1> sh scripts/install.sh')
        selected = identities[0]
    if selected != '-' and selected not in identities:
        raise ValueError('The selected signing certificate is unavailable. Existing application preserved.'
                         ' — Seçilen sertifika bu Mac’in anahtar zincirinde yok. Listeyi görmek için: security find-identity -v -p codesigning · kurulu uygulamaya dokunulmadı.')
    return selected


def resolve():
    listing = subprocess.check_output(['security', 'find-identity', '-v', '-p', 'codesigning'], text=True)
    identities = re.findall(r'^\s*\d+\) ([A-F0-9]{40}) ', listing, re.M)
    PIN.parent.mkdir(parents=True, exist_ok=True)
    with PIN.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pinned = json.loads(PIN.read_text())['identity'] if PIN.exists() else None
        selected = choose_identity(identities, pinned, os.environ.get('MEETING_OS_SIGNING_IDENTITY'))
        if not PIN.exists():
            temporary = PIN.with_suffix('.tmp')
            temporary.write_text(json.dumps({'identity': selected}) + '\n')
            temporary.replace(PIN)
    return selected


def verify(app):
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)


def prune_backups(folder, keep_dir=None, keep=2):
    """Keep the `keep` newest backups by MODIFICATION TIME, and never the one that was just created.

    They used to be sorted by name. Backups made before 1.2.30 are named by ISO timestamp ("2026-09-08T…") and
    the ones since by `time.time_ns()` ("17573…"), so every fresh backup sorted BEFORE every legacy one and was
    the first thing deleted — the rollback copy was destroyed the moment it was made, and this Mac's
    build/app-backups holds nothing newer than 8 Sep. mtime has no such tie to the naming scheme."""
    folder = Path(folder)
    try: entries = [p for p in folder.iterdir() if p.is_dir() and p != keep_dir]
    except OSError: return []
    def when(p):
        try: return p.stat().st_mtime
        except OSError: return 0.0
    survivors = keep - (1 if keep_dir is not None else 0)
    removed = sorted(entries, key=when, reverse=True)[max(survivors, 0):]
    for old in removed: shutil.rmtree(old, ignore_errors=True)
    return [str(p) for p in removed]


def publish(stage, target):
    verify(stage)
    with (stage / 'Contents/Info.plist').open('rb') as f:
        executable = plistlib.load(f)['CFBundleExecutable']
    commands = subprocess.check_output(['ps', '-axo', 'command='], text=True).splitlines()
    running = str(target / 'Contents/MacOS' / executable)
    if any(command == running or command.startswith(running + ' ') for command in commands):
        raise ValueError('Application is running. Quit it before installing; staged application preserved.')
    backup = ROOT / 'build/app-backups' / str(time.time_ns()) / target.name
    if target.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        target.rename(backup)
        # keep the two newest backups only; each is ~40 MB and they used to accumulate forever
        prune_backups(backup.parent.parent, keep_dir=backup.parent, keep=2)
    try:
        stage.rename(target)
    except BaseException:
        if backup.exists():
            backup.rename(target)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resolve', action='store_true')
    parser.add_argument('--sign', type=Path)
    parser.add_argument('--publish', type=Path)
    parser.add_argument('--target', type=Path)
    args = parser.parse_args()
    if args.resolve:
        print(resolve())
    elif args.sign:
        identity = resolve()
        subprocess.run(['codesign', '--force', '--deep', '--sign', identity, str(args.sign)], check=True)
        verify(args.sign)
    elif args.publish and args.target:
        publish(args.publish, args.target)
    else:
        parser.error('Choose --resolve, --sign APP, or --publish STAGE --target APP')


if __name__ == '__main__':
    main()
