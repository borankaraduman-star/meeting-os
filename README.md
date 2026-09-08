# Meeting OS — Boran’ın yerel toplantı hafızası

Mac uygulaması ve CLI: ayrı mikrofon/sistem sesi, canlı Türkçe transkript,
toplantı sonunda daha güçlü modelle nihai metin, konuşmacı ayrımı ve kalıcı ses
profilleri. Yerel özet, karar, risk, açık soru ve görev çıkarımı; Boran’ın görev
kuyruğu; kaynaklı arşiv araması ve görev taslakları. Varsayılan işleme bu Mac’te
yapılır; ücretli inference API’si veya otomatik dış servis aksiyonu yoktur.

## Bu Mac’te aç

**`Meeting OS.command` dosyasını çift tıklayın** veya `build/Meeting OS.app`
uygulamasını açın. Modeller ve Python ortamı kuruludur; yeniden indirme gerekmez.
Gerçek dosyalar `~/Library/Application Support/MeetingOS/` altında bulunur.
Codex çıktısındaki `meeting-os-local` bağlantısı proje klasörünü açar.

1. Toplantı adını yazıp **Yeni kayıt** seçin. İlk kullanımda macOS’un mikrofon
   ve ekran/sistem sesi izinlerini onaylayın. İzinler gerekirse **System Settings
   → Privacy & Security → Microphone / Screen & System Audio Recording** içinde
   **Meeting OS** için açılır. İzin değişikliğinden sonra uygulamayı yeniden açın.
2. Mikrofon ve sistem sesi ayrı WAV dosyalarına kaydedilir. Canlı metin geçicidir;
   kayıt devam ederken anonim konuşmacıların numaraları kalıcı kimlik değildir.
3. **Kaydı bitir** sesi kapatır, bekleyen parçaları işler ve büyük modelle nihai
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

**Ses dosyası aç** WAV/MP3/M4A/MP4 ve ffmpeg’in okuyabildiği diğer sesleri yerel
arşive kopyalayıp dönüştürür. Arama seçili toplantının metnini ve konuşmacılarını
filtreler. Markdown, SRT ve JSON dışa aktarımı vardır; JSON export ses vektörlerini
içermez. **Sözlük ve ses profilleri** bölümünde kişi adlarını ve PM terimlerini
satır satır ekleyebilir, kaydedilmiş profilleri silebilirsiniz.

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

macOS 15+, Apple Silicon, Xcode Command Line Tools, Python 3.12 ve ffmpeg gerekir.
Kaynak klasörünü iCloud dışındaki yerel bir dizine yerleştirip `scripts/setup.sh`
çalıştırın. Kurulum paketleri ve ücretsiz modelleri indirir; inference sesinizi
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
