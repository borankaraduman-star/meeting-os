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

Uygulama kendini günceller: yeni zip'i indirir, sha256 ile doğrular, açar ve kendi yerine koyar. Git yolu
(geliştirici Mac'i, `scripts/update.sh`) olduğu gibi durur; kanalı `meeting_os/updater.py` **tek başına**
`ROOT`'a bakarak seçer — `ROOT`'un adı `repo` ve bir üstünde `bundled: true` yazan `runtime.json` varsa paket
kanalı, yoksa git kanalı. Köprü eylemleri aynı: `update_check`, `update_start`, `update_status`.

### Sunucu: `GET|HEAD /dl/<secret>/<dosya>` (ve `/meetingos/dl/…`)

`server/sync_server.py` içinde, ekip eşitlemesiyle aynı portta ama ondan tamamen ayrı: `<root>/_downloads/`
altındaki statik dosyaları verir, **kimlik başlığı yoktur** (1,3 GB'lık zip tarayıcıdan da `curl`'den de
inebilmeli), yani **gizli yolun kendisi paroladır**. Bu yüzden yol asla günlüğe yazılmaz (`/dl/<secret>/…`
diye maskelenir).

- Seçenekler: `--downloads` (varsayılan `<root>/_downloads`), `--download-secret-file` (varsayılan
  **`/etc/meetingos-sync/download.secret`**, 32–128 hex). Dosya yoksa veya bozuksa route **her şeye 404**
  verir; `deploy.sh` dosyayı `openssl rand -hex 32` ile bir kez üretir, sahibi `root:meetingos`, izni `0640`
  (servis kullanıcısı yalnız okur). Değer hiçbir zaman ekrana basılmaz, yalnız "var/yok" yazılır. Secret her
  istekte dosyadan okunur: döndürmek için servisi yeniden başlatmak gerekmez.
- Karşılaştırma sabit zamanlı (`hmac.compare_digest`). Dosya adı `^[A-Za-z0-9._-]{1,120}$` ve nokta ile
  başlayamaz; sınıfta `/` yok, yani `_downloads` dışına çıkılamaz. Yanlış secret, eksik secret dosyası, kötü
  ad ve olmayan dosya **aynı 404**'ü verir (hangisi olduğu sızmasın).
- `Range: bytes=s-` ve `bytes=s-e` → `206` + `Content-Range` (yarıda kalan indirme sürsün), her yanıtta
  `Accept-Ranges: bytes`; aşan aralık `416`, bozuk başlık yok sayılır. `Content-Type` uzantıdan
  (`.zip` → `application/zip`, `.json` → `application/json`). `ETag` = yanındaki `<dosya>.sha256` varsa onun
  özeti, yoksa `mtime-size`; `If-None-Match` → `304`. Dosya parça parça (256 KB) akıtılır, belleğe alınmaz.
- `_downloads` bir **ekip değildir**: ekip dizinleri `sha256(token)[:32]` adlıdır, `_downloads` hiçbir
  `/index` yanıtında görünmez ve o yoldan hiçbir şey yazılamaz (GET/HEAD dışı → 405). `server/backup.sh`
  günlük yedeğin dışında tutar (yoksa 14 günlük yedek = ~18 GB).

### Yayınlama: `sh scripts/publish-bundle.sh build/Meeting-OS-<sürüm>.zip`

Sürümü dosya adından okur (`Meeting-OS-<sürüm>.zip`), `<zip>.sha256` yanında olmalıdır (yoksa hesaplar,
varsa zip ile **eşleştiğini doğrular**), zip'i ve sha dosyasını `root@100.87.35.111:/var/lib/meetingos-sync/_downloads/`
altına `scp`'ler, iki tarafta `wc -c` ile boyutu karşılaştırır, `chown meetingos`, en son `latest.json` yazar
(sıra önemli: latest.json var olmayan bir dosyayı asla göstermez), sonra secret'i ssh ile okuyup **iki
bağlantıyı** basar:

    https://hermes-vps.tail2d8c7e.ts.net/meetingos/dl/<secret>/Meeting-OS-<sürüm>.zip
    https://hermes-vps.tail2d8c7e.ts.net/meetingos/dl/<secret>/latest.json

`latest.json`: `{"version":"1.2.72","file":"Meeting-OS-1.2.72.zip","sha256":"…","size":n,
"published":"<utc>","notes":"docs/releases/v1.2.72.md ilk satırı (baştaki '# ' olmadan)"}`.

### İstemci: `meeting_os/updater.py`

**Secret pakette nerede:** önce `Contents/Resources/download.secret` (yalnız secret'in kendisi; `build-bundle.sh`
bunu yazmaz, imzalarken Boran koyar — böylece secret build betiğinin çıktısında hiç bulunmaz), yoksa
`runtime.json` içindeki `download_secret` anahtarı. İkisi de yoksa kart "Güncelleme adresi bu pakette yok"
der ve hiçbir yere bağlanmaz. `BUNDLE_BASE_URL` = `https://hermes-vps.tail2d8c7e.ts.net/meetingos/dl/<secret>`;
`runtime.json`'daki `download_base` anahtarı tüm adresi ezer (taşınan sunucu ve testler).

- `check` → `latest.json` (5 sn, urllib, `User-Agent: MeetingOS-updater/1`), sürümü `vkey` ile sayısal
  karşılaştırır (`1.2.10 > 1.2.9`). Yanıt git yolununkiyle **aynı sözlük**: `available`, `behind` (yeni varsa
  1), `remote`/`target` = sürüm dizgesi, `subjects` = `[notes]`, hata olursa `error`. Okunamayan yerel sürüm
  "eski" sayılır: bir daha hiç güncellenemeyen Mac'ten iyidir.
- `start` → ayrı oturumda (`start_new_session=True`) bağımsız bir işçi başlatır:
  `python -m meeting_os.updater --bundle-download --base … --app <çalışan .app> --pid <uygulamanın pid'i>`.
  `app_path`/`pid` Swift'ten gelir; gelmezse paketin kendi yolu ve `os.getppid()` (köprünün ebeveyni zaten
  uygulamadır) kullanılır.
- İşçi: zip'i `~/Library/Caches/MeetingOS/update/<dosya>` altına **kaldığı yerden** indirir (`Range`), her
  yüzde değişiminde `update-status.json`'a yazar (`state: downloading`, `percent`), sha256 doğrular
  (`verifying`), `ditto -x -k` ile geçici klasöre açar (`extracting`), `swap-update.sh`'yi bağımsız başlatıp
  `swapping` yazar. Her hata `state: failed` + `error`. Yarım zip **durur** (sonraki koşu Range ile sürdürür),
  sha256 **tutmayan** zip silinir (yoksa her denemeyi zehirler).
- `update-status.json` sözleşmesi `scripts/update.sh` ile aynıdır (`state`,`from`,`to`,`message`,`time`); tek
  eklenen anahtar `percent`. Böylece uygulamanın mevcut yoklaması değişmeden çalışır.

### Takas: `scripts/swap-update.sh <yeni.app> <hedef.app> <pid>`

Depoda `scripts/` altındadır; `updater.py` önce `runtime.json`'ın yanına (`Contents/Resources/swap-update.sh`)
bakar, yoksa `scripts/` altındakini kullanır — `build-bundle.sh` `scripts/`'i zaten kopyaladığı için ikisi de
aynı dosyadır. Sudo **yoktur**: hedef, uygulamanın o an çalıştığı yoldur (Swift gönderir), klasör yazılabilir
değilse takas reddedilir ve kurulu sürüm yerinde kalır. pid bitene kadar ≤60 sn bekler, `hedef` →
`hedef.previous` (eski `.previous` silinir), `yeni` → `hedef`, karantina özniteliği temizlenir, `open`. Takas
başarısızsa `.previous` geri gelir. Günlük: `~/Library/Application Support/MeetingOS/update.log` (uygulamanın
gösterdiği günlük), durum aynı `update-status.json`.

### Swift (`Updater.swift`)

`BundleInfo` `Contents/Resources/runtime.json`'ı kendi okur (`bundled`), `update_start` isteğine paket
kanalında `app_path` (= `Bundle.main.bundleURL.path`) ve `pid` ekler; `UpdateStatusLine` yeni durumları tek
cümleye çevirir (`downloading` → "Yeni sürüm indiriliyor · %42", `verifying`, `extracting`, `swapping`) ve
`shouldQuit(state:)` `swapping` için doğrudur — takas betiği pid'in bitmesini beklediği için uygulama kendini
kapatmalıdır. Kenar çubuğu düğmesinin adı değişmez ("Güncelle ve yeniden başlat"), kayıt sürerken erteleme
kuralı da aynıdır.

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
