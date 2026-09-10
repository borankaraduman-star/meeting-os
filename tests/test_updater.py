"""The in-app update check. It decides whether the button appears at all, so its two silent failure modes matter
more than its happy path: offering an OLDER release than the one installed, and reporting "güncel" on a Mac whose
branch has diverged and can never fast-forward. Every test here runs against a real local git repository — no
network, no remote host, no credentials."""
import os, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from meeting_os import updater

GIT_ENV = {**os.environ, 'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@x', 'GIT_COMMITTER_NAME': 'T',
           'GIT_COMMITTER_EMAIL': 't@x', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_SYSTEM': '/dev/null'}


def git(cwd, *args):
    return subprocess.run(['git', *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=True).stdout.strip()


class Fleet:
    """A bare origin carrying v1.2.9 AFTER v1.2.44 in graph order, and a clone of it. `describe --abbrev=0` from
    the tip answers v1.2.9 here; the newest release is v1.2.44."""
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.origin = root/'origin.git'; self.work = root/'work'; self.mac = root/'mac'
        git(root, 'init', '--bare', '-b', 'v0.1', str(self.origin))
        git(root, 'clone', str(self.origin), str(self.work))
        self.commits = []
        for i, tag in enumerate((None, 'v1.2.44', 'v1.2.9')):
            (self.work/f'f{i}').write_text(str(i))
            git(self.work, 'add', '-A'); git(self.work, 'commit', '-m', f'c{i}')
            self.commits.append(git(self.work, 'rev-parse', 'HEAD'))
            if tag: git(self.work, 'tag', tag)
        git(self.work, 'push', '--tags', 'origin', 'v0.1')
        git(root, 'clone', str(self.origin), str(self.mac))
        return self

    def rewind(self, n):
        git(self.mac, 'reset', '--hard', self.commits[n])

    def diverge(self):
        (self.mac/'local').write_text('x'); git(self.mac, 'add', '-A'); git(self.mac, 'commit', '-m', 'yerel')

    def __exit__(self, *a): self.tmp.cleanup()


class ReleaseTargetTests(unittest.TestCase):
    def test_the_highest_release_tag_wins_not_the_nearest_ancestor(self):
        with Fleet() as f:
            self.assertEqual(updater.release_target(f.mac), 'v1.2.44')
            nearest = subprocess.run(['git', 'describe', '--tags', '--abbrev=0', '--match', 'v*', 'origin/v0.1'],
                                     cwd=f.mac, capture_output=True, text=True).stdout.strip()
            self.assertEqual(nearest, 'v1.2.9')   # what the old code would have installed: a downgrade

    def test_an_untagged_branch_falls_back_to_the_tip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); git(root, 'init', '-b', 'v0.1', str(root/'r'))
            self.assertIsNone(updater.release_target(root/'r'))   # nothing released: the app must not offer what update.sh would refuse

    def test_the_dev_override_follows_every_commit(self):
        with Fleet() as f, patch.dict(os.environ, {'MEETING_OS_UPDATE_UNTAGGED': '1'}):
            self.assertEqual(updater.release_target(f.mac), 'origin/v0.1')


class CheckTests(unittest.TestCase):
    def test_a_mac_behind_the_newest_release_is_offered_it(self):
        with Fleet() as f:
            f.rewind(0)
            r = updater.check(f.mac)
            self.assertTrue(r['available'])
            self.assertEqual((r['target'], r['ahead'], r['dirty']), ('v1.2.44', 0, False))
            self.assertEqual(r['behind'], 1)
            self.assertNotIn('diverged', r)

    def test_a_diverged_branch_says_so_instead_of_reporting_nothing_to_do(self):
        """ahead AND behind: `merge --ff-only` in update.sh can never succeed. The old check returned
        available=False with no reason and the card simply disappeared."""
        with Fleet() as f:
            f.rewind(0); f.diverge()
            r = updater.check(f.mac)
            self.assertTrue(r['diverged'])
            self.assertFalse(r['available'])
            self.assertGreater(r['ahead'], 0); self.assertGreater(r['behind'], 0)
            self.assertIn('ayrışmış', r['error'])
            self.assertIn('Boran', r['hint'])

    def test_a_mac_on_the_newest_release_is_up_to_date_and_not_diverged(self):
        with Fleet() as f:
            f.rewind(1)
            r = updater.check(f.mac)
            self.assertFalse(r['available']); self.assertEqual(r['behind'], 0)
            self.assertNotIn('diverged', r)

    def test_an_unreachable_remote_is_an_error_not_an_exception(self):
        with Fleet() as f:
            git(f.mac, 'remote', 'set-url', 'origin', str(f.mac/'yok.git'))
            r = updater.check(f.mac)
            self.assertFalse(r['available']); self.assertIn('GitHub', r['error'])


class FetchSafetyTests(unittest.TestCase):
    def test_the_fetch_can_never_wait_on_a_credential_prompt_and_forces_moved_tags(self):
        calls = []
        class R: returncode = 0; stdout = ''; stderr = ''
        def fake(cmd, **kw): calls.append((cmd, kw)); return R()
        with patch.object(updater.subprocess, 'run', fake):
            updater.check('/nonexistent')
        fetch = next(c for c, _ in calls if c[1] == 'fetch')
        self.assertIn('--force', fetch); self.assertIn('--tags', fetch)
        env = calls[0][1]['env']
        self.assertEqual(env['GIT_TERMINAL_PROMPT'], '0')
        self.assertEqual(env['GIT_ASKPASS'], '/usr/bin/true')


if __name__ == '__main__':
    unittest.main()
