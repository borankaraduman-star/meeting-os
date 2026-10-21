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

    def test_bundle_is_torch_free(self):
        """2026-10-22: the voiceprint (Resemblyzer's LSTM) and the VAD (Silero) run through ONNX, so torch and
        everything only it or Resemblyzer's librosa mel pulled in stay out. ~700 MB of the 1 GB app was that."""
        names = {s.split('==')[0].lower() for s in M.PACKAGES + M.NO_DEPS_PACKAGES}
        for gone in ('torch', 'torchaudio', 'silero-vad', 'resemblyzer', 'librosa', 'numba', 'llvmlite',
                     'scikit-learn', 'sympy', 'webrtcvad'):
            self.assertNotIn(gone, names)
            self.assertIn(gone, {e.lower() for e in M.EXCLUDED_PACKAGES})
        self.assertEqual(M.NO_DEPS_PACKAGES, [])
        for needed in ('numpy', 'scipy', 'soundfile', 'onnxruntime', 'sherpa-onnx', 'sherpa-onnx-core'):
            self.assertIn(needed, names)

    def test_no_module_imports_a_package_the_bundle_does_not_carry_at_top_level(self):
        """A module-level import of an excluded package would break `import meeting_os.<x>` in the bundle
        for every path, not just the local one. Lazy imports inside a function are the local-model paths,
        each behind optional.require (a Turkish sentence instead of ModuleNotFoundError)."""
        import re
        banned = {'torch', 'torchaudio', 'silero_vad', 'resemblyzer', 'librosa', 'numba', 'sklearn', 'webrtcvad',
                  'mlx', 'mlx_lm', 'mlx_whisper', 'outlines', 'transformers', 'whisper', 'speechbrain', 'pyannote',
                  'huggingface_hub'}
        for path in (ROOT / 'meeting_os').glob('*.py'):
            for line in path.read_text(encoding='utf-8').splitlines():
                m = re.match(r'(?:import|from)\s+([A-Za-z_][\w]*)', line)   # column 0 only: module level
                if m: self.assertNotIn(m.group(1), banned, f'{path.name}: {line}')

    def test_onnx_models_ship_inside_the_package_tree(self):
        """The two ONNX files live in meeting_os/assets, which REPO_TREES copies whole; nothing in REPO_EXCLUDE
        may drop them, and models/ (gitignored, Sherpa only) is not where the code looks."""
        self.assertIn('meeting_os', M.REPO_TREES)
        for name in ('resemblyzer.onnx', 'silero_vad.onnx'):
            self.assertTrue((ROOT / 'meeting_os/assets' / name).is_file(), name)
            for pattern in M.REPO_EXCLUDE:
                self.assertFalse(Path(name).match(pattern), f'{pattern} {name} dosyasini disarida birakir')

    def test_onnxruntime_prune_keeps_the_python_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); ort = root / 'lib/python3.12/site-packages/onnxruntime'
            for sub in ('capi', 'transformers', 'quantization', 'tools'):
                (ort / sub).mkdir(parents=True)
            (ort / '__init__.py').write_text('')
            (ort / 'capi/onnxruntime_pybind11_state.so').write_bytes(b'b' * 64)
            (ort / 'capi/libonnxruntime.1.31.0.dylib').write_bytes(b'c' * 64)
            (ort / 'transformers/x.py').write_text('')
            M.prune(root)
            self.assertTrue((ort / 'capi/onnxruntime_pybind11_state.so').exists())
            self.assertTrue((ort / '__init__.py').exists())
            for gone in ('capi/libonnxruntime.1.31.0.dylib', 'transformers', 'quantization', 'tools'):
                self.assertFalse((ort / gone).exists(), gone)


class RepoContents(unittest.TestCase):
    def test_every_included_path_exists_in_the_checkout(self):
        for tree in M.REPO_TREES: self.assertTrue((ROOT / tree).is_dir(), tree)
        for file in M.REPO_FILES: self.assertTrue((ROOT / file).is_file(), file)
        for script in M.REPO_SCRIPTS: self.assertTrue((ROOT / 'scripts' / script).is_file(), script)

    def test_every_script_a_module_runs_is_shipped_and_nothing_else(self):
        """probe.py and reports.py NAME install.sh / update.sh / fix-signing-prompts.sh, but only inside hint
        strings. updater.py RUNS scripts/swap-update.sh (the bundle update channel). The 2026-09-13 fresh-Mac
        simulation found the old guard blind — it looked for `Popen(['sh'` while updater spells it
        `Popen(['/bin/sh'` — and every shipped bundle unable to update itself. This one finds the real
        `scripts/<name>` every module hands to a shell and demands the manifest ship exactly those."""
        import re
        needed = set()
        for path in (ROOT / 'meeting_os').glob('*.py'):
            text = path.read_text(encoding='utf-8')
            if re.search(r"(?:Popen|run)\(\[\s*['\"](?:/bin/)?sh['\"]", text):
                needed.update(re.findall(r"'scripts'\s*/\s*'([^']+\.sh)'", text))
                needed.update(re.findall(r"scripts/([A-Za-z0-9._-]+\.sh)", text))
        # update.sh is the GIT channel: updater.start runs it only when runtime.json says the install is not a
        # bundle, so a bundle never needs it. Everything else a module hands to a shell must ship.
        needed.discard('update.sh')
        self.assertEqual(sorted(needed), sorted(M.REPO_SCRIPTS))
        self.assertEqual(M.REPO_SCRIPTS, ['swap-update.sh'])

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
        self.assertEqual(d, {'python': 'runtime/bin/python3', 'repo': 'repo', 'bundled': True, 'version': '1.2.72',
                             'download_base': 'https://github.com/borankaraduman-star/meeting-os/releases/latest/download'})
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
