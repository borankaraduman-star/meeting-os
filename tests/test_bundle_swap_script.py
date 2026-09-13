"""The one file the bundle update channel runs, and whether it ships.

Written during the 2026-09-13 fresh-Mac simulation (docs/reviews/2026-09-13-fresh-mac-simulation.md), which
found that `Meeting OS.app` 1.2.85 and 1.2.86 carry no `swap-update.sh` anywhere, so `update_start` answers
`{"error": "swap-update.sh bulunamadı"}` and the in-app update cannot work at all.

`tests/test_bundle_layout.py::test_nothing_under_scripts_is_needed_at_runtime` was supposed to catch exactly
this. It scans `meeting_os/*.py` for `Popen(['sh'` and three sibling markers, but `updater.py` spells it
`Popen(['/bin/sh'`, so the guard matches nothing and asserts an empty list against an empty list.

These tests assert the requirement directly instead of pattern-matching the source: the path
`updater.swap_script()` resolves to inside a bundle has to be a path `build-bundle.sh` actually writes.

RED until `scripts/bundle_manifest.py` sets `REPO_SCRIPTS = ['swap-update.sh']` (see the review for the
one-line fix and the alternative, `Contents/Resources/swap-update.sh`).
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

import bundle_manifest as M   # noqa: E402
from meeting_os import updater   # noqa: E402


def _fake_bundle(tmp, *, beside_runtime=False, under_repo=False):
    """A `Meeting OS.app` skeleton with only the files this question is about."""
    resources = Path(tmp) / 'Meeting OS.app' / 'Contents' / 'Resources'
    (resources / 'repo' / 'meeting_os').mkdir(parents=True)
    (resources / 'runtime.json').write_text(
        '{"python":"runtime/bin/python3","repo":"repo","bundled":true,"version":"1.2.86"}', encoding='utf-8')
    if beside_runtime:
        (resources / 'swap-update.sh').write_text('#!/bin/sh\n', encoding='utf-8')
    if under_repo:
        (resources / 'repo' / 'scripts').mkdir(parents=True, exist_ok=True)
        (resources / 'repo' / 'scripts' / 'swap-update.sh').write_text('#!/bin/sh\n', encoding='utf-8')
    return resources / 'repo'


class SwapScriptShips(unittest.TestCase):
    def test_the_manifest_copies_the_script_the_bundle_channel_runs(self):
        """`updater.start_bundle` raises 'swap-update.sh bulunamadı' when this file is not in the bundle, and
        the ONLY thing that puts a script under `repo/scripts` is REPO_SCRIPTS."""
        self.assertIn('swap-update.sh', M.REPO_SCRIPTS,
                      'the bundle update channel runs scripts/swap-update.sh; nothing else copies it')
        self.assertTrue((ROOT / 'scripts' / 'swap-update.sh').is_file())

    def test_swap_script_resolves_to_a_real_file_inside_a_bundle(self):
        """The resolution order `updater.swap_script()` uses, against a bundle laid out the way
        `bundle_manifest` says it will be."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_bundle(tmp, under_repo='swap-update.sh' in M.REPO_SCRIPTS)
            rt = updater.bundle_runtime(root)
            self.assertIsNotNone(rt, 'the skeleton has to look bundled for this test to mean anything')
            resolved = updater.swap_script(rt, root)
            self.assertTrue(Path(resolved).is_file(),
                            f'update_start would raise "swap-update.sh bulunamadı"; resolved to {resolved}')

    def test_either_location_satisfies_the_updater(self):
        """`Contents/Resources/swap-update.sh` is the documented alternative (docs/BUNDLE.md), and it wins
        over the repo copy. Whichever Boran picks, one of them has to exist."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_bundle(tmp, beside_runtime=True)
            rt = updater.bundle_runtime(root)
            resolved = Path(updater.swap_script(rt, root))
            self.assertTrue(resolved.is_file())
            self.assertEqual(resolved.name, 'swap-update.sh')
            self.assertEqual(resolved.parent.name, 'Resources')

    def test_the_old_guard_cannot_see_how_updater_spawns_a_shell(self):
        """Why the blind spot existed, pinned so it is not reintroduced: the markers
        test_nothing_under_scripts_is_needed_at_runtime looks for do not appear in updater.py."""
        text = (ROOT / 'meeting_os' / 'updater.py').read_text(encoding='utf-8')
        self.assertIn("Popen(['/bin/sh'", text, 'updater.py spawns a shell')
        for marker in ("run(['sh'", 'Popen(["sh"', "Popen(['sh'", "'scripts/build"):
            self.assertNotIn(marker, text,
                             f'{marker!r} now matches; the layout guard may be real again — re-check it')


if __name__ == '__main__':
    unittest.main()
