#!/bin/sh
# "Göze batmama" kanıtı — Codex P0 #7.
#
# İddia: göze batma açıkken ve toplantı ekrandayken Meeting OS pencereleri paylaşılan görüntüde görünmez.
# İddianın tamamı tek satıra dayanıyor: NSWindow.sharingType = .none (DiscreetMode.windowSharingType).
# Bu betik o satırı bu Mac'te kanıtlar:
#
#   1. Ekran kilidi ve uygulama çalışıyor mu, göze batma açık mı — kontrol eder.
#   2. `privacyProbe` tercihini yazar: uygulama bunu "toplantı ekranda" gibi okur (App.applyWindowPrivacy).
#   3. Pencereyi öne alır ve çerçevesini pencere listesinden okur (Erişilebilirlik izni gerekmez).
#   4. Bayrak KAPALIYKEN ve AÇIKKEN birer `screencapture -x` alır.
#   5. Pencerenin dikdörtgeni içindeki piksellerin değiştiğini, dışındakilerin değişmediğini ölçer.
#
# GEÇTİ = dikdörtgenin içi iki görüntüde farklı (yani AÇIK görüntüde uygulama içeriği yok) ve dışı aynı.
# Hiçbir yere tıklamaz, kayıt başlatmaz, transkript okumaz. Görüntüler geçici klasörde kalır ve silinir.
#
# Bu betiğin kanıtladığı şey bu Mac'in kendi ekran görüntüsüdür. GERÇEK kabul ölçütü hâlâ açık:
# ikinci bir Mac'ten Zoom ekran paylaşımını izleyen kişinin gördüğü görüntü (docs/BUNDLE.md → Göze batmama).
set -eu
cd "$(dirname "$0")/.."

bundle="${MEETING_OS_BUNDLE_ID:-local.boran.meeting-os}"
say() { printf '%s\n' "$*"; }
field() { printf '%s' "$1" | sed -n "s/.*\"$2\":\([^,}]*\).*/\1/p" | tr -d '"'; }

# 1 ── ön koşullar ───────────────────────────────────────────────────────────
if ioreg -n Root -d1 2>/dev/null | grep -qE '"CGSSessionScreenIsLocked"[[:space:]]*=[[:space:]]*Yes'; then
  say "ATLANDI: ekran kilitli. Kilidi açıp tekrar çalıştırın (ekran görüntüsü alınamaz)."
  exit 2
fi
if ! pgrep -x MeetingOS >/dev/null 2>&1; then
  say "ATLANDI: Meeting OS çalışmıyor. Uygulamayı açıp bir toplantı ekranda dururken tekrar çalıştırın."
  exit 2
fi
discreet=$(defaults read "$bundle" discreetMode 2>/dev/null || echo 1)   # anahtar yoksa varsayılan: açık
if [ "$discreet" = "0" ]; then
  say "ATLANDI: göze batma kapalı (Ayarlar → Sistem). Kanıt bu ayar açıkken anlamlı."
  exit 2
fi

tmp=$(mktemp -d "${TMPDIR:-/tmp}/meetingos-privacy.XXXXXX")
cleanup() { rc=$?; defaults delete "$bundle" privacyProbe >/dev/null 2>&1 || true; rm -rf "$tmp"; exit "$rc"; }
trap cleanup EXIT INT TERM

# 2 ── pencere çerçevesi ─────────────────────────────────────────────────────
rect=$(swift scripts/privacy-probe.swift rect "$bundle") || { say "HATA: $rect"; exit 1; }
case "$rect" in *'"error"'*) say "ATLANDI: $(field "$rect" error)"; exit 2;; esac
x=$(field "$rect" x); y=$(field "$rect" y); w=$(field "$rect" w); h=$(field "$rect" h)
dw=$(field "$rect" display_w); dh=$(field "$rect" display_h)
if [ "$(field "$rect" on_main_display)" != "true" ]; then
  say 'ATLANDI: pencere ana ekranda değil. screencapture -x ana ekranı alır; pencereyi ana ekrana taşıyın.'
  exit 2
fi
covered=$(printf '%s' "$rect" | sed -n 's/.*"covered_by":\[\([^]]*\)\].*/\1/p')
if [ -n "$covered" ]; then
  say "ATLANDI: pencerenin önünde başka pencere var ($covered). Meeting OS penceresini önde bırakın."
  exit 2
fi
say "Pencere: ${w}x${h} @ (${x},${y}) · ana ekran ${dw}x${dh}"

# 3 ── iki ekran görüntüsü ───────────────────────────────────────────────────
# Uygulama bayrağı iki saniyelik yoklamada okur; dört saniye bir turu garanti eder.
defaults write "$bundle" privacyProbe -bool false
sleep 4
screencapture -x "$tmp/off.png"
defaults write "$bundle" privacyProbe -bool true
sleep 4
screencapture -x "$tmp/on.png"
defaults delete "$bundle" privacyProbe >/dev/null 2>&1 || true

# 4 ── karşılaştırma ─────────────────────────────────────────────────────────
stats=$(swift scripts/privacy-probe.swift compare "$tmp/off.png" "$tmp/on.png" "$x" "$y" "$w" "$h" "$dw" "$dh") || { say "HATA: $stats"; exit 1; }
case "$stats" in *'"error"'*) say "HATA: $(field "$stats" error)"; exit 1;; esac
inside=$(field "$stats" inside_changed); outside=$(field "$stats" outside_changed)
imean=$(field "$stats" inside_mean); omean=$(field "$stats" outside_mean)
say "Ölçüm: $stats"
say "Dikdörtgen içinde değişen piksel: $inside (ortalama fark $imean) · dışında: $outside (ortalama fark $omean)"

verdict=$(awk -v i="$inside" -v o="$outside" -v m="$imean" 'BEGIN { print (i>=0.20 && m>=3 && o<=0.02) ? "PASS" : "FAIL" }')
if [ "$verdict" = "PASS" ]; then
  say "GEÇTİ: bayrak açıkken pencerenin dikdörtgeninde uygulama içeriği yok; ekranın geri kalanı değişmedi."
  say "Not: gerçek kabul ölçütü hâlâ ikinci bir Mac'ten izlenen Zoom paylaşımıdır."
  exit 0
fi
say "KALDI: pencere dikdörtgeni iki görüntüde yeterince farklı değil ya da ekranın geri kalanı da değişti."
say "Olası nedenler: terminale Ekran Kaydı izni verilmemiş (iki görüntü de uygulamayı göstermez),"
say "ekranda hareketli bir şey var (video, saat, animasyon) ya da .none gerçekten uygulanmıyor."
exit 1
