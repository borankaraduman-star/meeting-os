# Meeting OS — Boran’ın yerel toplantı hafızası

Mac uygulaması ve CLI: ayrı mikrofon/sistem sesi, canlı Türkçe transkript,
toplantı sonunda nihai metin, konuşmacı ayrımı ve kalıcı ses
profilleri. Yerel özet, karar, risk, açık soru ve görev çıkarımı; Boran’ın görev
kuyruğu; kaynaklı arşiv araması ve görev taslakları. Varsayılan işleme bu Mac’te
yapılır; ücretli inference API’si veya otomatik dış servis aksiyonu yoktur.

## Bu Mac’te aç

**`Meeting OS.command` dosyasını çift tıklayın.** Uygulama henüz yoksa ilk kurulumu
başlatır; kuruluysa uygulamayı açar. İlk kurulumda araçlar ve modeller indirilir.
Homebrew veya Apple geliştirici araçları eksikse kurucunun gösterdiği adımları
tamamlayın. Gerekirse aynı dosyayı tekrar açın. Hata ayrıntısı `installation.log`
dosyasına kaydedilir. Kurulu uygulama ayrıca `build/Meeting OS.app` içindedir.
Gerçek dosyalar `~/Library/Application Support/MeetingOS/` altında bulunur.
Codex çıktısındaki `meeting-os-local` bağlantısı proje klasörünü açar.

1. Toplantı adını yazıp **Yeni kayıt** seçin. İlk kullanımda macOS’un mikrofon
   ve ekran/sistem sesi izinlerini onaylayın. İzinler gerekirse **System Settings
   → Privacy & Security → Microphone / Screen & System Audio Recording** içinde
   **Meeting OS** için açılır. İzin değişikliğinden sonra uygulamayı yeniden açın.
2. Mikrofon ve sistem sesi ayrı WAV dosyalarına kaydedilir. Canlı metin geçicidir;
   kayıt devam ederken anonim konuşmacıların numaraları kalıcı kimlik değildir.
3. **Kaydı bitir** sesi kapatır, bekleyen parçaları işler ve yerel modelle nihai
   transkripti ayrı bir arşiv kaydı olarak oluşturur. Canlı kayıt kurtarma için korunur.
4. Nihai metinde bir bölümü dinleyip **Düzelt** seçin. Metni veya konuşmacı adını
   değiştirebilirsiniz. Özgün metin ve düzeltme geçmişi korunur.
5. **Özet** ekranında her maddenin kaynak alıntısını kontrol edin.
   Kayıt son işlemi ve dosya içe aktarımı bittiğinde yerel analiz otomatik başlar.
   İsim/metin düzeltince analiz eski işaretlenir; **Analizi güncelle** seçin.
6. Aynı kişinin sonraki toplantılarda tanınması için en az 3 saniyelik temiz,
   tek konuşmacılı bir bölümü dinleyin; temiz ses onayını işaretleyip **Ses
   profilini kaydet** seçin. İsim düzeltmek tek başına profil eğitmez. Gürültülü,
   çakışan veya kısa bağlamlı örnekler reddedilir. Aynı adlı farklı kişilere
   ayırt edici adlar verin. Belirsiz eşleşmeler isimsiz kalır.

Kenar çubuğundaki **Yazıya çevirme** seçimi varsayılan olarak OpenRouter’dır: kayıt bitince ses seçili modele gönderilir, bu Mac’te model yüklenmez, konuşmacı ayrımı sağlayıcıdan gelir (varsayılan Deepgram Nova-3). Bu modda kayıt sırasında canlı metin yoktur. Bitmemiş kayıtlar başlıktaki **OpenRouter ile yazıya çevir** ile gönderilir. Kayıtlı ses dosyaları **OpenRouter ile ses aç** üzerinden yazıya çevrilir; yerel
`import` ve `transcript_import` yolları CLI’de durur, kenar çubuğunda düğmeleri yoktur.
Bir toplantıyı silmek için listede sağ tıklayıp **Toplantıyı sil…** seçin veya
başlıktaki çöp kutusunu kullanın; onaydan sonra transkript, düzeltmeler, özet,
görevler ve toplantıya ait ses klasörü silinir, ses profilleri korunur. Üzerinde iş
süren toplantı silinemez. Arama seçili toplantının metnini ve konuşmacılarını
filtreler. Markdown, SRT ve JSON dışa aktarımı vardır; JSON export ses vektörlerini
içermez. **Sözlük ve ses profilleri** bölümünde kişi adlarını ve PM terimlerini
satır satır ekleyebilir, kaydedilmiş profilleri silebilirsiniz.

## Günlük kullanım kısayolları ve kontrol

- **⌘R** kaydı başlatır/bitirir. Kayıt sırasında **⌘M** önemli an, **⌘⇧M** karar, **⌘⌥M** bana görev, **⌘⌃M** sonra bak işareti koyar; işaretler kayıt bitince Kontrol sekmesinin en üstünde ve ilgili paragrafta görünür.
- **Kontrol** sekmesi bütün metni okumak yerine şüpheli yerleri sıralar: onay bekleyen isim (“Sol Üst?” → Onayla), isimsiz konuşmacı, çakışan konuşma, kısa sesle tanıma, sahibi belirsiz görev. Altında kimlik karnesi (otomatik doğru/yanlış, öneri onay/red, kaçırılan, metin düzeltmesi) vardır.
- **Okuma görünümü** aynı kişinin ardışık bölümlerini paragraf yapar, “hı hı/tabii” araya girişlerini katlar, dolgu seslerini gizler (kapatılabilir). **Bölümler** ham kayıtları gösterir.
- **Görevlerim → Sonraki toplantı gündemi…** son 5 toplantının açık görev, soru ve kararlarından kaynaklı bir Markdown taslak kaydeder; hiçbir yere gönderilmez.
- Kayıt sırasında ekran uykusu engellenir (sistem sesi yakalama ekran uyuyunca düşer). Mikrofon hoparlör yankısı yüklenmeden atlanır.
- CLI: `quality report` (düzeltmelerinizden WER ve kimlik karnesi), `quality compare --model … --allow-upload` (modelleri kendi düzeltmelerinize karşı ölçer), `agenda --output gundem.md`.

## Özet, görevler ve hafıza

**Görevlerim**: Boran’a atanmış, bu toplantıya ait veya bütün görevleri görün.
Başlık/sahip/tarihi düzenleyin; Açık / Devam ediyor / Tamamlandı / Kaldırıldı
seçin. Yeniden analiz elle düzenlemeleri ve görev durumunu sıfırlamaz. Sonraki
analizin desteklemediği görevler güncel değil diye işaretlenir; silinmez.
Belirsiz sahiplik boş bırakılır. Tarihler kayıtta söylendiği gibi gösterilir;
“yarın” otomatik takvim tarihine çevrilmez. İsimlerin doğru olması görev
sahipliğinin doğruluğunu etkiler.

**Taslak hazırla** yalnızca seçilen görevin kanıtlarını kullanarak bu Mac’te
incelemeniz için metin üretir. Taslak öneridir; gerçek dünya işi tamamlanmış
sayılmaz. **Codex / Claude Code / ChatGPT için paket kaydet** kaynaklar, görev ve
varsa güncel taslağı bir Markdown dosyasına yazar. Hiçbir agente kendiliğinden
mesaj göndermez veya iş başlatmaz. Başka uygulamaya dosyayı verdiğinizde o
uygulamanın veri politikası geçerlidir. Codex ve Claude abonelikleri API
kredisi olarak kullanılmaz.

**Hafıza** tüm tamamlanmış toplantılarda anahtar kelime arar. **Kayıtlardan
yanıtla** en fazla 12 ilgili bölümle yerel, alıntılı bir yanıt üretir. Yeterli
kaynak yoksa yanıt vermekten kaçınır. Arama sözcük tabanlıdır; anlamca benzer
ama farklı kelimelerle yazılmış bütün kayıtları bulma garantisi yoktur.

**Dışa aktar → Özet ve görevler** paylaşmaya hazır yerel Markdown üretir.
Salt okunur MCP bağlantısı için [V1 kullanım rehberi](docs/V1_USAGE.md).

## Model seçimi ve ölçülmüş kalite

- Canlı STT: **MLX Whisper large-v3-turbo**.
- Nihai / içe aktarılan ses: **MLX Whisper large-v3**.
- Konuşma bölgeleri: **Silero VAD**.
- Nihai konuşmacı ayrımı: **sherpa-onnx, pyannote segmentation 3.0 + TitaNet-small**.
- Kalıcı kişi eşleştirme: **Resemblyzer**, model sürümüne bağlı SQLite profilleri.
- Yerel analiz: **Qwen3-4B-Instruct-2507, MLX 4-bit**; JSON yapısı üretim sırasında sınırlandırılır, kaynak alıntıları ayrıca doğrulanır.
- Whisper CPU, whisper.cpp ve ECAPA karşılaştırma için CLI’de bulunur.

M4 / 16 GB üzerinde 12 Türkçe insan okuma kaydında kelime hata oranı büyük
modelde **%8,2**, turbo modelde **%11,9** ölçüldü. Bu küçük set gerçek toplantı
kalitesini kanıtlamaz. Türkçe/İngilizce sentetik geçiş örneği, gerçek ses kimliği
ve konuşmacı testleriyle birlikte tüm kapsam/sınırlar [VALIDATION.md](docs/VALIDATION.md)
içindedir. 3–5 kendi toplantınız için [benchmark rehberi](docs/BENCHMARK.md) ve
`benchmarks/manifest.example.json` hazırdır.

## Kayıt güvenliği ve sınırlar

Ses kaydedici transkripsiyondan bağımsız çalışır, kapanmış WAV parçalarını kendi
kalıcı günlüğüne yazar. Python işlemi kesilse bile tamamlanmış ses parçaları
**Son transkripti oluştur / Kurtar** ile işlenebilir. Ani sistem kapanışında henüz
kapanmamış son parça kurtarılamayabilir. Uygulamadan normal çıkış, sürmekte olan
kaydın kapanmasını ve son işlemin tamamlanmasını bekler.

Arayüzde kayıt üst sınırı 4 saattir. WAV kayıt yaklaşık 2 GB/saat alan
kullanabilir; boş disk alanını buna göre ayırın. Kaydedici 1,2 GB altında
başlamaz, yaklaşık 1 GB kaldığında kapanmış parçaları koruyarak durur. Kulaklık kullanımı önerilir:
akustik echo cancellation yoktur; hoparlör sesi mikrofona geri girerse çift
metin/konuşmacı karışıklığı olabilir. Diğer uygulamaların sistem sesi de alınır.
Ekran kareleri saklanmaz. Çakışan konuşmaların tüm kelimelerini kurtarma,
Bluetooth/uyku/ekran kilidi sonrası kesintisizlik ve uzun cihaz kaydı henüz
kanıtlanmış değildir. İlk macOS izin penceresi kullanıcı etkileşimi gerektirir;
bu pencere otomasyonla geçilmedi.

## CLI

Proje klasöründen:

```sh
.venv/bin/python -m meeting_os doctor
.venv/bin/python -m meeting_os record /local/path/toplanti --live --seconds 3600
.venv/bin/python -m meeting_os finalize /local/path/toplanti --title 'Sprint planlama'
.venv/bin/python -m meeting_os import /path/meeting.m4a --title 'Görüşme'
.venv/bin/python -m meeting_os meetings
.venv/bin/python -m meeting_os show MEETING_ID
.venv/bin/python -m meeting_os label-segment MEETING_ID SEGMENT_ID 'İpek'
.venv/bin/python -m meeting_os enroll MEETING_ID SEGMENT_ID 'İpek' --confirmed-clean
.venv/bin/python -m meeting_os profiles
.venv/bin/python -m meeting_os analyze MEETING_ID
.venv/bin/python -m meeting_os actions --owner Boran
.venv/bin/python -m meeting_os prepare TASK_ID
.venv/bin/python -m meeting_os handoff TASK_ID /local/path/task.md
.venv/bin/python -m meeting_os ask "onboarding PRD"
.venv/bin/python -m meeting_os benchmark benchmarks/manifest.example.json --output /local/path/results
```

Varsayılan DB `~/Library/Application Support/MeetingOS/meeting-os.sqlite`.
İzole test için `--db /local/test.sqlite` seçeneğini **alt komuttan önce** verin.
`transcribe --help` model/motor/dil/eşik seçeneklerini gösterir. `--language auto`
çok dilli başlangıç algılar; `tr` Türkçe ağırlıklı toplantılar içindir ve İngilizce
kelimeler transcribe edilir, çeviri yapılmaz. `vocabulary.txt` bir ipucudur;
isimlerin kesin yazılmasını garanti eden otomatik değiştirme listesi değildir.

## Başka bir Mac / yeniden kurulum

Kaynak: <https://github.com/borankaraduman-star/meeting-os> — en son sürüm ZIP’i ve SHA256 toplamı
<https://github.com/borankaraduman-star/meeting-os/releases/latest> adresinde. Git ile:

```sh
git clone https://github.com/borankaraduman-star/meeting-os.git
cd meeting-os && open "Meeting OS.command"
```

macOS 15+, Apple Silicon, Xcode Command Line Tools, Python 3.12 ve ffmpeg gerekir.
ZIP kullanıyorsanız açıp kaynak klasörünü iCloud dışında yerel bir dizine yerleştirin.
Yeni Mac’te OpenRouter anahtarını uygulamadaki **OpenRouter ile ses aç** penceresinden bir kez
kaydedin (anahtar o Mac’in Anahtar Zinciri’nde kalır); ses profilleri ve toplantılar Mac’e özeldir,
taşınmaz.
`Meeting OS.command` dosyasını çift tıklayın; eksik Homebrew/Python/ffmpeg araçlarını
kurmaya yönlendirir ve ardından `scripts/setup.sh` çalıştırır.
macOS indirilen dosyayı engellerse Sistem Ayarları → Gizlilik ve Güvenlik içindeki
uyarıyı inceleyin; bu paket Apple tarafından noterlenmiş bir kurucu değildir. Kurulum paketleri ve ücretsiz modelleri indirir; inference sesinizi
yüklemez. Test edilmiş paket sürümleri `requirements-macos-tested.txt` içindedir.
Bu Mac’in bağımsız Python tabanı `MeetingOS/python-3.12`, ortamı
`MeetingOS/runtime-v0.1` altında; Codex önbelleğine bağımlı değildir.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/stress-capture.py
scripts/build-capture.sh
scripts/build-desktop.sh
```

Uygulama yerel ad-hoc imzalıdır; başka Mac’lere notarize edilmiş tek dosya
kurulum paketi değildir. App bundle bu yerel çalışma ortamını kullanır; proje ve
runtime klasörlerini silmeyin. Veri/üçüncü taraf kaynakları
[THIRD_PARTY.md](docs/THIRD_PARTY.md) içindedir.

CPU Whisper karşılaştırma ağırlığı disk alanı için kaldırılmıştır; sonuçları
korunur ve `models fetch whisper-turbo` ile yeniden indirilebilir. Canlı/nihai
MLX, konuşmacı ve yerel analiz modelleri bu Mac’te hazırdır.

## 1.0.3 bellek koruması

16 GB Mac için canlı ve nihai transkript varsayılanı `mlx-turbo` oldu. Büyük
Whisper modeli 32 GB altında yüklenmez. Bu bir hız/bellek–doğruluk tercihidir;
büyük modelle aynı doğruluk garanti edilmez. MLX önbelleği 64 MB ile sınırlandı.
Uygulama kendi işinin fiziksel bellek kullanımını ve macOS bellek uyarılarını
izler; kaynak baskısında işi durdurur. Kayıt sürüyorsa önce normal kapanış ister;
hâlihazırdaki model çağrısı dönerken gecikme olabilir. İşletim sistemi veya diğer
uygulamaların neden olduğu tüm bellek sorunlarını engelleme garantisi değildir.

## 1.0.4 kurulum ve kayıt durdurma

Standart kurulum artık yalnızca turbo STT, konuşmacı ve yerel özet modellerini indirir; büyük Whisper isteğe bağlı benchmark modelidir. Hugging Face CAS/Xet varsayılan olarak kapalıdır, HTTP indirme zaman aşımı 120 saniyedir. Hesap/token zorunlu değildir; açıkça ayarlanmış ortam değişkenleri korunur. Bu ayar tüm ağ hatalarını önleme garantisi değildir.

Kayıt yardımcısı durdurma sinyalinden sonra 15 saniye içinde kapanmazsa uygulama kendi yardımcısını sonlandırır ve kaydı eksik olarak işaretler. Tamamlanmış ses parçaları ve günlük korunur. Hâlen çalışan native model çağrısının iptali ayrı bir sınırlamadır; bu sürüm onun için kesin bir zaman garantisi vermez.

Güncel kalite döngüsü ve kalan kabul testleri: [ITERATION_CHECKPOINT](docs/ITERATION_CHECKPOINT.md).

## 1.0.5 — 16 GB Mac için transkripsiyon

`--engine auto` varsayılandır. 16 GB ve altı Mac'lerde quantize turbo whisper.cpp, GPU kapalı ve iki CPU iş parçacığıyla çalışır. Kurulum uygun modeli ve sabit sürümlü whisper.cpp derlemesini hazırlar. Özel model yolu verirken `--engine mlx`, `cpp` veya `whisper` belirtin.

Ağır komutlar ayrı süreçlerde bellek baskısı ve süreç grubu belleği izlenerek çalışır. Örneklemeli koruma her işletim sistemi arızasını önleme garantisi değildir. Canlı metin ayrı işçilerde üretilir; ana süreç ölürse ses yakalama ve model süreçleri arkada bırakılmaz. Tamamlanmış ses parçaları korunur.

Kapak kapalıyken dahili mikrofon donanımsal olarak kapanır; uygulama bu durumu gösterir. Kapağı açın veya harici mikrofon kullanın.

16 GB Mac'te özet/görev analizi otomatik başlamaz; Analiz sekmesinden isteğe bağlı çalıştırılır ve bellek korumasına tabidir. Bu bilgisayarın mevcut yükünde büyük özet modeli bellek baskısına takıldı; küçük model kalite testini geçmediği için varsayılan yapılmadı.

[Bu Mac'te ölçülen sonuçlar](docs/RELIABILITY_1.0.5.md).

### İsteğe bağlı OpenRouter transkripsiyonu

Sol menüde **OpenRouter ile ses aç**, kullanıcı onayıyla varsayılan `openai/gpt-transcribe` veya model menüsündeki dört doğrulanmış alternatifi kullanır. Bu ücretli bulut seçeneği yerel varsayılanları değiştirmez. Anahtar macOS Anahtar Zinciri’nde tutulur; konuşmacı ayrımı ve özet/görev analizi yerelde kalır. Kurulum, fiyat, devam etme ve doğrulama sınırları: [OpenRouter rehberi](docs/OPENROUTER.md).
