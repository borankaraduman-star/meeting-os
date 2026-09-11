# Tek parça uygulama paketi (bundle): indir → Uygulamalar'a sürükle → aç

Tarih: 2026-09-11 03:40. Boran: "kullanacak insanlar terminal yazamaz; en basit insanın kullanabileceği hale getir" ve
"bugün arkadaşlara ileteceğim, nasıl indirip kuracaklar, guide hazırla".

Bugünkü kurulum (`git clone` + `install.sh`: Homebrew, Xcode araçları, sertifika, pip, swift build) bir geliştirici
kurulumudur. Ekip arkadaşı için tek kabul edilebilir yol: **bir zip indir, `Meeting OS.app`'i Uygulamalar'a sürükle, aç.**
Bunun için uygulama Python'unu, paketlerini, ses modelini, ffmpeg'i, kayıt yardımcısını ve ekip davetini kendi içinde
taşır. Güncelleme de aynı yoldan: yeni zip'i indirir, doğrular, kendini değiştirir.

## Paket düzeni

    Meeting OS.app/Contents/
      MacOS/MeetingOS                      SwiftUI uygulaması (bugünkü build-desktop.sh çıktısı)
      Resources/AppIcon.icns
      Resources/runtime.json               {"python":"runtime/bin/python3","repo":"repo","bundled":true,"version":"1.2.72"}
      Resources/runtime/                   python-build-standalone cpython-3.12 (aarch64-apple-darwin, install_only)
                                           + pip ile kurulmuş paketler (aşağıda) + bin/ffmpeg (statik)
      Resources/repo/                      meeting_os/ paketi, vocabulary.txt, docs/KULLANIM.md, docs/MODEL_LOCK.json,
                                           models/sherpa/ (yalnız bulut yolunun kullandığı dosyalar),
                                           build/MeetingCapture.app (kayıt yardımcısı), scripts/ (yalnız çalışma anında
                                           gerekenler; install/update/build betikleri DEĞİL)
      Resources/invite.json                team_cloud.invite_file_text(include_key=True) çıktısı — ekip token'ı +
                                           OpenRouter anahtarı; ilk açılışta içe alınır (aşağıda)
      Resources/swap-update.sh             güncelleme takas betiği (aşağıda)
      Info.plist                           build-desktop.sh'nin ürettiği; CFBundleShortVersionString paket sürümü

`runtime.json` yolları `/` ile başlamıyorsa `Bundle.main.resourceURL`'e göre çözülür (App.swift `Runtime`). `bundled:true`
iken: güncelleme git değil paket kanalı (aşağıda); "kaynak deposu" satırları kurulum kartında görünmez; `ROOT`
(`meeting_os/cli.py`, `Path(__file__).resolve().parents[1]`) zaten `Resources/repo` olur.

İşler `runtime/bin/python3 -m meeting_os …` ile koşar; `PATH` başına `runtime/bin` eklenir ki `shutil.which('ffmpeg')`
paketteki ffmpeg'i bulsun (Swift `jobEnvironment` + bridge `Process.environment`).

## Paket kurma: `scripts/build-bundle.sh [--invite] [--output build/bundle]`

1. `scripts/build-desktop.sh` çıktısını (imzasız kopya için `build/desktop-stage` mantığı) temel al.
2. `runtime/`: `cpython-3.12.<x>+<tarih>-aarch64-apple-darwin-install_only.tar.gz` (astral-sh/python-build-standalone;
   `build/downloads/` altında önbellek; sha256 kontrol), `runtime/bin/python3 -m pip install` ile:
   `requirements-macos-tested.txt` içinden bulut yolunun gerektirdiği alt küme (numpy, scipy, soundfile,
   huggingface-hub, resemblyzer + torch, silero-vad, sherpa-onnx, librosa/numba/llvmlite, scikit-learn, webrtcvad,
   setuptools) + `imageio-ffmpeg` (statik ffmpeg ikilisi → `runtime/bin/ffmpeg` kopyası). mlx, mlx-lm, mlx-whisper,
   outlines, transformers, pyarrow, torchaudio PAKETE GİRMEZ (yerel model dönemi). `pip cache purge`, `__pycache__`,
   `*/tests/`, `*.dist-info/RECORD` dışı gereksizler silinir; hedef ≤ 1,3 GB.
3. `repo/`: yukarıdaki dosyalar `rsync` ile; `.git`, `build/*` (MeetingCapture.app hariç), `models/*` (sherpa hariç),
   `tests/`, `desktop/` girmez.
4. `--invite`: gerçek veri klasöründen `team_cloud.invite_file_text(REAL_DATA_DIR, include_key=True)` → `invite.json`.
5. Doğrulama (betik içinde, imzasız kopyada): `runtime/bin/python3 -m meeting_os doctor`, `runtime/bin/python3 -c
   "import resemblyzer, silero_vad, sherpa_onnx, torch"`, `runtime/bin/ffmpeg -version`, paket boyutu yazdırılır.
6. İmza ve zip betiğin DIŞINDA (Boran'ın Mac'i): `scripts/signing.py --sign "build/bundle/Meeting OS.app"` →
   `ditto -c -k --keepParent` → `build/Meeting-OS-<sürüm>.zip` + sha256. (`codesign --deep` Resources altındaki Mach-O
   dosyaları da imzalar; hardened runtime yok, kendinden imzalı sertifika.)

## İlk açılış (Swift)

`bundled` ise ve `setup_status` ne `openrouter.key` ne `team.token` görüyorsa, `Resources/invite.json` okunur ve
`team_join` köprü eylemine verilir (davet dosyasıyla aynı yol: `team.token` + yoksa `openrouter.key` yazılır, eşitleme
başlar). Karşılama ekranı yalnız **adı** sorar (mikrofon etiketi) ve izin düğmelerini gösterir (mikrofon, ekran kaydı =
sistem sesi, bildirim). Davet zaten alınmışsa hiçbir şey sormaz.

## Güncelleme (paket kanalı)

- Sunucu (`server/sync_server.py`): `GET /dl/<secret>/<dosya>` — `/var/lib/meetingos-sync/_downloads/` altından statik
  dosya (zip ve `latest.json`), `secret` = `/etc/meetingos-sync/download.secret` (32+ hex; `deploy.sh` yoksa üretir).
  Tarayıcıdan da çalışır (kimlik başlığı yok; gizli yol yeter). `HEAD` ve `Range` desteklenir (1,3 GB indirme
  kaldığı yerden sürsün). Yanlış secret 404. `latest.json`: `{"version":"1.2.72","file":"Meeting-OS-1.2.72.zip",
  "sha256":"…","size":n,"published":"<utc>","notes":"docs/releases/v1.2.72.md ilk satırı"}`.
- Yayınlama: `scripts/publish-bundle.sh build/Meeting-OS-<sürüm>.zip` → scp `_downloads/`'a, `wc -c` doğrulama,
  `latest.json` yazar, indirme bağlantısını basar: `https://hermes-vps.tail2d8c7e.ts.net/meetingos/dl/<secret>/Meeting-OS-<sürüm>.zip`.
- İstemci (`meeting_os/updater.py`): `bundled` ise `check` → `latest.json` (5 sn), sürüm karşılaştırma (`vkey`),
  `{'available':bool,'version','size','notes'}`; `start` → zip'i `~/Library/Caches/MeetingOS/update/` altına indirir
  (ilerleme dosyası `update-status.json`: `downloading` yüzde), sha256 doğrular, `ditto -x -k` ile açar, sonra
  `swap-update.sh <yeni.app> <hedef.app> <pid>` betiğini `nohup`/`setsid` ile bağımsız başlatır ve uygulamaya çıkmasını
  söyler. Betik: pid bitene kadar bekler (≤60 sn), hedefi `<hedef>.previous` olarak yana alır, yeniyi yerine koyar,
  `open` ile açar, `.previous`'ı 7 gün sonra siler (bir sonraki güncelleme siler). Takas başarısızsa `.previous` geri
  gelir. Uygulama kendisi indirdiği için karantina yok (`LSFileQuarantineEnabled` yok).
- Swift (`Updater.swift`): `bundled` iken kenar çubuğu düğmesi aynı ("Güncelle ve yeniden başlat"), ama git yolu yerine
  paket kanalını çağırır; ilerleme yüzdesi gösterir; kayıt sürerken ertelenir (mevcut kural).

## Gatekeeper (tek seferlik, iki tık)

Zip tarayıcıyla indiği için karantinalıdır; kendinden imzalı sertifika Apple tarafından doğrulanamaz. İlk açılışta
macOS "Apple bu uygulamayı doğrulayamadı" der: **Sistem Ayarları → Gizlilik ve Güvenlik → en altta "Yine de Aç"**.
Bir kez. Güncellemeler uygulamanın kendi indirmesi olduğu için bir daha sorulmaz. Apple Developer ID (yıllık 99 $) alınırsa
paket notarize edilir ve bu adım tamamen kalkar; Boran'ın kararı.

## Doğrulama

- Paket bu Mac'te: `build/bundle/Meeting OS.app` doğrudan açılır (repo/venv yokmuş gibi: `MEETING_OS_TEST_BUNDLE=1`
  ile `runtime.json` göreli yollar), kurulum kartı yeşil, kısa bir kayıt → transkript → özet.
- İkinci Mac (Boran'ın): zip indir → Uygulamalar → Yine de Aç → ad → kayıt.
- Testler: `tests/test_bundle_layout.py` (runtime.json göreli çözüm, rsync dışlama listesi, invite içe alma),
  `tests/test_updater_bundle.py` (latest.json, sha, sürüm kıyası, takas betiği kuru koşu), `tests/test_sync_server.py`
  (+ `/dl/` route, Range, 404), Swift `RuntimeTests` (göreli yol), `UpdaterTests` (bundled dal).
