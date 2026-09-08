#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo 'Apple Silicon Mac gerekiyor (M1/M2/M3/M4 veya sonrası). Intel/Rosetta desteklenmiyor.' >&2
  exit 1
fi
major=$(sw_vers -productVersion | cut -d. -f1)
if (( major < 15 )); then echo 'macOS 15 veya sonrası gerekiyor.' >&2; exit 1; fi
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
export HOMEBREW_NO_ANALYTICS=1
if ! command -v brew >/dev/null; then
  echo 'Homebrew eksik. Resmi kurucu açılıyor; açıklamaları okuyup gerekiyorsa Mac parolanızı girin.'
  installer=$(mktemp -t meeting-os-homebrew)
  trap 'rm -f "$installer"' EXIT
  curl --fail --show-error --location https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$installer"
  /bin/bash "$installer"
fi
if ! xcrun --find swift >/dev/null 2>&1; then
  xcode-select --install || true
  echo 'Apple geliştirici araçlarının kurulumunu tamamlayıp Meeting OS.command dosyasını tekrar açın.' >&2
  exit 1
fi
if ! command -v python3.12 >/dev/null; then brew install python@3.12; fi
if ! command -v ffmpeg >/dev/null; then brew install ffmpeg; fi
if ! command -v cmake >/dev/null; then brew install cmake; fi
export MEETING_OS_PYTHON="$(command -v python3.12)"
echo 'Python paketleri ve modeller kuruluyor…'
/bin/sh scripts/setup.sh 2>&1 | tee installation.log
echo 'Kurulum tamamlandı. Meeting OS açılıyor.'
