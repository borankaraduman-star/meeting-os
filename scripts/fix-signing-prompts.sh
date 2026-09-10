#!/bin/sh
# Stops the "codesign wants to use key 'Meeting OS Local'" password dialogs for good.
# A self-signed identity imported with `security import` carries no partition list, so macOS asks on EVERY
# signing (each build, each update) and "Always Allow" never sticks. Granting the apple-tool/codesign partitions
# needs the login keychain password once; `security` asks for it in the terminal, nothing is stored.
set -u
KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"
# Whatever identity build/signing-identity.json pins ("Meeting OS Local" on a teammate's Mac, an Apple Development
# certificate on a developer's): the partition list is granted to every signing key in the login keychain.
COUNT="$(/usr/bin/security find-identity -v -p codesigning 2>/dev/null | grep -c ') [0-9A-F]\{40\} ' || true)"
if [ "$COUNT" = 0 ]; then
  echo "Bu Mac'te kod imzalama sertifikası yok; yapılacak bir şey yok (önce scripts/install.sh)."; exit 0
fi
/usr/bin/security find-identity -v -p codesigning 2>/dev/null | grep ') [0-9A-F]\{40\} ' | sed 's/^ *//'
echo "Mac giriş parolanız bir kez sorulacak (yukarıdaki imzalama anahtarına codesign için kalıcı izin veriliyor)…"
if /usr/bin/security set-key-partition-list -S apple-tool:,apple:,codesign: -s "$KEYCHAIN" >/dev/null; then
  echo "Tamam: derleme ve güncellemeler artık Anahtar Zinciri penceresi açmaz."
else
  echo "Olmadı. Elle: Anahtar Zinciri Erişimi → giriş → imzalama sertifikasının özel anahtarı → Bilgi Al → Erişim Denetimi → 'Tüm uygulamalara izin ver'." >&2
  exit 1
fi
