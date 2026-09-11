"""What `scripts/build-bundle.sh` puts in `Meeting OS.app`, checked without building it.

The build takes twenty minutes and a gigabyte of wheels; these tests take a second. They can do that because
every list the script uses lives in `scripts/bundle_manifest.py` and nowhere else — so what is asserted here
is what the script will actually copy, install and delete.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

import bundle_manifest as M   # noqa: E402
from meeting_os import team_cloud   # noqa: E402


class ManifestLists(unittest.TestCase):
    def test_pins_come_from_the_measured_requirements_file(self):
        """A package in the bundle at a version nobody measured is the bug this catches."""
        pinned = {}
        for line in (ROOT / M.CONSTRAINTS_FILE).read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '==' not in line: continue
            name, version = line.split('==', 1)
            pinned[name.strip().lower().replace('_', '-')] = version.strip()
        untested = []
        for spec in M.PACKAGES + M.NO_DEPS_PACKAGES:
            self.assertIn('==', spec, spec)
            name, version = spec.split('==')
            key = name.lower().replace('_', '-')
            if key not in pinned: untested.append(spec); continue
            self.assertEqual(pinned[key], version, f'{name}: manifest {version}, olculmus {pinned[key]}')
        # imageio-ffmpeg is the one package the requirements file never had: it exists to carry the static
        # ffmpeg binary, which a checkout gets from Homebrew instead.
        self.assertEqual(untested, ['imageio-ffmpeg==0.6.0'])

    def test_local_model_packages_stay_out(self):
        names = {s.split('==')[0].lower() for s in M.PACKAGES + M.NO_DEPS_PACKAGES}
        for banned in M.EXCLUDED_PACKAGES:
            self.assertNotIn(banned.lower(), names, f'{banned} pakete girmemeli')
        for banned in ('mlx', 'mlx-lm', 'mlx-whisper', 'outlines', 'transformers', 'pyarrow'):
            self.assertIn(banned, M.EXCLUDED_PACKAGES)

    def test_resemblyzer_is_installed_without_its_typing_backport(self):
        """Resemblyzer still asks for `typing`, whose only wheel is py2 and whose module would sit in
        site-packages beside the standard library's own. Its real dependencies are all in PACKAGES."""
        self.assertEqual(M.NO_DEPS_PACKAGES, ['Resemblyzer==0.1.4'])
        names = {s.split('==')[0].lower() for s in M.PACKAGES}
        for real in ('librosa', 'numpy', 'scipy', 'torch', 'webrtcvad'):
            self.assertIn(real, names)

    def test_silero_needs_torchaudio(self):
        """docs/BUNDLE.md leaves torchaudio out; silero_vad/utils_vad.py imports it at module level, so
        `import silero_vad` — every VAD pass — would raise without it. 4 MB, and the bundle verification step
        imports silero_vad on purpose."""
        names = {s.split('==')[0].lower() for s in M.PACKAGES}
        self.assertIn('silero-vad', names)
        self.assertIn('torchaudio', names)


class RepoContents(unittest.TestCase):
    def test_every_included_path_exists_in_the_checkout(self):
        for tree in M.REPO_TREES: self.assertTrue((ROOT / tree).is_dir(), tree)
        for file in M.REPO_FILES: self.assertTrue((ROOT / file).is_file(), file)
        for script in M.REPO_SCRIPTS: self.assertTrue((ROOT / 'scripts' / script).is_file(), script)

    def test_nothing_under_scripts_is_needed_at_runtime(self):
        """probe.py and reports.py NAME install.sh / update.sh / fix-signing-prompts.sh, but only inside hint
        strings. If a module ever starts running one, this list has to grow and this test says so."""
        self.assertEqual(M.REPO_SCRIPTS, [])
        runner = []
        for path in (ROOT / 'meeting_os').glob('*.py'):
            text = path.read_text(encoding='utf-8')
            for marker in ("run(['sh'", 'Popen(["sh"', "Popen(['sh'", "'scripts/build"):
                if marker in text: runner.append(path.name)
        self.assertEqual(runner, [])

    def test_sherpa_subset_is_exactly_what_speakers_py_opens(self):
        """speakers.py names two model files and diarization_checkpoints.py checks the same two. Everything
        else under models/sherpa is 45 MB of history."""
        speakers = (ROOT / 'meeting_os/speakers.py').read_text(encoding='utf-8')
        self.assertIn("'titanet-small.onnx'", speakers)
        self.assertIn("'sherpa-onnx-pyannote-segmentation-3-0/model.onnx'", speakers)
        self.assertIn('titanet-small.onnx', M.SHERPA_FILES)
        self.assertIn('sherpa-onnx-pyannote-segmentation-3-0/model.onnx', M.SHERPA_FILES)
        for dropped in M.SHERPA_EXCLUDED:
            self.assertNotIn(dropped, M.SHERPA_FILES)
            self.assertNotIn(Path(dropped).name, speakers)
        self.assertEqual(sorted(set(M.SHERPA_FILES)), sorted(M.SHERPA_FILES))

    def test_capture_helper_lands_where_the_cli_looks_for_it(self):
        cli = (ROOT / 'meeting_os/cli.py').read_text(encoding='utf-8')
        self.assertIn(f"{M.CAPTURE_APP_DEST}/Contents/MacOS/MeetingCapture", cli)


class BuildScript(unittest.TestCase):
    """The script must keep asking the manifest instead of growing its own copy of a list."""

    def setUp(self):
        self.text = (ROOT / 'scripts/build-bundle.sh').read_text(encoding='utf-8')

    def test_script_reads_every_list_from_the_manifest(self):
        for query in ('packages', 'no-deps-packages', 'repo-trees', 'repo-files', 'repo-exclude',
                      'sherpa-files', 'python-asset', 'python-url', 'runtime-json', 'prune'):
            self.assertIn(f'ask {query}', self.text, f'betik {query} listesini manifestten almiyor')

    def test_script_never_signs_or_publishes(self):
        """Signing is Boran's Mac, after this script. A build-bundle.sh that signs would ask for a Keychain
        password in a terminal nobody is watching. Comment lines are exempt: the header says where signing
        happens instead, which is the point."""
        code = [l for l in self.text.splitlines() if l.strip() and not l.lstrip().startswith('#')]
        for line in code:
            for banned in ('codesign', 'signing.py', '/usr/bin/security', 'ditto -c', 'install.sh', 'update.sh'):
                self.assertNotIn(banned, line, f'{banned}: {line}')

    def test_overridable_inputs_have_defaults(self):
        for name in ('REPO', 'CAPTURE_APP', 'MODELS_DIR', 'DOWNLOADS', 'HOST_PY', 'VENV_PY'):
            self.assertIn(f'{name}=${{{name}:-', self.text, f'{name} icin varsayilan yok')

    def test_download_is_cached_and_checksummed(self):
        self.assertIn('shasum -a 256', self.text)
        self.assertIn('.sha256', self.text)
        self.assertIn('if [ ! -f "$tarball" ]', self.text)   # re-runnable: a second run reuses the tarball


class PruneRules(unittest.TestCase):
    def test_prune_removes_the_dead_weight_and_keeps_the_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / 'lib/python3.12/site-packages'
            for path in ['bin', 'lib/tcl8.6', 'lib/tk8.6', 'lib/python3.12/idlelib',
                         'lib/python3.12/turtledemo', 'lib/python3.12/test', 'share/man', 'include/python3.12',
                         'lib/python3.12/site-packages/numpy/tests', 'lib/python3.12/site-packages/numpy/testing',
                         'lib/python3.12/site-packages/torch/include', 'lib/python3.12/site-packages/torch/lib',
                         'lib/python3.12/site-packages/torch/__pycache__']:
                (root / path).mkdir(parents=True, exist_ok=True)
            (root / 'bin/python3').write_text('#!/bin/sh\n')
            (root / 'lib/libpython3.12.dylib').write_bytes(b'x' * 100)
            (root / 'lib/python3.12/config-3.12-darwin').mkdir(parents=True)
            (root / 'lib/python3.12/config-3.12-darwin/libpython3.12.a').write_bytes(b'y' * 4096)
            (site / 'numpy/testing/__init__.py').write_text('')
            (site / 'numpy/tests/test_all.py').write_text('x' * 10)
            (site / 'torch/lib/libtorch.dylib').write_bytes(b'z' * 2048)
            (site / 'torch/__pycache__/x.cpython-312.pyc').write_bytes(b'p' * 8)
            removed, freed = M.prune(root)
            self.assertGreater(freed, 4096)
            for gone in ['lib/tcl8.6', 'lib/tk8.6', 'lib/python3.12/idlelib', 'lib/python3.12/turtledemo',
                         'lib/python3.12/test', 'share', 'include',
                         'lib/python3.12/site-packages/numpy/tests',
                         'lib/python3.12/site-packages/torch/include',
                         'lib/python3.12/site-packages/torch/__pycache__',
                         'lib/python3.12/config-3.12-darwin/libpython3.12.a']:
                self.assertFalse((root / gone).exists(), f'{gone} silinmeliydi')
            for kept in ['bin/python3', 'lib/libpython3.12.dylib',
                         'lib/python3.12/site-packages/numpy/testing/__init__.py',
                         'lib/python3.12/site-packages/torch/lib/libtorch.dylib']:
                self.assertTrue((root / kept).exists(), f'{kept} silinmemeliydi')
            self.assertIn('share', removed)
            # Idempotent: a second pass on a pruned tree finds nothing and frees nothing.
            self.assertEqual(M.prune(root), ([], 0))

    def test_testing_packages_are_never_treated_as_tests(self):
        self.assertNotIn('testing', M.PRUNE_DIR_NAMES)
        self.assertIn('tests', M.PRUNE_DIR_NAMES)
        self.assertIn('__pycache__', M.PRUNE_DIR_NAMES)
        self.assertIn('.a', M.PRUNE_SUFFIXES)


class RuntimeJson(unittest.TestCase):
    def test_shape_is_relative_and_carries_the_version(self):
        d = M.runtime_json('1.2.72')
        self.assertEqual(d, {'python': 'runtime/bin/python3', 'repo': 'repo', 'bundled': True, 'version': '1.2.72'})
        self.assertFalse(d['python'].startswith('/'), 'mutlak yol paketi tasinamaz yapar')
        self.assertFalse(d['repo'].startswith('/'))
        json.dumps(d)   # must survive the round trip the script writes it through

    def test_swift_reads_exactly_these_keys(self):
        """App.swift decodes runtime.json through one CodingKeys list; a key added here and forgotten there
        is silently dropped, and a bundled app would quietly behave like a checkout."""
        swift = (ROOT / 'desktop/Sources/MeetingOS/App.swift').read_text(encoding='utf-8')
        keys = next(l for l in swift.splitlines() if 'CodingKey' in l and 'case' in l)
        declared = {name.strip() for name in keys.split('case', 1)[1].split('}')[0].split(',')}
        self.assertEqual(declared, set(M.runtime_json('1.0.0')))
        self.assertIn('resolved(resources:', swift)

    def test_version_is_read_out_of_the_package(self):
        from meeting_os import __version__
        self.assertEqual(M.version(ROOT), __version__)


class ShippedInvite(unittest.TestCase):
    """`--invite` writes `team_cloud.invite_file_text(...)`; the first launch hands that text straight back to
    `team_cloud.accept_invite`. If those two ever stop agreeing, a teammate opens a dead app."""

    def test_invite_file_round_trips_into_a_fresh_data_folder(self):
        token = 'a1b2c3d4' * 4
        with tempfile.TemporaryDirectory() as tmp:
            sender, receiver = Path(tmp) / 'sender', Path(tmp) / 'receiver'
            sender.mkdir(); receiver.mkdir()
            team_cloud.join(sender, token)
            (sender / 'openrouter.key').write_text('sk-or-v1-secret\n', encoding='utf-8')
            os.chmod(sender / 'openrouter.key', 0o600)
            text = team_cloud.invite_file_text(sender, include_key=True)
            self.assertTrue(text.strip(), 'davet dosyasi bos')
            payload = json.loads(text)
            self.assertEqual(payload['team'], token)
            self.assertEqual(payload['key'], 'sk-or-v1-secret')

            # accept_invite ends with a network sync; the join itself is what is under test.
            original = team_cloud.sync
            team_cloud.sync = lambda data_dir, *a, **k: {'pushed': 0, 'pulled': 0, 'hosts': []}
            try: result = team_cloud.accept_invite(receiver, text)
            finally: team_cloud.sync = original
            self.assertTrue(result.get('joined'), result)
            self.assertTrue(result.get('key_written'))
            self.assertEqual(team_cloud.token(receiver), token)
            self.assertEqual((receiver / 'openrouter.key').read_text(encoding='utf-8').strip(), 'sk-or-v1-secret')
            self.assertEqual(team_cloud.team_id_short(token), result['team_id_short'])

    def test_a_build_without_the_flag_ships_no_invite(self):
        script = (ROOT / 'scripts/build-bundle.sh').read_text(encoding='utf-8')
        self.assertIn('rm -f "$resources/invite.json"', script)
        self.assertIn('invite_file_text', script)
        # --invite ships the team only; --invite-with-key adds this Mac's key (11 Sep 2026: one key per teammate).
        self.assertIn("include_key=os.environ.get('INVITE_KEY') == '1'", script)
        self.assertIn('--invite-with-key', script)

    def test_swift_reads_the_file_the_script_writes(self):
        swift = (ROOT / 'desktop/Sources/MeetingOS/BundleInvite.swift').read_text(encoding='utf-8')
        self.assertIn(f'static let fileName="{M.INVITE_JSON}"', swift)


if __name__ == '__main__':
    unittest.main()
