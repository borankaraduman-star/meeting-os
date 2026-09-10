"""scripts/update.sh runs detached, with the app quit — a codesign password dialog there has nobody to answer
it. These tests drive the real script with `git`, `pgrep`, `open` and the virtualenv's `python` stubbed on PATH
and HOME pointed at a temp directory, so every decision that can stop or mutate this Mac is exercised end to
end. Nothing here touches the Keychain, the real repository, or a real build."""
import json, os, shutil, stat, subprocess, tempfile, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROM, TO = 'aaaaaaa', 'bbbbbbb'


def _exe(path, body):
    path.write_text('#!/bin/sh\n' + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class UpdateScriptTests(unittest.TestCase):
    def run_update(self, *, marker=True, build='exit 0\n', tags='v9.9.9', can_ff=True, merged=False,
                   installed=None, deps_changed=False, capture_running=False, recording=None, lock=None,
                   shared_recording=None, env=None):
        """Runs the real script against a fake repository.

        merged        HEAD already sits on the target (a retry after a post-merge failure)
        installed     contents of build/installed-commit, or None for a Mac that never recorded one
        deps_changed  `git diff --quiet` reports requirements/capture changes between BASE and TO
        recording     seconds of age for a recording-heartbeat.json, or None for no recording
        lock          seconds of age for an existing $DATA/update.lock.d, or None
        Returns a dict: code, status, log, installed (build/installed-commit), merged (did the merge run).
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            home = tmp/'home'; repo = tmp/'repo'; bin_dir = tmp/'bin'
            data = home/'Library/Application Support/MeetingOS'
            for d in (data, repo/'scripts', repo/'.git', repo/'build', repo/'.venv/bin', bin_dir): d.mkdir(parents=True)
            shutil.copy(ROOT/'scripts/update.sh', repo/'scripts/update.sh')
            _exe(repo/'scripts/build-desktop.sh', build)
            _exe(repo/'scripts/build-capture.sh', 'echo CAPTURE_RAN\nexit 0\n')
            _exe(repo/'.venv/bin/python', 'echo PIP_RAN\nexit 0\n')
            if marker: (data/'signing-partition.ok').write_text('granted\n')
            if merged: (repo/'.git/merged').write_text('')
            if installed: (repo/'build/installed-commit').write_text(installed + '\n')
            if recording is not None:
                beat = data/'recording-heartbeat.json'   # this Mac's own recorder writes it here; the shared copy under MeetingOS-Reports/<host>/ is ignored
                beat.parent.mkdir(parents=True, exist_ok=True); beat.write_text('{}')
                os.utime(beat, (time.time()-recording, time.time()-recording))
            if shared_recording is not None:   # another Mac's meeting, published into the shared report folder
                beat = home/'Library/Mobile Documents/com~apple~CloudDocs/MeetingOS-Reports/Other-Mac/recording-heartbeat.json'
                beat.parent.mkdir(parents=True, exist_ok=True); beat.write_text('{}')
                os.utime(beat, (time.time()-shared_recording, time.time()-shared_recording))
            if lock is not None:
                (data/'update.lock.d').mkdir()
                os.utime(data/'update.lock.d', (time.time()-lock, time.time()-lock))
            _exe(bin_dir/'pgrep', 'case "$2" in MeetingCapture) exit %d ;; esac\nexit 1\n' % (0 if capture_running else 1))
            _exe(bin_dir/'open', 'exit 0\n')                        # the EXIT trap relaunches it
            _exe(bin_dir/'git', f'''
case "$1 $2" in
  "rev-parse --short") [ -f .git/merged ] && echo {TO} || echo {FROM}; exit 0 ;;
  "status --porcelain") exit 0 ;;
  "fetch --tags") exit 0 ;;
  "tag --merged") printf '%s\\n' {tags or "''"}; exit 0 ;;
  "describe --tags") echo NEAREST_TAG_MUST_NOT_BE_USED; exit 0 ;;
  "merge-base --is-ancestor") exit {0 if can_ff else 1} ;;
  "cat-file -e") exit 0 ;;
  "merge --ff-only") : > .git/merged; echo MERGE_RAN; exit 0 ;;
  "diff --quiet") exit {1 if deps_changed else 0} ;;
esac
exit 0
''')
            environ = {**os.environ, 'HOME': str(home), 'PATH': f'{bin_dir}:{os.environ["PATH"]}', **(env or {})}
            r = subprocess.run(['/bin/sh', 'scripts/update.sh'], cwd=repo, env=environ,
                               capture_output=True, text=True, timeout=180)
            state = json.loads((data/'update-status.json').read_text()) if (data/'update-status.json').is_file() else {}
            installed_now = (repo/'build/installed-commit').read_text().strip() if (repo/'build/installed-commit').is_file() else None
            return {'code': r.returncode, 'status': state, 'log': (data/'update.log').read_text(),
                    'installed': installed_now, 'merged': (repo/'.git/merged').exists(),
                    'lock': (data/'update.lock.d').exists()}

    # ---- the signing gate -------------------------------------------------------------------------------
    def test_missing_marker_stops_before_the_merge_and_before_any_build(self):
        r = self.run_update(marker=False, build='echo BUILD_RAN; exit 0\n')
        self.assertEqual(r['code'], 1)
        self.assertEqual(r['status']['state'], 'failed')
        self.assertIn('fix-signing-prompts.sh', r['status']['message'])
        self.assertIn('/scripts/fix-signing-prompts.sh', r['status']['message'])   # absolute, copy-pasteable
        self.assertEqual(r['status']['to'], FROM)     # the working tree never moved
        self.assertFalse(r['merged'])                 # the whole point: a blocked Mac does not end up on the new commit
        self.assertNotIn('MERGE_RAN', r['log'])
        self.assertNotIn('BUILD_RAN', r['log'])       # the gate fires before pip, capture and Swift

    def test_a_branch_that_cannot_fast_forward_is_refused_before_the_merge(self):
        r = self.run_update(can_ff=False, build='echo BUILD_RAN; exit 0\n')
        self.assertEqual(r['code'], 1)
        self.assertIn('Dal ileri sarılamadı', r['status']['message'])
        self.assertIn('update.log', r['status']['message'])
        self.assertFalse(r['merged'])
        self.assertNotIn('BUILD_RAN', r['log'])

    def test_signing_failure_is_not_reported_as_a_compiler_failure(self):
        r = self.run_update(build='echo "error: errSecAuth (OSStatus -25293)" >&2; exit 1\n')
        self.assertEqual(r['status']['state'], 'failed')
        self.assertIn('fix-signing-prompts.sh', r['status']['message'])
        self.assertNotIn('Derleme başarısız', r['status']['message'])

    def test_other_build_failures_name_the_untouched_installed_app(self):
        r = self.run_update(build='echo "error: no such module" >&2; exit 1\n')
        self.assertEqual(r['status']['state'], 'failed')
        self.assertIn('kurulu sürüm değişmedi', r['status']['message'])
        self.assertIn('build/Meeting OS.app', r['status']['message'])
        self.assertNotIn('fix-signing-prompts.sh', r['status']['message'])
        self.assertIsNone(r['installed'])             # nothing was installed, so nothing is recorded

    def test_marker_present_and_build_ok_completes_and_records_the_installed_commit(self):
        r = self.run_update()
        self.assertEqual(r['code'], 0)
        self.assertEqual(r['status']['state'], 'done')
        self.assertIn(f'{FROM} → {TO}', r['status']['message'])
        self.assertEqual(r['installed'], TO)
        self.assertFalse(r['lock'])                   # released on the way out

    # ---- retries ----------------------------------------------------------------------------------------
    def test_a_retry_after_a_post_merge_failure_still_runs_pip_and_the_capture_helper(self):
        """HEAD already sits on the new commit; the installed app is still the old one. Comparing against HEAD
        would skip both steps and install a new app against old dependencies."""
        r = self.run_update(merged=True, installed=FROM, deps_changed=True)
        self.assertEqual(r['status']['state'], 'done')
        self.assertIn('PIP_RAN', r['log'])
        self.assertIn('CAPTURE_RAN', r['log'])
        self.assertIn(f'{FROM} → {TO}', r['status']['message'])   # the message names what is actually replaced
        self.assertEqual(r['installed'], TO)

    def test_without_an_installed_commit_the_head_at_start_is_the_fallback(self):
        r = self.run_update(merged=True, installed=None, deps_changed=True)
        self.assertEqual(r['status']['state'], 'done')
        self.assertNotIn('PIP_RAN', r['log'])         # FROM == TO: nothing to compare, nothing to reinstall
        self.assertEqual(r['installed'], TO)

    # ---- refusals ---------------------------------------------------------------------------------------
    def test_a_second_updater_refuses_while_one_is_running(self):
        r = self.run_update(lock=60)
        self.assertEqual(r['code'], 1)
        self.assertIn('zaten sürüyor', r['log'])
        self.assertIsNone(r['status'].get('state'))   # the status file belongs to the run that holds the lock: untouched
        self.assertFalse(r['merged'])

    def test_a_teammates_recording_in_the_shared_folder_does_not_refuse(self):
        r = self.run_update(shared_recording=30)   # two Macs share one iCloud folder: the other one's meeting is not ours
        self.assertEqual(r['status']['state'], 'done')

    def test_a_stale_lock_is_cleared(self):
        r = self.run_update(lock=45*60)
        self.assertEqual(r['status']['state'], 'done')

    def test_a_live_recording_heartbeat_refuses_the_update(self):
        r = self.run_update(recording=30, build='echo BUILD_RAN; exit 0\n')
        self.assertEqual(r['code'], 1)
        self.assertEqual((r['status']['state'], r['status']['message']), ('refused', 'Kayıt sürüyor; güncelleme yapılmadı'))
        self.assertFalse(r['merged'])
        self.assertNotIn('BUILD_RAN', r['log'])

    def test_a_stale_recording_heartbeat_does_not_refuse(self):
        r = self.run_update(recording=30*60)
        self.assertEqual(r['status']['state'], 'done')

    def test_a_running_capture_helper_refuses_the_update(self):
        r = self.run_update(capture_running=True)
        self.assertEqual(r['code'], 1)
        self.assertEqual((r['status']['state'], r['status']['message']), ('refused', 'Kayıt sürüyor; güncelleme yapılmadı'))

    # ---- the release target -----------------------------------------------------------------------------
    def test_the_highest_release_tag_wins_not_the_nearest_ancestor(self):
        r = self.run_update(tags="v1.2.9 v1.2.44 v1.2.10")
        self.assertEqual(r['status']['state'], 'done')
        self.assertNotIn('NEAREST_TAG_MUST_NOT_BE_USED', r['log'])

    def test_an_untagged_branch_is_not_installed(self):
        r = self.run_update(tags='')
        self.assertEqual(r['code'], 1)
        self.assertIn('etiket', r['status']['message'])
        self.assertFalse(r['merged'])


class UpdateScriptSourceTests(unittest.TestCase):
    def test_fetch_never_waits_on_a_credential_prompt(self):
        src = (ROOT/'scripts/update.sh').read_text()
        self.assertIn('GIT_TERMINAL_PROMPT=0', src)
        self.assertIn('GIT_ASKPASS=/usr/bin/true', src)
        self.assertIn("zaman aşımı", src)

    def test_the_relaunch_prefers_the_bundle_that_was_just_built(self):
        src = (ROOT/'scripts/update.sh').read_text()
        trap = [line for line in src.splitlines() if 'open "$REPO/build/Meeting OS.app"' in line]
        self.assertTrue(trap, 'the EXIT trap must open the built bundle by path')
        self.assertLess(trap[0].index('open "$REPO/build/Meeting OS.app"'), trap[0].index('open -a'))

    def test_the_status_file_is_written_atomically(self):
        src = (ROOT/'scripts/update.sh').read_text()
        self.assertIn('mv -f "$tmp" "$STATUS"', src)

    def test_the_log_is_rotated(self):
        src = (ROOT/'scripts/update.sh').read_text()
        self.assertIn('LOG_MAX_BYTES=1048576', src)
        self.assertIn('mv -f "$LOG" "$LOG.1"', src)


if __name__ == '__main__':
    unittest.main()
