#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
revision=52a939a2a762224e255d366c1182b2af4dd1a032
if [ ! -d build/whisper.cpp/.git ]; then
  git clone https://github.com/ggml-org/whisper.cpp.git build/whisper.cpp
fi
git -C build/whisper.cpp checkout "$revision"
cmake_bin="${CMAKE_BIN:-cmake}"
"$cmake_bin" -S build/whisper.cpp -B build/whisper.cpp/out -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF
"$cmake_bin" --build build/whisper.cpp/out --target whisper-cli -j 4
mkdir -p build/whisper-cpp/bin
cp build/whisper.cpp/out/bin/whisper-cli build/whisper-cpp/bin/whisper-cli
build/whisper-cpp/bin/whisper-cli --help
