import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
import plistlib
import subprocess
import os
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

    def signing_fixture(self, module, folder, label, descriptions=None):
        app = folder / 'Meeting OS.app'
        (app / 'Contents').mkdir(parents=True)
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleExecutable': 'MeetingOS', **(descriptions or {})}))
        identity = 'A' * 40
        listing = f'  1) {identity} "{label}"\n     1 valid identities found\n'
        return app, identity, listing

    def test_developer_id_rebuild_uses_runtime_timestamp_and_only_declared_access(self):
        for descriptions, expected in (
            ({'NSMicrophoneUsageDescription': True, 'NSCalendarsUsageDescription': ' ',
              'NSAppleEventsUsageDescription': 'Unrelated declaration'}, {}),
            ({'NSMicrophoneUsageDescription': 'Record meeting audio', 'NSScreenCaptureUsageDescription': 'System audio'},
             {'com.apple.security.device.audio-input': True}),
            ({'NSMicrophoneUsageDescription': 'Record meeting audio', 'NSCalendarsFullAccessUsageDescription': 'Read current event',
              'NSCalendarsUsageDescription': 'Read current event', 'NSRemindersFullAccessUsageDescription': 'Add chosen task'},
             {'com.apple.security.device.audio-input': True, 'com.apple.security.personal-information.calendars': True}),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                module = self.load_module()
                folder = Path(tmp)
                app, identity, listing = self.signing_fixture(module, folder, 'Developer ID Application: Example (TEAM123)', descriptions)
                captured = []
                entitlement_paths = []
                def run(command, **kwargs):
                    self.assertTrue(kwargs.get('check'))
                    if '--sign' in command:
                        self.assertIn('--timestamp', command)
                        self.assertEqual(command[command.index('--options') + 1], 'runtime')
                        self.assertNotIn('--deep', command)  # do not apply main-app rights to nested helpers
                        entitlement = Path(command[command.index('--entitlements') + 1])
                        entitlement_paths.append(entitlement)
                        captured.append(plistlib.loads(entitlement.read_bytes()))
                with patch.object(module, 'PIN', folder / 'pin.json'), patch.dict(os.environ, {}, clear=True), \
                     patch.object(module.subprocess, 'check_output', return_value=listing) as identities, \
                     patch.object(module.subprocess, 'run', side_effect=run) as commands, \
                     patch('sys.argv', ['signing.py', '--sign', str(app)]):
                    module.main()
                    module.main()  # persisted identity must behave identically on a later rebuild
                self.assertEqual(captured, [expected, expected])
                self.assertTrue(all(not p.exists() for p in entitlement_paths))
                self.assertEqual(commands.call_args_list[-1].args[0], ['codesign', '--verify', '--deep', '--strict', str(app)])
                self.assertEqual(identities.call_count, 2)
                self.assertEqual(identities.call_args.args[0], ['security', 'find-identity', '-v', '-p', 'codesigning'])
                self.assertEqual(json.loads((folder / 'pin.json').read_text())['identity'], identity)

    def test_pinned_identity_label_controls_profile_among_multiple_certificates(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            app, identity, listing = self.signing_fixture(module, folder, 'Developer ID Application: Example (TEAM123)',
                                                        {'NSMicrophoneUsageDescription': 'Record meeting audio'})
            pin = folder / 'pin.json'; pin.write_text(json.dumps({'identity': identity}))
            listing = f'  1) {"B" * 40} "Apple Development: Example (TEAM123)"\n' + listing.replace('1)', '2)')
            with patch.object(module, 'PIN', pin), patch.dict(os.environ, {}, clear=True), \
                 patch.object(module.subprocess, 'check_output', return_value=listing), patch.object(module.subprocess, 'run') as commands, \
                 patch('sys.argv', ['signing.py', '--sign', str(app)]):
                module.main()
            signed = commands.call_args_list[0].args[0]
            self.assertEqual(signed[signed.index('--sign') + 1], identity)
            self.assertIn('--timestamp', signed)
            self.assertIn('--options', signed)

    def test_apple_development_and_explicit_adhoc_keep_existing_signing_behavior(self):
        for label, requested in (('Apple Development: Example (TEAM123)', None), ('', '-')):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                module = self.load_module()
                folder = Path(tmp)
                app, identity, listing = self.signing_fixture(module, folder, label)
                env = {} if requested is None else {'MEETING_OS_SIGNING_IDENTITY': requested}
                with patch.object(module, 'PIN', folder / 'pin.json'), patch.dict(os.environ, env, clear=True), \
                     patch.object(module.subprocess, 'check_output', return_value=listing), patch.object(module.subprocess, 'run') as commands, \
                     patch('sys.argv', ['signing.py', '--sign', str(app)]):
                    module.main()
                self.assertEqual(commands.call_args_list[0].args[0],
                                 ['codesign', '--force', '--deep', '--sign', requested or identity, str(app)])

    def test_developer_id_signing_failure_never_verifies_or_retries_without_entitlements(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            app, _, listing = self.signing_fixture(module, folder, 'Developer ID Application: Example (TEAM123)',
                                                  {'NSMicrophoneUsageDescription': 'Record meeting audio'})
            paths = []
            def fail(command, **kwargs):
                if '--entitlements' in command: paths.append(Path(command[command.index('--entitlements') + 1]))
                raise subprocess.CalledProcessError(1, command)
            with patch.object(module, 'PIN', folder / 'pin.json'), patch.dict(os.environ, {}, clear=True), \
                 patch.object(module.subprocess, 'check_output', return_value=listing), patch.object(module.subprocess, 'run', side_effect=fail) as commands, \
                 patch.object(module, 'verify') as verify, patch('sys.argv', ['signing.py', '--sign', str(app)]):
                with self.assertRaises(subprocess.CalledProcessError): module.main()
            self.assertEqual(commands.call_count, 1)
            verify.assert_not_called()
            self.assertEqual(len(paths), 1)
            self.assertFalse(paths[0].exists())

    def test_missing_certificate_name_fails_before_signing(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as tmp:
            identity = 'A' * 40
            with patch.object(module, 'PIN', Path(tmp) / 'pin.json'), patch.dict(os.environ, {}, clear=True), \
                 patch.object(module.subprocess, 'check_output', return_value=f'  1) {identity} \n'), \
                 patch.object(module.subprocess, 'run') as commands, patch.object(module, 'verify') as verify, \
                 patch('sys.argv', ['signing.py', '--sign', str(Path(tmp) / 'app')]):
                with self.assertRaisesRegex(ValueError, 'certificate name'): module.main()
            commands.assert_not_called()
            verify.assert_not_called()


if __name__ == '__main__':
    unittest.main()
