# Meeting OS — doğrulama raporu, 8 Eylül 2026

Teslim: çalışan yerel Mac uygulaması, CLI, kayıt yardımcısı, model adaptörleri,
SQLite ses hafızası, benchmark araçları ve kaynak kod. M4 / 16 GB, macOS 26.5.2.
Gerçek kullanıcı toplantısı verilmedi; aşağıdaki testleri toplantı kalitesi veya
biyometrik güvenilirlik garantisi olarak yorumlamayın.

## Uygulama ve dayanıklılık

- **31 otomatik test geçti.** Türkçe normalizasyon/DER, unknown/margin/model
  ayrımı, metin ve isim düzeltme, atomik profil kaydı, journal ve hata davranışı,
  native ONNX konuşmacı sınırları ve deterministik yeniden çalıştırma kapsanır.
- Swift kayıt yardımcısı ve SwiftUI uygulaması release olarak derlenip yerel
  imzalandı. Kaynak içindeki build scriptleri aynı paketleri üretir.
- Arayüzden FLEURS ses dosyası içe aktarıldı, transkript görüntülendi, konuşmacı
  etiketi kaydedildi; uygulama kapatılıp açıldığında etiket ve arşiv korundu. Son sürümde metin
  düzeltme ve sözlük kaydetme akışı da arayüzden geçti.
- Native PCM self-test ayrı mic/system WAV, ortak zaman tabanı ve kapanmış dosya
  biçimini doğruladı. Daha önceki gerçek 3 saniyelik cihaz kaydı 48 kHz mono mic /
  stereo system olarak geçti: `CAPTURE_SMOKE.json`.
- Ana uygulamada eksik mikrofon kullanım açıklaması bulundu ve giderildi.
  Ardından macOS izin bekleme aşamasına ulaşıldı. Bilgisayar kullanım aracı
  sistem izin penceresine erişimi engelledi; izin atlatılmadı. **Ana uygulamanın
  ilk macOS izinleri kullanıcı tarafından tamamlanmalı; GUI üzerinden gerçek
  kayıt→finalize uçtan uca bu nedenle doğrulanamadı.** İzin bekleyen kayıt
  durduruldu; normal iptal durumu ayrıca kodda ele alındı.
- Native kaydedicinin stdout alıcısı kapatıldığında süreç sağlam kaldı ve kendi
  günlüğünden ses yeniden oluşturuldu. 1.800 parça / iki kaynak / üç saat ses
  hızlandırılmış testte tam beklenen kare sayısıyla birleştirildi:
  `STRESS_CAPTURE.json`. Bu üç saat duvar saatiyle cihaz/ASR soak testi değildir.
- macOS process sandbox ile **tüm network erişimi engellenmişken** yerel
  transkripsiyon tamamlandı. Kullanıcının ağ ayarları değiştirilmedi.
- Python tabanı ve 1,5 GB ortam önbellekten kalıcı Application Support klasörüne
  taşındı; 31 test yeni ortamda geçti.

## Türkçe STT — gerçek insan sesi

Google FLEURS Turkish test split, ilk 12 kayıt, CC-BY-4.0. Okuma sesi; toplantı
değildir. Referans `raw_transcription`; normalized WER Türkçe harf/noktalama
normalizasyonu içerir, yazıyla/rakamla sayı eşdeğerliği içermez. Kişi/yer adları
ve sayılar bazı hataların kaynağıdır. Aynı dosyalar ve sözlük kullanıldı.

| Motor | Mikro WER | Medyan RTF (başlatma dahil) | Başarılı koşu |
|---|---:|---:|---:|
| MLX turbo + Sherpa | %11,89 | 0,521 | 12/12 |
| MLX large-v3 + Sherpa | %8,20 | 0,946 | 12/12 |

Buna göre canlı turbo, final/import large-v3 seçildi. Küçük kliplerin başlangıç
maliyeti RTF’yi artırır; bu ölçüm uzun toplantıda sürdürülebilir gecikme garantisi
vermez. Tam tablolar: `benchmarks/results-fleurs-tr/REPORT.md`, `report.json`.

## Diğer ASR karşılaştırmaları

İlk sentetik Türkçe/PM testinde 16,657 sn TTS + 5 sn sessizlik, beş yapılandırma,
10/10 koşu başarılı. TTS İngilizce telaffuzu ölçümü etkiler.

| Yapılandırma | Konuşma duvar süresi | RTF | WER |
|---|---:|---:|---:|
| MLX turbo + Resemblyzer | 7,37 sn | 0,442 | %14,3 |
| MLX large-v3 + Resemblyzer | 10,57 sn | 0,635 | %14,3 |
| whisper.cpp q5 turbo | 20,17 sn | 1,211 | %14,3 |
| OpenAI Whisper CPU turbo | 18,51 sn | 1,111 | %14,3 |
| MLX turbo + ECAPA | 6,90 sn | 0,414 | %14,3 |

Tüm sessizlik koşullarında 0 kelime. Ayrı Türkçe→İngilizce→Türkçe sentetik
örnekte üç MLX yapılandırması WER 0 ve entity recall %100 verdi. **Bu gerçek
insan code-switch doğruluğu değildir.** Tarihsel sonuçlar baseline diarization
ile alındı; yeni Sherpa sonuçlarıyla aynı koşu sayılmamalıdır.

## Konuşmacı ayrımı

Eski 2,5 sn embedding baseline tek sentetik kişiyi birden fazla kişiye böldü;
bu nedenle varsayılan olmaktan çıkarıldı. Sherpa pyannote3 segmentation +
TitaNet-small, global clustering .9 ile:

- Resmî dört konuşmacılı Çince test sesinde dört grup buldu. Gold etiket yok;
  yalnızca konuşmacı sayısı doğrulandı, DER iddiası yapılmıyor.
- LibriSpeech’den dört gerçek ses × üç farklı parça sırayla birleştirildi.
  .9 eşiğinde dört grup, **12/12 bölümde doğru çoğunluk ataması**; .7 eşiğinde
  altı grup, 11/12. Global optimal etiket eşlemesi kullanıldı.
  `DIARIZATION_HUMAN.json` ve yeniden üretme scripti mevcut.
- Kısa 9 sn sentetik iki ses örneğinde ayrım hâlâ zayıf. 15 sn altı bağlam ve
  canlı parçalar belirsizlik işareti taşır; bu örneklerden profil eğitimi yapılmaz.
- Doğal söz kesme/overlap ve gerçek toplantı DER’i henüz ölçülmedi. Oluşturulmuş
  okuma parçalarının sınırları insan etiketli konuşma RTTM’i değildir.

## Kalıcı ses kimliği

LibriSpeech dev-clean: sekiz gerçek konuşmacı, altısı kayıtlı/ikisi yeni.
Kayıt için bir ses, test için başka üç ses kullanıldı; DB kapatılıp yeniden
açıldı. Eşik .80, ikinci adaya margin .08. Her koşul 24 test (18 bilinen + 6
bilinmeyen); gürültü deterministik 20 dB SNR.

| Embedding / koşul | Doğru / 24 | Yanlış kişi ataması | İsimsiz kalan bilinen kişi |
|---|---:|---:|---:|
| Resemblyzer temiz | 24 | 0 | 0 |
| Resemblyzer gürültü | 11 | 0 | 13 |
| Resemblyzer 3 sn | 23 | 0 | 1 |
| ECAPA temiz | 19 | 0 | 5 |
| ECAPA gürültü | 6 | 0 | 18 |
| ECAPA 3 sn | 8 | 0 | 16 |

Resemblyzer varsayılan kaldı. Gürültüde çekimserlik yüksek; sıfır gözlenen yanlış
atama küçük testte garanti anlamına gelmez. Bunlar İngilizce sesli kitap sesleri;
Türkçe toplantı/farklı gün/farklı mikrofon genellemesi ölçülmedi.
`IDENTITY_HUMAN.json` tüm sonuçları içerir. Model hash’i değişirse eski profiller
farklı modelde kullanılmaz. Otomatik profil eğitimi yoktur.

## İnceleme ve kalan ölçüm işleri

Claude Code, mevcut Max oturumuyla kısa mimari ve kod inceleme checkpoint’lerinde
kullanıldı; meeting audio/transkriptleri bu incelemelere gönderilmedi, API anahtarı
kullanılmadı. İnceleme bulguları ve düzeltilen noktalar `REVIEW_RESOLUTION.md`.

Kendi 3–5 toplantınızda Türkçe code-switch, kişi adları, ses değişimi, yeni kişi,
uzun kayıt drift’i, overlap ve canlı gecikmeyi ölçmek için harness hazırdır.
Uyku/ekran kilidi/Bluetooth sonrası sorunsuz devam ve akustik echo cancellation
bu teslimde kanıtlanmış/uygulanmış özellikler değildir.
