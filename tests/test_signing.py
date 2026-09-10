import importlib.util
from pathlib import Path
import unittest
import tempfile
import plistlib
import subprocess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class SigningTests(unittest.TestCase):
    def load_module(self):
        spec = importlib.util.spec_from_file_location('signing', ROOT / 'scripts/signing.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_invalid_stage_preserves_installed_app(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'Meeting OS.app'
            target.mkdir()
            (target / 'marker').write_text('existing')
            with patch.object(module, 'verify', side_effect=subprocess.CalledProcessError(1, 'codesign')):
                with self.assertRaises(subprocess.CalledProcessError):
                    module.publish(Path(tmp) / 'invalid-stage', target)
            self.assertEqual((target / 'marker').read_text(), 'existing')

    def test_running_app_preserves_both_bundles(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as tmp:
            target, stage = Path(tmp) / 'Meeting OS.app', Path(tmp) / 'stage.app'
            target.mkdir()
            (stage / 'Contents').mkdir(parents=True)
            (stage / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'MeetingOS'}))
            with patch.object(module, 'verify'), patch.object(module.subprocess, 'check_output',
                    return_value=str(target / 'Contents/MacOS/MeetingOS') + '\n'):
                with self.assertRaisesRegex(ValueError, 'running'):
                    module.publish(stage, target)
            self.assertTrue(target.exists())
            self.assertTrue(stage.exists())

    def test_backups_are_pruned_by_age_and_the_fresh_one_always_survives(self):
        """Legacy ISO names sort AFTER time_ns names, so name-ordered pruning deleted the backup it had just
        made. A folder holding both styles is exactly what a Mac updated across 1.2.30 has."""
        import os, time
        module = self.load_module()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            names = ['2026-09-08T10-00-00', '2026-09-08T11-00-00', '1757400000000000000', '1757500000000000000']
            for i, name in enumerate(names):
                d = folder / name; d.mkdir(); (d/'Meeting OS.app').mkdir()
                os.utime(d, (1_000_000 + i*3600, 1_000_000 + i*3600))
            fresh = folder / str(time.time_ns()); fresh.mkdir(); (fresh/'Meeting OS.app').mkdir()
            removed = module.prune_backups(folder, keep_dir=fresh, keep=2)
            left = sorted(p.name for p in folder.iterdir())
            self.assertIn(fresh.name, left)                 # the one just created is never a candidate
            self.assertIn('1757500000000000000', left)      # the newest of the rest, by mtime
            self.assertEqual(len(left), 2)
            self.assertEqual(len(removed), 3)
            self.assertEqual(module.prune_backups(folder, keep_dir=fresh, keep=2), [])   # idempotent

    def test_pruning_survives_an_unreadable_folder(self):
        module = self.load_module()
        self.assertEqual(module.prune_backups(Path('/nonexistent/app-backups')), [])

    def test_builders_do_not_silently_use_adhoc_signatures(self):
        for name in ('build-desktop.sh', 'build-capture.sh'):
            script = (ROOT / 'scripts' / name).read_text()
            self.assertNotIn('codesign --force --deep --sign - ', script)
            self.assertIn('signing.py', script)

    def test_identity_policy(self):
        path = ROOT / 'scripts' / 'signing.py'
        self.assertTrue(path.exists(), 'Stable signing identity selection is missing')
        spec = importlib.util.spec_from_file_location('signing', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        a, b = 'A' * 40, 'B' * 40
        self.assertEqual(module.choose_identity([a], None, None), a)
        self.assertEqual(module.choose_identity([a, b], a, None), a)
        self.assertEqual(module.choose_identity([a, b], None, b), b)
        for identities, pinned, requested in [([], None, None), ([a,b], None, None),
                ([b], a, None), ([a,b], a, b), ([a], a, '-'), ([a], None, 'invalid'),
                ([], '-', None), ([a], '-', None)]:
            with self.assertRaises(ValueError):
                module.choose_identity(identities, pinned, requested)
        self.assertEqual(module.choose_identity([], None, '-'), '-')


if __name__ == '__main__':
    unittest.main()
