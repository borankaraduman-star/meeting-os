#!/bin/sh
# Tek parça uygulama paketi: indir → Uygulamalar’a sürükle → aç (docs/BUNDLE.md).
#
# Çıktı: build/bundle/Meeting OS.app — İMZASIZ. İmza, zip ve yayınlama bu betiğin DIŞINDA:
#   .venv/bin/python scripts/signing.py --sign "build/bundle/Meeting OS.app"
#
# Paket kendi Python’unu (python-build-standalone), bulut yolunun paketlerini, statik ffmpeg’i, Sherpa
# konuşmacı modellerini ve kayıt yardımcısını taşır; kullanan Mac’te ne Homebrew ne depo ne venv gerekir.
# Hangi dosyanın girip hangisinin girmediği scripts/bundle_manifest.py içinde yazılıdır; tests/test_bundle_layout.py
# aynı listeyi denetler.
#
# Kullanım:  sh scripts/build-bundle.sh [--invite] [--output DIZIN]
#   --invite   Bu Mac’in veri klasöründen ekip davetini (yalnız ekip token’ı) Resources/invite.json
#   --invite-with-key   Aynı davet, bu Mac’in OpenRouter anahtarı da içinde (tek ortak anahtar dağıtımı)
#              olarak yazar. Bayrak yoksa dosya hiç oluşmaz.
#   --output   Paketin yazılacağı dizin (varsayılan build/bundle).
# Ortam değişkenleri: REPO, CAPTURE_APP, MODELS_DIR, DOWNLOADS, HOST_PY, VENV_PY, DATA_DIR.
#
# -f: dosya adı genişletmesi kapalı. Dışlama kalıpları (*.pyc) kabuktan rsync’e bozulmadan geçmeli.
set -euf

self=$(cd "$(dirname "$0")" && pwd)
REPO=${REPO:-}
if [ -z "$REPO" ]; then REPO=$(cd "$self/.." && pwd); fi
manifest="$self/bundle_manifest.py"

invite=0
invite_key=0
output=

while [ $# -gt 0 ]; do
    case "$1" in
        --invite) invite=1 ;;
        --invite-with-key) invite=1; invite_key=1 ;;
        --output) shift; output=${1:-} ;;
        --output=*) output=${1#--output=} ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) printf 'bilinmeyen secenek: %s\n' "$1" >&2; exit 2 ;;
    esac
    shift
done

OUTPUT=${output:-}
if [ -z "$OUTPUT" ]; then OUTPUT="$REPO/build/bundle"; fi
DOWNLOADS=${DOWNLOADS:-"$REPO/build/downloads"}
CAPTURE_APP=${CAPTURE_APP:-"$REPO/build/MeetingCapture.app"}
MODELS_DIR=${MODELS_DIR:-"$REPO/models"}
HOST_PY=${HOST_PY:-/usr/bin/python3}
VENV_PY=${VENV_PY:-"$REPO/.venv/bin/python"}
DATA_DIR=${DATA_DIR:-"$HOME/Library/Application Support/MeetingOS"}

say() { printf '==> %s\n' "$*"; }
die() { printf 'HATA: %s\n' "$*" >&2; exit 1; }
ask() { "$HOST_PY" "$manifest" "$@"; }

[ -x "$HOST_PY" ] || die "Python yok: $HOST_PY (HOST_PY ile gosterin)"
[ -d "$CAPTURE_APP" ] || die "Kayit yardimcisi yok: $CAPTURE_APP (once sh scripts/build-capture.sh, ya da CAPTURE_APP ile gosterin)"
[ -d "$MODELS_DIR/sherpa" ] || die "Sherpa modelleri yok: $MODELS_DIR/sherpa (MODELS_DIR ile gosterin)"
command -v swift >/dev/null 2>&1 || die "swift yok; Xcode komut satiri araclari gerekli"

VERSION=$(ask version "$REPO")
say "Meeting OS $VERSION · paket: $OUTPUT"

# --------------------------------------------------------------- 1. Swift uygulaması
say "Swift uygulamasi derleniyor (release)"
swift build --package-path "$REPO/desktop" -c release --jobs 1

# --------------------------------------------------------------- 2. iskelet
app="$OUTPUT/Meeting OS.app"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources" "$DOWNLOADS"
cp "$REPO/desktop/.build/release/MeetingOS" "$app/Contents/MacOS/MeetingOS"
cp "$REPO/desktop/Icon/AppIcon.icns" "$app/Contents/Resources/AppIcon.icns"
resources="$app/Contents/Resources"

# build-desktop.sh’nin plist’i, tek farkla: CFBundleShortVersionString paket sürümüdür.
cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.boran.meeting-os</string>
<key>CFBundleName</key><string>Meeting OS</string>
<key>CFBundleExecutable</key><string>MeetingOS</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>${VERSION}</string>
<key>LSMinimumSystemVersion</key><string>15.0</string>
<key>NSMicrophoneUsageDescription</key><string>Meeting OS toplantı mikrofonunu yalnızca bu Mac üzerinde kaydeder ve yazıya dönüştürür.</string>
<key>NSScreenCaptureUsageDescription</key><string>Meeting OS toplantı sistem sesini yerel olarak kaydeder. Ekran görüntüsü saklanmaz.</string>
<key>NSCalendarsFullAccessUsageDescription</key><string>Meeting OS kayıt başlarken o andaki takvim etkinliğinin adını ve katılımcılarını okur; takvime hiçbir şey yazmaz.</string>
<key>NSCalendarsUsageDescription</key><string>Meeting OS kayıt başlarken o andaki takvim etkinliğinin adını ve katılımcılarını okur; takvime hiçbir şey yazmaz.</string>
<key>NSRemindersFullAccessUsageDescription</key><string>Meeting OS seçtiğiniz görevi Apple Hatırlatıcılar’a ekler; başka hiçbir şey okumaz veya değiştirmez.</string>
<key>NSRemindersUsageDescription</key><string>Meeting OS seçtiğiniz görevi Apple Hatırlatıcılar’a ekler; başka hiçbir şey okumaz veya değiştirmez.</string>
<key>NSHighResolutionCapable</key><true/>
<key>CFBundleURLTypes</key><array><dict>
<key>CFBundleURLName</key><string>Meeting OS</string>
<key>CFBundleTypeRole</key><string>Viewer</string>
<key>CFBundleURLSchemes</key><array><string>meetingos</string></array>
</dict></array>
<key>CFBundleDocumentTypes</key><array><dict>
<key>CFBundleTypeName</key><string>Meeting OS daveti</string>
<key>CFBundleTypeRole</key><string>Viewer</string>
<key>LSHandlerRank</key><string>Owner</string>
<key>LSItemContentTypes</key><array><string>local.boran.meeting-os.invite</string></array>
</dict></array>
<key>UTExportedTypeDeclarations</key><array><dict>
<key>UTTypeIdentifier</key><string>local.boran.meeting-os.invite</string>
<key>UTTypeDescription</key><string>Meeting OS daveti</string>
<key>UTTypeConformsTo</key><array><string>public.json</string></array>
<key>UTTypeTagSpecification</key><dict>
<key>public.filename-extension</key><array><string>meetingos-invite</string></array>
</dict>
</dict></array>
</dict></plist>
PLIST

# --------------------------------------------------------------- 3. runtime: python-build-standalone
asset=$(ask python-asset)
url=$(ask python-url)
sums_url=$(ask python-sums-url)
toplevel=$(ask python-toplevel)
tarball="$DOWNLOADS/$asset"
shafile="$DOWNLOADS/$asset.sha256"

if [ ! -f "$tarball" ]; then
    say "Python indiriliyor: $asset"
    curl -fL --retry 3 --retry-delay 2 -o "$tarball.part" "$url" || die "indirilemedi: $url"
    mv "$tarball.part" "$tarball"
else
    say "Python onbellekten: $tarball"
fi

actual=$(shasum -a 256 "$tarball" | awk '{print $1}')
expected=
if curl -fsSL --retry 2 -o "$DOWNLOADS/SHA256SUMS.$PPID" "$sums_url" 2>/dev/null; then
    expected=$(awk -v want="$asset" '$2==want {print $1}' "$DOWNLOADS/SHA256SUMS.$PPID")
    rm -f "$DOWNLOADS/SHA256SUMS.$PPID"
fi
if [ -z "$expected" ] && [ -f "$shafile" ]; then expected=$(cat "$shafile"); fi
if [ -n "$expected" ] && [ "$expected" != "$actual" ]; then
    rm -f "$tarball"
    die "sha256 uyusmadi (beklenen $expected, gelen $actual); indirme silindi, betigi tekrar calistirin"
fi
printf '%s\n' "$actual" > "$shafile"
say "sha256 dogrulandi: $actual"

runtime="$resources/runtime"
stage="$OUTPUT/.runtime-stage"
rm -rf "$stage"; mkdir -p "$stage"
tar -xzf "$tarball" -C "$stage"
[ -d "$stage/$toplevel" ] || die "arsiv icinde $toplevel/ yok"
mv "$stage/$toplevel" "$runtime"
rm -rf "$stage"
py="$runtime/bin/python3"
[ -x "$py" ] || die "runtime python yok: $py"

# --------------------------------------------------------------- 4. paketler
constraints="$REPO/$(ask constraints-file)"
[ -f "$constraints" ] || die "pin dosyasi yok: $constraints"
say "Paketler kuruluyor (olculmus pinler: $(basename "$constraints"))"
ask packages > "$OUTPUT/.packages.txt"
ask no-deps-packages > "$OUTPUT/.packages-nodeps.txt"
"$py" -m pip install --no-cache-dir --disable-pip-version-check --constraint "$constraints" -r "$OUTPUT/.packages.txt"
"$py" -m pip install --no-cache-dir --disable-pip-version-check --no-deps -r "$OUTPUT/.packages-nodeps.txt"
rm -f "$OUTPUT/.packages.txt" "$OUTPUT/.packages-nodeps.txt"

# imageio-ffmpeg’in taşıdığı statik ffmpeg ikilisi runtime/bin/ffmpeg olur: PATH’in başına runtime/bin
# konduğu için (App.swift Runtime.childEnvironment) shutil.which('ffmpeg') paketin kendi ffmpeg’ini bulur.
say "ffmpeg cikariliyor"
ffsrc=$("$py" - <<'PY'
import glob, os, sys
import imageio_ffmpeg
root = os.path.join(os.path.dirname(imageio_ffmpeg.__file__), 'binaries')
found = [p for p in sorted(glob.glob(os.path.join(root, 'ffmpeg*'))) if os.path.isfile(p)]
if not found:
    sys.exit('imageio_ffmpeg/binaries icinde ffmpeg yok')
print(found[-1])
PY
)
cp "$ffsrc" "$runtime/bin/ffmpeg"
chmod 755 "$runtime/bin/ffmpeg"
"$runtime/bin/ffmpeg" -version >/dev/null 2>&1 || die "paketlenen ffmpeg calismadi: $runtime/bin/ffmpeg"

# --------------------------------------------------------------- 5. budama
say "Gereksizler siliniyor"
"$py" -m pip cache purge >/dev/null 2>&1 || true
pruned=$(ask prune "$runtime")
say "budandi: $(printf '%s' "$pruned" | awk '{print $1}') yol, $(printf '%s' "$pruned" | awk '{printf "%.0f", $2/1048576}') MB"

# --------------------------------------------------------------- 6. repo/
repo="$resources/repo"
rm -rf "$repo"; mkdir -p "$repo"
excludes=
for pattern in $(ask repo-exclude); do excludes="$excludes --exclude=$pattern"; done
# shellcheck disable=SC2086
for tree in $(ask repo-trees); do
    [ -d "$REPO/$tree" ] || die "depoda yok: $tree"
    rsync -a $excludes "$REPO/$tree" "$repo/"
done
for file in $(ask repo-files); do
    [ -f "$REPO/$file" ] || die "depoda yok: $file"
    mkdir -p "$repo/$(dirname "$file")"
    cp "$REPO/$file" "$repo/$file"
done
for script in $(ask repo-scripts); do
    mkdir -p "$repo/scripts"
    cp "$REPO/scripts/$script" "$repo/scripts/$script"
done

sherpa_dest="$repo/$(ask sherpa-dest)"
mkdir -p "$sherpa_dest"
for file in $(ask sherpa-files); do
    [ -f "$MODELS_DIR/sherpa/$file" ] || die "model dosyasi yok: $MODELS_DIR/sherpa/$file"
    mkdir -p "$sherpa_dest/$(dirname "$file")"
    cp "$MODELS_DIR/sherpa/$file" "$sherpa_dest/$file"
done

capture_dest="$repo/$(ask capture-dest)"
mkdir -p "$(dirname "$capture_dest")"
# shellcheck disable=SC2086
rsync -a $excludes "$CAPTURE_APP/" "$capture_dest/"
[ -x "$capture_dest/Contents/MacOS/MeetingCapture" ] || die "kayit yardimcisi kopyalanmadi"

# --------------------------------------------------------------- 7. runtime.json
ask runtime-json "$VERSION" > "$resources/runtime.json"

# --------------------------------------------------------------- 8. --invite
if [ "$invite" -eq 1 ]; then
    [ -x "$VENV_PY" ] || die "davet icin depo venv gerekli: $VENV_PY"
    if [ "$invite_key" -eq 1 ]; then say "Ekip daveti yaziliyor (token + OpenRouter anahtari)"; else say "Ekip daveti yaziliyor (yalniz token; anahtar kisiye ozel baglantiyla gelir)"; fi
    REPO_DIR="$REPO" INVITE_KEY="$invite_key" "$VENV_PY" - "$resources/invite.json" "$DATA_DIR" <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, os.environ['REPO_DIR'])
from meeting_os.team_cloud import invite_file_text
text = invite_file_text(Path(sys.argv[2]), include_key=os.environ.get('INVITE_KEY') == '1')
if not text.strip():
    sys.exit('Bu Mac’te ekip belirteci yok; davet yazılamadı')
Path(sys.argv[1]).write_text(text, encoding='utf-8')
PY
else
    rm -f "$resources/invite.json"
fi

xattr -cr "$app" 2>/dev/null || true

# --------------------------------------------------------------- 9. doğrulama
# PYTHONDONTWRITEBYTECODE: doğrulama importları paketin içine __pycache__ yazıp az önce budanan
# dosyaları geri getirmesin — imzalanacak paket, derlenen paketin aynısı olmalı.
say "Dogrulama"
export PYTHONDONTWRITEBYTECODE=1
"$py" -c "import resemblyzer, silero_vad, sherpa_onnx, torch, numpy, scipy, soundfile; print('import OK')"
# PATH tam da uygulamanın çocuklarına verdiği gibi kurulur (App.swift Runtime.childEnvironment), yoksa
# doctor bu Mac’in Homebrew ffmpeg’ini bulur ve paketin kendi ffmpeg’i hiç denenmemiş olur.
( cd "$repo" && PATH="$runtime/bin:$PATH" ../runtime/bin/python3 -m meeting_os doctor ) || die "doctor cokti"
"$runtime/bin/ffmpeg" -version | head -1
du -sh "$app"
budget=$(ask size-budget)
bytes=$(du -sk "$app" | awk '{print $1*1024}')
if [ "$bytes" -gt "$budget" ]; then
    printf 'UYARI: paket hedefin uzerinde (%s bayt > %s bayt)\n' "$bytes" "$budget" >&2
fi
say "imzasiz paket hazir: $app"
printf '%s\n' "$app"
