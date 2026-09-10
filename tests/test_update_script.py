"""scripts/update.sh runs detached, with the app quit — a codesign password dialog there has nobody to answer
it. These tests drive the real script with `git`, `pgrep` and `open` stubbed on PATH and HOME pointed at a temp
directory, so the two signing decisions are exercised end to end. Nothing here touches the Keychain, the real
repository, or a real build."""
import json, os, shutil, stat, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROM, TO = 'aaaaaaa', 'bbbbbbb'


def _exe(path, body):
    path.write_text('#!/bin/sh\n' + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class UpdateScriptTests(unittest.TestCase):
    def run_update(self, *, marker, build):
        """Returns (exit code, parsed update-status.json). `build` is the body of a fake build-desktop.sh."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            home = tmp/'home'; repo = tmp/'repo'; bin_dir = tmp/'bin'
            data = home/'Library/Application Support/MeetingOS'
            for d in (data, repo/'scripts', repo/'.git', bin_dir): d.mkdir(parents=True)
            shutil.copy(ROOT/'scripts/update.sh', repo/'scripts/update.sh')
            _exe(repo/'scripts/build-desktop.sh', build)
            _exe(repo/'scripts/build-capture.sh', 'exit 0\n')
            if marker: (data/'signing-partition.ok').write_text('granted\n')
            _exe(bin_dir/'pgrep', 'exit 1\n')                       # the app is not running
            _exe(bin_dir/'open', 'exit 0\n')                        # the EXIT trap relaunches it
            _exe(bin_dir/'git', f'''
case "$1 $2" in
  "rev-parse --short") [ -f .git/merged ] && echo {TO} || echo {FROM}; exit 0 ;;
  "status --porcelain") exit 0 ;;
  "fetch --tags") exit 0 ;;
  "describe --tags") echo v9.9.9; exit 0 ;;
  "merge --ff-only") : > .git/merged; exit 0 ;;
  "diff --quiet") exit 0 ;;
esac
exit 0
''')
            env = {**os.environ, 'HOME': str(home), 'PATH': f'{bin_dir}:{os.environ["PATH"]}'}
            r = subprocess.run(['/bin/sh', 'scripts/update.sh'], cwd=repo, env=env,
                               capture_output=True, text=True, timeout=180)
            status = json.loads((data/'update-status.json').read_text())
            return r.returncode, status, (data/'update.log').read_text()

    def test_missing_marker_stops_before_any_build(self):
        code, status, log = self.run_update(marker=False, build='echo BUILD_RAN; exit 0\n')
        self.assertEqual(code, 1)
        self.assertEqual(status['state'], 'failed')
        self.assertIn('fix-signing-prompts.sh', status['message'])
        self.assertEqual(status['to'], TO)
        self.assertNotIn('BUILD_RAN', log)          # the gate fires before pip, capture and Swift

    def test_signing_failure_is_not_reported_as_a_compiler_failure(self):
        code, status, _ = self.run_update(
            marker=True, build='echo "error: errSecAuth (OSStatus -25293)" >&2; exit 1\n')
        self.assertEqual(status['state'], 'failed')
        self.assertIn('fix-signing-prompts.sh', status['message'])
        self.assertNotIn('Derleme başarısız', status['message'])

    def test_other_build_failures_keep_the_generic_message(self):
        code, status, _ = self.run_update(marker=True, build='echo "error: no such module" >&2; exit 1\n')
        self.assertEqual(status['state'], 'failed')
        self.assertIn('Derleme başarısız', status['message'])
        self.assertNotIn('fix-signing-prompts.sh', status['message'])

    def test_marker_present_and_build_ok_completes(self):
        code, status, _ = self.run_update(marker=True, build='exit 0\n')
        self.assertEqual(code, 0)
        self.assertEqual(status['state'], 'done')
        self.assertIn(f'{FROM} → {TO}', status['message'])


class UpdateScriptSourceTests(unittest.TestCase):
    def test_fetch_never_waits_on_a_credential_prompt(self):
        src = (ROOT/'scripts/update.sh').read_text()
        self.assertIn('GIT_TERMINAL_PROMPT=0', src)
        self.assertIn('GIT_ASKPASS=/usr/bin/true', src)
        self.assertIn("zaman aşımı", src)
