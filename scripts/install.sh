#!/bin/sh
# Meeting OS — tek komutluk kurulum (yeni bir Mac ya da yeni bir ekip arkadaşı için).
#
#   git clone -b v0.1 https://github.com/borankaraduman-star/meeting-os.git ~/meeting-os
#   sh ~/meeting-os/scripts/install.sh
#
# Tekrar tekrar çalıştırılabilir: kurulu olanı yeniden kurmaz, girilmiş adı ve anahtarı korur.
# Zoom'un kapalı olması gerekmez. root/sudo ile çalıştırılmaz.
set -eu
set -o pipefail 2>/dev/null || true   # setup.sh çıktısı tee'ye gider; hatası tee'nin başarısı altında kaybolmasın
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
DATA="$HOME/Library/Application Support/MeetingOS"
KEYCHAIN_SERVICE='local.boran.meeting-os.openrouter'   # desktop/Sources/MeetingOS/OpenRouterImport.swift ve meeting_os/openrouter.py aynı adı okur

if [ "$(id -u)" = 0 ]; then
  echo 'Bu betiği sudo ile çalıştırmayın; kendi kullanıcınızla çalıştırın.' >&2; exit 1
fi
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo 'Apple Silicon Mac gerekiyor (M1/M2/M3/M4 veya sonrası). Intel/Rosetta desteklenmiyor.' >&2; exit 1
fi
if [ "$(sw_vers -productVersion | cut -d. -f1)" -lt 15 ]; then
  echo 'macOS 15 veya sonrası gerekiyor.' >&2; exit 1
fi

PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"; export PATH
HOMEBREW_NO_ANALYTICS=1; export HOMEBREW_NO_ANALYTICS

echo '1/6 · Gerekli araçlar'
if ! command -v brew >/dev/null; then
  echo 'Homebrew eksik. Resmi kurucu açılıyor; açıklamaları okuyup gerekiyorsa Mac parolanızı girin.'
  installer="$(mktemp -t meeting-os-homebrew)"
  trap 'rm -f "$installer"' EXIT
  curl --fail --show-error --location https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$installer"
  /bin/bash "$installer"
fi
if ! xcrun --find swift >/dev/null 2>&1; then
  xcode-select --install || true
  echo 'Apple geliştirici araçlarının kurulumunu tamamlayın, sonra bu betiği tekrar çalıştırın.' >&2
  exit 1
fi
for tool in python3.12 ffmpeg cmake; do
  case "$tool" in python3.12) formula='python@3.12';; *) formula="$tool";; esac
  if ! command -v "$tool" >/dev/null; then echo "  $tool kuruluyor…"; brew install "$formula"; fi
done
MEETING_OS_PYTHON="$(command -v python3.12)"; export MEETING_OS_PYTHON

# İmzalama kimliği derlemenin son adımında gerekiyor; gigabaytlarca indirmeden önce burada bakılır.
# scripts/signing.py otomatik ad-hoc imzaya düşmez: kimlik yoksa ya da birden fazlaysa derleme durur.
if [ ! -f build/signing-identity.json ] && [ -z "${MEETING_OS_SIGNING_IDENTITY:-}" ]; then
  identities="$(/usr/bin/security find-identity -v -p codesigning 2>/dev/null | grep -c ') [0-9A-F]\{40\} ' || true)"
  if [ "$identities" = 0 ]; then
    keychain="$HOME/Library/Keychains/login.keychain-db"
    certdir="$(mktemp -d -t meeting-os-cert)"
    # An earlier run whose trust dialog was cancelled left the certificate imported but untrusted, so
    # find-identity still reports 0. Importing a second one would make "Meeting OS Local" ambiguous and this
    # step would fail forever: if the certificate is already there, only the trust step is repeated.
    if /usr/bin/security find-certificate -c 'Meeting OS Local' -Z "$keychain" >/dev/null 2>&1; then
      echo "'Meeting OS Local' sertifikası zaten var ama güvenilir değil; yalnızca güven adımı yineleniyor (macOS parola soracak)…"
      ( /usr/bin/security find-certificate -c 'Meeting OS Local' -p "$keychain" > "$certdir/cert.pem" &&
        security add-trusted-cert -r trustRoot -p codeSign -k "$keychain" "$certdir/cert.pem"
      ) || echo "Sertifikaya güven verilemedi; aşağıdaki elle adımı uygulayın." >&2
    else
      # No certificate at all (a fresh Mac): make one self-signed code-signing identity in the login keychain.
      # The trust step opens one macOS password dialog; that is the only interactive part of the whole install.
      echo "Kod imzalama sertifikası yok; 'Meeting OS Local' adıyla kendinden imzalı bir tane oluşturuluyor (macOS bir kez parola soracak)…"
      (
        cd "$certdir" &&
        openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=Meeting OS Local/O=Meeting OS" -keyout key.pem -out cert.pem \
          -addext "keyUsage=critical,digitalSignature" -addext "extendedKeyUsage=critical,codeSigning" -addext "basicConstraints=critical,CA:false" >/dev/null 2>&1 &&
        { openssl pkcs12 -export -inkey key.pem -in cert.pem -out id.p12 -passout pass:meetingos -legacy >/dev/null 2>&1 || openssl pkcs12 -export -inkey key.pem -in cert.pem -out id.p12 -passout pass:meetingos >/dev/null 2>&1; } &&
        security import id.p12 -k "$keychain" -P meetingos -T /usr/bin/codesign -T /usr/bin/security >/dev/null &&
        security add-trusted-cert -r trustRoot -p codeSign -k "$keychain" cert.pem
      ) || echo "Sertifika kendiliğinden oluşturulamadı; aşağıdaki elle adımı uygulayın." >&2
    fi
    rm -rf "$certdir"
    # Without a partition list codesign asks for the keychain password on EVERY signing (each build and each
    # update) and "Always Allow" never sticks — that was the dialog storm of 10 Sep 2026. One password now, in
    # the terminal, fixes it for good. scripts/fix-signing-prompts.sh does the same on an already-installed Mac.
    /bin/sh "$(dirname "$0")/fix-signing-prompts.sh" || true
    identities="$(/usr/bin/security find-identity -v -p codesigning 2>/dev/null | grep -c ') [0-9A-F]\{40\} ' || true)"
  fi
  if [ "$identities" != 1 ]; then
    echo "Kod imzalama sertifikası bulunamadı ya da birden fazla var (bulunan: $identities)." >&2
    cat >&2 <<'CERT'
Uygulama macOS izinlerini koruyabilmek için sabit bir imzayla derlenir. Bir kez yapın:
  Anahtar Zinciri Erişimi → menü: Sertifika Yardımcısı → Sertifika Oluştur…
    Ad: Meeting OS · Kimlik türü: Kendinden imzalı kök · Sertifika türü: Kod İmzalama
Sonra bu betiği tekrar çalıştırın. Birden fazla sertifika varsa:
  MEETING_OS_SIGNING_IDENTITY=<SHA-1> sh scripts/install.sh
(SHA-1 listesi: security find-identity -v -p codesigning)
CERT
    exit 1
  fi
fi

echo '2/6 · Python ortamı, modeller ve uygulama derlemesi (ilk seferde birkaç GB indirir)'
/bin/sh scripts/setup.sh 2>&1 | tee installation.log

PY=".venv/bin/python"
# Bir ayarı yazar ve etkin değeri geri okur; geçersiz değeri meeting_os/reports.py sessizce yok sayar.
setting() { "$PY" -m meeting_os reports settings --set "$1=$2" >/dev/null; }
read_setting() { "$PY" - "$1" <<'PY'
import sys
from pathlib import Path
from meeting_os.reports import load_settings
print(load_settings(Path.home()/'Library/Application Support/MeetingOS').get(sys.argv[1]) or '')
PY
}

echo '3/6 · Adınız'
current="$(read_setting user_name)"
if [ -t 0 ]; then
  printf '  Toplantılarda mikrofon kaydınız bu adla etiketlenir [%s]: ' "$current"
  read -r name || name=''
  if [ -n "$name" ]; then setting user_name "$name"; fi
else
  echo "  Etkileşimli değil; ad değişmedi ($current). Sonra: Ayarlar → Genel → Adınız."
fi
echo "  Ad: $(read_setting user_name)"

echo '4/6 · OpenRouter API anahtarı'
if /usr/bin/security find-generic-password -s "$KEYCHAIN_SERVICE" -a openrouter >/dev/null 2>&1; then
  echo '  Anahtar zaten Anahtar Zinciri’nde; değiştirmek için uygulamadaki OpenRouter penceresini kullanın.'
elif [ -t 0 ]; then
  echo '  https://openrouter.ai/keys adresinden bir anahtar oluşturun (yazıya çevirme ≈ $0,10/saat).'
  printf '  Anahtar (görünmez, boş bırakılırsa atlanır): '
  stty -echo 2>/dev/null || true
  read -r key || key=''
  stty echo 2>/dev/null || true
  echo
  case "$key" in
    '') echo '  Atlandı; uygulama ilk bulut işleminde soracak.' ;;
    *[[:space:]]*) echo '  Anahtarda boşluk var; kaydedilmedi. Uygulamadan girebilirsiniz.' >&2 ;;
    *)
      # Anahtar `security -i` girdisinden okunur; komut satırında geçmediği için `ps` çıktısında görünmez.
      printf 'add-generic-password -U -s %s -a openrouter -w %s\n' "$KEYCHAIN_SERVICE" "$key" | /usr/bin/security -i >/dev/null
      echo '  Anahtar macOS Anahtar Zinciri’ne kaydedildi.' ;;
  esac
else
  echo '  Etkileşimli değil; anahtar sorulmadı. Uygulama ilk bulut işleminde soracak.'
fi

echo '5/6 · Kurulum denetimi'
"$PY" -m meeting_os doctor || echo '  Doctor uyarı verdi; ayrıntı yukarıda. Uygulama yine de açılabilir.'

echo '6/6 · Hazır'
mkdir -p "$DATA"
cat <<'NEXT'

Sırada üç adım var:
  1. Uygulamayı açın: "Meeting OS.command" dosyasını çift tıklayın (kurulan uygulama: build/Meeting OS.app).
  2. İlk kayıtta macOS Mikrofon ve Ekran/Sistem Sesi izinlerini verin. Eksik izinler Ayarlar (⌘,) → Kurulum durumu kartında kırmızı görünür; oradan tek tıkla istenir.
  3. Kaydı başlatıp bitirmek için her yerden ⌃⌥R.

Ekip rehberi: docs/EKIP.md
NEXT
