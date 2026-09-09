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
        raise ValueError('Ad-hoc builds require explicit opt-in each time. Migrate to a stable certificate; see docs/MACOS_PERMISSIONS.md.')
    if pinned and requested and pinned != requested:
        raise ValueError('Signing identity change refused. Migrate the saved identity explicitly; macOS permissions may need renewal.')
    selected = requested or pinned
    if selected is None:
        if len(identities) != 1:
            raise ValueError('Select one valid certificate SHA-1 with MEETING_OS_SIGNING_IDENTITY. No automatic ad-hoc fallback. See docs/MACOS_PERMISSIONS.md.')
        selected = identities[0]
    if selected != '-' and selected not in identities:
        raise ValueError('The selected signing certificate is unavailable. Existing application preserved.')
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
        for old in sorted(backup.parent.parent.iterdir(), key=lambda p: p.name)[:-2]:
            if old.is_dir(): shutil.rmtree(old, ignore_errors=True)
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
