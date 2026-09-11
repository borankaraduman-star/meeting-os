"""What goes inside `Meeting OS.app`, and what stays out.

`scripts/build-bundle.sh` asks this module for every list it uses (`python3 scripts/bundle_manifest.py
<list>`) and `tests/test_bundle_layout.py` checks the same lists without building anything. One source, so
the package the tests describe is the package the script actually produces.

The rule behind the lists: the bundle carries the CLOUD path only — record, assemble with ffmpeg, upload to
OpenRouter, diarize with Sherpa, embed voices with Resemblyzer. Local transcription and local analysis
(mlx, mlx-lm, mlx-whisper, outlines, transformers, whisper, speechbrain, pyarrow) are a development-machine
concern and would add gigabytes nobody on the receiving end can use.
"""
import json
import re
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------- runtime

PYTHON_VERSION = '3.12.14'
PYTHON_RELEASE = '20260901'            # astral-sh/python-build-standalone release tag
PYTHON_ASSET = f'cpython-{PYTHON_VERSION}+{PYTHON_RELEASE}-aarch64-apple-darwin-install_only.tar.gz'
PYTHON_RELEASE_URL = f'https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_RELEASE}'
PYTHON_URL = f'{PYTHON_RELEASE_URL}/{PYTHON_ASSET}'
PYTHON_SUMS_URL = f'{PYTHON_RELEASE_URL}/SHA256SUMS'
# The tarball unpacks to a single `python/` directory; it becomes Contents/Resources/runtime.
PYTHON_TAR_TOPLEVEL = 'python'

# ---------------------------------------------------------------- packages

#: Everything the cloud path imports, at the version `requirements-macos-tested.txt` pins. pip resolves the
#: transitive closure (httpx, requests, sympy, jinja2, joblib, soxr, …); the same requirements file is passed
#: as a --constraint, so anything pulled in that was measured on this Mac keeps its measured version.
#:
#: torchaudio is here although docs/BUNDLE.md leaves it out: `silero_vad/utils_vad.py` does a top-level
#: `import torchaudio`, so `import silero_vad` — which meeting_os/audio.py does for every VAD pass — cannot
#: work without it. It costs 4 MB, not the hundreds torch costs.
PACKAGES = [
    'numpy==2.5.3',
    'scipy==1.18.1',
    'soundfile==0.14.0',
    'huggingface_hub==1.30.0',
    'torch==2.14.0',
    'torchaudio==2.11.0',
    'silero-vad==6.2.1',
    'sherpa-onnx==1.13.7',
    'sherpa-onnx-core==1.13.7',
    'librosa==1.0.0',
    'numba==0.67.0',
    'llvmlite==0.49.0',
    'scikit-learn==1.9.0',
    'webrtcvad==2.0.10',
    'requests==2.34.2',
    'setuptools==80.10.2',
    'imageio-ffmpeg==0.6.0',
]

#: Installed with --no-deps. Resemblyzer still declares the abandoned `typing` backport, whose only wheel is
#: py2 and whose module file lands in site-packages next to the standard library's own `typing`. Its real
#: dependencies (librosa, numpy, scipy, torch, webrtcvad) are all in PACKAGES above.
NO_DEPS_PACKAGES = ['Resemblyzer==0.1.4']

#: Never in the bundle, whatever pulls them in: the local-model era.
EXCLUDED_PACKAGES = ['mlx', 'mlx-lm', 'mlx-metal', 'mlx-whisper', 'outlines', 'outlines_core',
                     'transformers', 'tokenizers', 'pyarrow', 'openai-whisper', 'speechbrain',
                     'pyannote.audio', 'tiktoken', 'sentencepiece']

CONSTRAINTS_FILE = 'requirements-macos-tested.txt'

# ---------------------------------------------------------------- repo/

#: Copied whole (minus REPO_EXCLUDE) into Contents/Resources/repo.
REPO_TREES = ['meeting_os']
#: Single files, at the same relative path.
REPO_FILES = ['vocabulary.txt', 'docs/KULLANIM.md', 'docs/MODEL_LOCK.json']
#: rsync patterns dropped from every tree.
REPO_EXCLUDE = ['__pycache__', '*.pyc', '*.pyo', '.DS_Store']
#: Nothing under scripts/ runs at runtime: probe.py and reports.py only NAME `scripts/install.sh`,
#: `scripts/update.sh` and `scripts/fix-signing-prompts.sh` inside hint strings, and the bundle channel
#: replaces the git update path altogether. Kept as an explicit empty list so a future runtime dependency
#: has somewhere obvious to go.
REPO_SCRIPTS: list = []
#: The recording helper, copied to repo/build/MeetingCapture.app (cli.py --capture-bin looks for it there).
CAPTURE_APP_DEST = 'build/MeetingCapture.app'

# ---------------------------------------------------------------- models/sherpa

#: The only model files the cloud path opens: speakers.py builds its Sherpa config from these two, and
#: `meeting-os-model.json` is what `doctor` lists. Paths are relative to models/sherpa.
SHERPA_FILES = [
    'meeting-os-model.json',
    'titanet-small.onnx',
    'sherpa-onnx-pyannote-segmentation-3-0/model.onnx',
]
#: Present in the checkout, read by nothing: the 38 MB alternative embedder, the tarball `titanet` was
#: extracted from, and the int8 segmentation model the config never names.
SHERPA_EXCLUDED = [
    'eres2net.onnx',
    'segmentation.tar.bz2',
    'sherpa-onnx-pyannote-segmentation-3-0/model.int8.onnx',
]
SHERPA_DEST = 'models/sherpa'

# ---------------------------------------------------------------- pruning

#: Removed from the runtime after pip is done. Shell globs, relative to Contents/Resources/runtime.
PRUNE_GLOBS = [
    'share',
    'include',
    'lib/pkgconfig',
    'lib/tcl*', 'lib/tk*', 'lib/itcl*', 'lib/tdbc*', 'lib/thread*', 'lib/sqlite3*',
    'lib/libtcl*', 'lib/libtk*',
    'lib/python*/idlelib',
    'lib/python*/turtledemo',
    'lib/python*/tkinter',
    'lib/python*/lib2to3',
    'lib/python*/ensurepip',
    'lib/python*/site-packages/torch/include',
    'lib/python*/site-packages/torch/test',
]
#: Directories with these names are removed wherever they appear. `testing` is NOT here: numpy.testing and
#: torch.testing are importable modules other code reaches for, unlike a `tests` package.
PRUNE_DIR_NAMES = ['__pycache__', 'tests', 'test']
#: Files with these suffixes are removed wherever they appear: static archives are link-time only, and the
#: bytecode goes with the __pycache__ directories anyway.
PRUNE_SUFFIXES = ['.a', '.pyc', '.pyo']

SIZE_BUDGET_BYTES = 1.3 * 1024**3

# ---------------------------------------------------------------- runtime.json

RUNTIME_JSON = 'runtime.json'
INVITE_JSON = 'invite.json'


def runtime_json(version):
    """Contents/Resources/runtime.json. Both paths are RELATIVE, which is the whole signal: App.swift
    resolves a path that does not start with `/` against Bundle.main.resourceURL, so the app works wherever
    the user dragged it."""
    return {'python': 'runtime/bin/python3', 'repo': 'repo', 'bundled': True, 'version': str(version)}


def version(repo):
    """`__version__` out of meeting_os/__init__.py, read as text: this runs under a Python that has none of
    the package's dependencies installed."""
    text = (Path(repo) / 'meeting_os/__init__.py').read_text(encoding='utf-8')
    match = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
    if not match: raise SystemExit('meeting_os/__init__.py icinde __version__ yok')
    return match.group(1)


# ---------------------------------------------------------------- prune

def prune(root):
    """Delete everything PRUNE_* names under `root`. Returns (removed paths, bytes freed) so the build log
    can say what the pruning was worth."""
    root = Path(root)
    removed, freed = [], 0

    def size(path):
        if path.is_symlink(): return 0
        if path.is_dir(): return sum(f.stat().st_size for f in path.rglob('*') if f.is_file() and not f.is_symlink())
        return path.stat().st_size

    def drop(path):
        nonlocal freed
        try: gone = size(path)
        except OSError: gone = 0
        if path.is_dir() and not path.is_symlink(): shutil.rmtree(path, ignore_errors=True)
        else: path.unlink(missing_ok=True)
        freed += gone; removed.append(str(path.relative_to(root)))

    for pattern in PRUNE_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.exists() or path.is_symlink(): drop(path)
    for path in sorted(root.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if not (path.exists() or path.is_symlink()): continue
        if path.is_dir() and not path.is_symlink() and path.name in PRUNE_DIR_NAMES: drop(path)
        elif path.is_file() and path.suffix in PRUNE_SUFFIXES: drop(path)
    return removed, freed


# ---------------------------------------------------------------- cli

def _lines(values): return '\n'.join(str(v) for v in values)


def main(argv):
    if not argv: raise SystemExit('kullanim: bundle_manifest.py <liste> [arg]')
    name, rest = argv[0], argv[1:]
    table = {
        'packages': lambda: _lines(PACKAGES),
        'no-deps-packages': lambda: _lines(NO_DEPS_PACKAGES),
        'excluded-packages': lambda: _lines(EXCLUDED_PACKAGES),
        'constraints-file': lambda: CONSTRAINTS_FILE,
        'repo-trees': lambda: _lines(REPO_TREES),
        'repo-files': lambda: _lines(REPO_FILES),
        'repo-exclude': lambda: _lines(REPO_EXCLUDE),
        'repo-scripts': lambda: _lines(REPO_SCRIPTS),
        'sherpa-files': lambda: _lines(SHERPA_FILES),
        'sherpa-dest': lambda: SHERPA_DEST,
        'capture-dest': lambda: CAPTURE_APP_DEST,
        'python-asset': lambda: PYTHON_ASSET,
        'python-url': lambda: PYTHON_URL,
        'python-sums-url': lambda: PYTHON_SUMS_URL,
        'python-toplevel': lambda: PYTHON_TAR_TOPLEVEL,
        'size-budget': lambda: int(SIZE_BUDGET_BYTES),
    }
    if name in table: print(table[name]()); return 0
    if name == 'version': print(version(rest[0])); return 0
    if name == 'runtime-json': print(json.dumps(runtime_json(rest[0]), ensure_ascii=False)); return 0
    if name == 'prune':
        removed, freed = prune(rest[0])
        print(f'{len(removed)} {freed}')
        return 0
    raise SystemExit(f'bilinmeyen liste: {name}')


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
