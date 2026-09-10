#!/bin/sh
# Stops the "codesign wants to use key 'Meeting OS Local'" password dialogs for good.
# A self-signed identity imported with `security import` carries no partition list, so macOS asks on EVERY
# signing (each build, each update) and "Always Allow" never sticks. Granting the apple-tool/codesign partitions
# needs the login keychain password once; `security` asks for it in the terminal, nothing is stored.
set -u
KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"
if ! /usr/bin/security find-certificate -c 'Meeting OS Local' -Z "$KEYCHAIN" >/dev/null 2>&1; then
  echo "'Meeting OS Local' sertifikası bu Mac'te yok; yapılacak bir şey yok."; exit 0
fi
echo "Mac giriş parolanız bir kez sorulacak (imzalama anahtarına codesign için kalıcı izin veriliyor)…"
if /usr/bin/security set-key-partition-list -S apple-tool:,apple:,codesign: -s "$KEYCHAIN" >/dev/null; then
  echo "Tamam: derleme ve güncellemeler artık Anahtar Zinciri penceresi açmaz."
else
  echo "Olmadı. Elle: Anahtar Zinciri Erişimi → giriş → 'Meeting OS Local' özel anahtarı → Bilgi Al → Erişim Denetimi → 'Tüm uygulamalara izin ver'." >&2
  exit 1
fi
