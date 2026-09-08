#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo 'Meeting OS requires an Apple Silicon Mac.' >&2; exit 1
fi
if ! command -v ffmpeg >/dev/null && [ ! -x /opt/homebrew/bin/ffmpeg ]; then
  echo 'Install ffmpeg first (for example: brew install ffmpeg).' >&2; exit 1
fi
if [ ! -x .venv/bin/python ]; then
  "${MEETING_OS_PYTHON:-python3.12}" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements-macos-tested.txt
.venv/bin/python -m pip install -e '.[mlx,speakers]'
.venv/bin/python scripts/fetch-recommended.py
scripts/build-capture.sh
scripts/build-desktop.sh
.venv/bin/python -m meeting_os doctor
