#!/bin/sh
# One command, the whole release (docs/BUNDLE.md, docs/ITERATION_CHECKPOINT.md ritüeli). Sürüm sahibinin Mac'i:
# Developer ID sertifikası + notarytool `meetingos` profili gerekir; `--app-only` ile başka bir Mac yalnız yerel
# uygulamayı derleyip kurar (paket, imza, yayın yok).
#
#     sh scripts/release.sh 1.2.90            # docs/releases/v1.2.90.md önceden yazılmış olmalı
#     sh scripts/release.sh 1.2.90 --app-only
set -eu
VERSION=${1:-}; MODE=${2:-}
case "$VERSION" in [0-9]*.[0-9]*.[0-9]*) ;; *) echo "kullanım: sh scripts/release.sh <sürüm> [--app-only]" >&2; exit 2;; esac
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd); cd "$REPO"
PY=.venv/bin/python
NOTE="docs/releases/v$VERSION.md"
[ -f "$NOTE" ] || { echo "önce sürüm notu: $NOTE" >&2; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = v0.1 ] || { echo "v0.1 dalında olmalı" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "çalışma ağacı temiz değil; önce commit" >&2; exit 1; }
if ps -axo command= | grep -qE "[m]eeting_os (transcribe|finalize|record)|[M]eetingCapture"; then echo "kayıt ya da iş sürüyor; bekle" >&2; exit 1; fi
if [ "$MODE" != --app-only ]; then
  security find-identity -v -p codesigning | grep -q "Developer ID Application" || { echo "Developer ID yok; bu Mac paket üretemez (--app-only)" >&2; exit 1; }
  xcrun notarytool history --keychain-profile meetingos >/dev/null 2>&1 || { echo "notarytool profili 'meetingos' yok" >&2; exit 1; }
fi
echo "==> 1/7 sürüm $VERSION"
OLD=$($PY -c "import meeting_os;print(meeting_os.__version__)")
sed -i '' "s/__version__ = '$OLD'/__version__ = '$VERSION'/" meeting_os/__init__.py
sed -i '' "s|<string>$OLD</string>|<string>$VERSION</string>|" scripts/build-desktop.sh
sed -i '' "1s/($OLD)/($VERSION)/" docs/KULLANIM.md
$PY scripts/changelog-index.py --cache build/releases.json --html build/changelog-all.html >/dev/null
echo "==> 2/7 testler"
MEETING_OS_TEST_IGNORE_PRESSURE=1 $PY -m unittest discover -s tests 2>&1 | tail -2 | grep -q "^OK" || { echo "Python testleri kırmızı; sürüm durdu" >&2; git checkout -- meeting_os/__init__.py scripts/build-desktop.sh docs/KULLANIM.md; exit 1; }
(cd desktop && swift test 2>&1 | grep -E "Executed [0-9]+ tests" | tail -1 | grep -q "with 0 failures") || { echo "Swift testleri kırmızı; sürüm durdu" >&2; exit 1; }
echo "==> 3/7 commit + uygulama"
git add -A && git commit -qm "release $VERSION" 
osascript -e 'tell application "Meeting OS" to quit' >/dev/null 2>&1 || true; sleep 2
sh scripts/build-desktop.sh >/dev/null && codesign --verify --deep --strict "build/Meeting OS.app" && open -g "build/Meeting OS.app"
echo "==> 4/7 push + etiket"
git push -q origin v0.1 && git tag "v$VERSION" && git push -q origin "v$VERSION" && git rev-parse --short HEAD > build/installed-commit
[ "$MODE" = --app-only ] && { echo "tamam (yalnız uygulama): $VERSION kuruldu ve itildi"; exit 0; }
echo "==> 5/7 paket (~10 dk)"
rm -rf build/bundle; rm -f build/Meeting-OS-*.zip build/Meeting-OS-*.zip.sha256
sh scripts/build-bundle.sh >/dev/null
echo "==> 6/7 Developer ID imza + Apple noter"
sh scripts/sign-notarize.sh "build/bundle/Meeting OS.app" | tail -3
echo "==> 7/7 yayın"
sh scripts/publish-github.sh "build/Meeting-OS-$VERSION.zip" | grep "yayında"
sh scripts/publish-bundle.sh "build/Meeting-OS-$VERSION.zip" | grep "zip:"
rm -rf build/bundle
echo "tamam: $VERSION — sürüm günlüğü artefaktı ve docs/ITERATION_CHECKPOINT.md elle güncellenir"
