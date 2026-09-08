#!/bin/zsh
set -eu
set -o pipefail
cd "${0:A:h}"
if [[ ! -d 'build/Meeting OS.app' ]]; then
  print 'Meeting OS ilk kurulum: gerekli araçlar ve yerel modeller indirilecek.'
  print 'İnternet bağlantısını ve bu pencereyi açık tutun. Kurulum birkaç GB indirebilir.'
  if ! /bin/bash scripts/install-mac.sh; then
    print '\nKurulum tamamlanamadı. Yukarıdaki açıklamayı kontrol edin.'
    if [[ -f installation.log ]]; then print "Kurulum günlüğü: $PWD/installation.log"; fi
    if [[ -t 0 ]]; then read '?Pencereyi kapatmak için Enter…'; fi
    exit 1
  fi
fi
open 'build/Meeting OS.app'
