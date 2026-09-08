#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
revision=52a939a2a762224e255d366c1182b2af4dd1a032
source_dir=build/whisper.cpp
if [ ! -e "$source_dir/.git" ]; then
  git init "$source_dir"
fi
if ! git -C "$source_dir" rev-parse --git-dir >/dev/null 2>&1; then
  echo 'Whisper kaynak önbelleği geçersiz; dosyalar korundu. Yeni bir uygulama klasöründen kurulumu deneyin.' >&2
  exit 1
fi
# A valid .git directory does not prove the pinned commit finished downloading.
# Fetch only a missing pin; intact cached installations remain usable offline.
if ! git -C "$source_dir" cat-file -e "$revision^{commit}" 2>/dev/null; then
  git -C "$source_dir" fetch --depth 1 https://github.com/ggml-org/whisper.cpp.git "$revision"
fi
git -C "$source_dir" checkout --detach "$revision"
cmake_bin="${CMAKE_BIN:-cmake}"
"$cmake_bin" -S build/whisper.cpp -B build/whisper.cpp/out -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF
"$cmake_bin" --build build/whisper.cpp/out --target whisper-cli -j 4
mkdir -p build/whisper-cpp/bin
cp build/whisper.cpp/out/bin/whisper-cli build/whisper-cpp/bin/whisper-cli
build/whisper-cpp/bin/whisper-cli --help
