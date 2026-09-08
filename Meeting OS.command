#!/bin/zsh
set -eu
cd "${0:A:h}"
if [[ ! -d 'build/Meeting OS.app' ]]; then
  print 'Uygulama henüz kurulmamış. README.md içindeki kurulumu çalıştırın.'
  exit 1
fi
open 'build/Meeting OS.app'
