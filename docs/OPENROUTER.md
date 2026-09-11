# OpenRouter transkripsiyon modelleri

Bu seçenek ücretli ve bulut tabanlıdır. 9 Eylül 2026 kullanıcı kararıyla **varsayılan yazıya çevirme yolu OpenRouter’dır ve bu yolda bu Mac’te hiçbir model yüklenmez**: canlı STT, Sherpa konuşmacı ayrımı, Resemblyzer kimlik ve bellek baskısı kapısı devreye girmez. Yerel model kenar çubuğundaki “Yazıya çevirme” seçiminden hâlâ seçilebilir. Native optimizasyon otomasyonu duraklatılmıştır.

## Kayıt sonrası bulut yolu (varsayılan)

1. Ayarlar (⌘,) → Sistem → **Yazıya çevirme** OpenRouter olsun ve aynı bölümden model seçilsin (kenar çubuğunda seçici yoktur). Varsayılan model konuşmacı ayrımı sunan `microsoft/mai-transcribe-2` (Azure). `deepgram/nova-3` de ayrım sunar ama 9 Eylül 2026 gerçek Türkçe testinde aksan işaretlerini düşürdü ve dil verilmezse anlamsız çıktı verdi; Türkçe için önerilmez. Diğer beş modelde konuşmacılar ayrılmaz, yalnız kaynak etiketi kalır.
2. **Yeni kayıt** bu modda canlı önizleme olmadan alınır (`record` komutu `--live` almaz). Kayıt sırasında ekranda metin yoktur.
3. Kayıt bitince uygulama `openrouter-finalize MEETING --model M --allow-upload` başlatır. Mic ve sistem parçaları dosya kopyalamayla iki tam WAV’a birleştirilir, her kaynak ffmpeg ile en fazla 20 dakikalık Opus parçalarına sıkıştırılır (ayrım sunmayan modellerde 30 saniyelik pencereler), dijital sessiz parçalar yüklenmez. Sistem sesi için sağlayıcı ayrımı istenir (`verbose_json`, `timestamp_granularities: ["segment"]`, `provider.options.deepgram.diarize` / `azure.diarization.enabled`).
4. Etiketler: mikrofon = **Ayarlar’daki adınız**; sistem sesi = **Konuşmacı 1, 2, …** (sağlayıcı numarası). Ardından **hafif yerel ses profili adımı** çalışır: her ayrılmış bölümden (≥3 s) Resemblyzer vektörü çıkarılır, küme ortalaması kayıtlı profillerle eşleştirilir (isim eşiği 0.87, marj 0.05; 0.83 üstü ve marjı yeten kümeler öneri olarak gösterilir) ve eşleşen kümeler otomatik isim alır. Bu adım bellek uyarı seviyesinde (2) çalışır, kritik seviyede (4) atlanır; başarısız olursa transkript yine tamamlanır ve altbilgide “eşleştirme atlandı” görünür. Kullanıcı bir bölümü düzenleyip **Bu konuşmacıyı adlandır ve profili kaydet** dediğinde küme adlandırılır ve küme merkezi profil olarak kaydedilir; sonraki toplantılarda aynı ses otomatik tanınır. Bu, “yerelde model yok” kuralının bilinçli tek istisnasıdır (embedder yüz MB mertebesinde). Sağlayıcı numaraları parça içinde tutarlıdır; 20 dakikayı aşan kayıtlarda parçalar arası eşleşme yoktur ve etiket `Konuşmacı <parça>-<n>` olur. Ayrım olmayan modelde sistem sesi **Karşı taraf** olarak tek etikettir. Kalıcı ses profili eşleştirmesi bu yolda da çalışır: kayıtlı profillerle eşleşen kümeler adlarını kendiliğinden alır.
5. Her parça transkriptiyle birlikte tek işlemde checkpoint’lenir. Kesintide başlıktaki **OpenRouter ile yazıya çevir** aynı modelle sürdürür; farklı model reddedilir. Bitmemiş eski yerel kayıtlar da aynı düğmeyle buluta gönderilebilir; geçici canlı metin silinir ve bulut metniyle değişir.
6. **OpenRouter ile ses aç** artık aynı bulut-only yolu kullanır (`openrouter-import --no-local`). Eski Sherpa’lı `openrouter-import` yolu yalnız CLI’de ve `--no-local` verilmeden çalışır.

Gerçek ölçüm (9 Eylül 2026, aynı 60 s Türkçe podcast parçası): MAI-Transcribe 2 $0.0017, 2.4 s, düzgün Türkçe, ayrım iki konuşmacıyı kısa onaylara kadar ayırdı; GPT Transcribe $0.0045, düzgün Türkçe, ayrım yok; Deepgram Nova-3 $0.0043, aksan işaretleri eksik, dil verilmezse “Marketing” gibi tek kelime. 142 s MAI ile $0.0039. Deepgram Nova-3 için OpenRouter uç noktası 9 Eylül 2026’da doğrulandı (sağlayıcı Deepgram, $0.0043 birim fiyat; dakika başına olduğu Deepgram liste fiyatıyla örtüşür ama OpenRouter faturasıyla ölçülmedi). MAI-Transcribe 2 uç noktası Azure; fiyat birimi doğrulanmadı. Türkçe kalitesi ve konuşmacı ayrımı doğruluğu bu cihazda henüz gerçek istekle ölçülmedi.


## Kullanım

1. Sol menüde **OpenRouter ile ses aç**.
2. OpenRouter API anahtarını güvenli alana girip **Anahtarı kaydet** (Ayarlar → Sistem → **OpenRouter anahtarı** satırından da girilir). Anahtar iki yerde durur: uygulamanın klasöründeki yalnız size açık dosya (`~/Library/Application Support/MeetingOS/openrouter.key`, 0600) ve yedek olarak macOS Anahtar Zinciri (`local.boran.meeting-os.openrouter`, hesap `openrouter`). **Uygulama Anahtar Zinciri’ni en fazla bir kez okur** ve okuduğunu bu dosyaya alır; sonraki açılışlar, işler ve güncellemeler yalnız dosyayı okur (her güncelleme uygulamanın imzasını değiştirdiği için macOS aksi hâlde her seferinde yeniden soruyordu). `scripts/install.sh` sırasında anahtarı verirseniz dosya kurulumda yazılır ve Anahtar Zinciri penceresi hiç çıkmaz. Python tarafı hiçbir zaman `security` çağırmaz: yalnız `OPENROUTER_API_KEY` ortam değişkenine, sonra bu dosyaya bakar; ikisi de yoksa iş “uygulamayı bir kez açın (Ayarlar → Sistem)” diyerek durur. Anahtar CLI argümanlarına, SQLite’a veya loglara yazılmaz; başka uygulamaların anahtarları aranmaz.
3. Transkripsiyon modelini, dosyayı ve başlığı seçin. Varsayılan `microsoft/mai-transcribe-2` (MAI-Transcribe 2; ≈ $0,10/saat, konuşmacı ayrımı var). Gönderim/ücret kutusunu işaretleyip **Yükle ve yazıya çevir**.
4. Transkript tamamlanınca konuşmacı etiketlerini düzeltin. Özet, karar ve görevler bulut modunda transkript biter bitmez kendiliğinden hazırlanır (OpenRouter · `openai/gpt-4.1-mini`); **Özet** sekmesinden yeniden üretilebilir. Yerel yazıya çevirme seçiliyse 16 GB ve altı Mac’lerde analiz otomatik başlatılmaz. Metinde desteklenmeyen sorumlu/tarih üretilmemesi için mevcut kaynak-alıntısı doğrulamaları kullanılır; sonuçlar yine incelenmelidir.
5. Ağ hatasında tamamlanmış parçalar saklanır. Aynı toplantıyı seçip **İşlemi sürdür**. Belirsiz ağ hatasından önce sunucu ücret kesmiş olabilir; otomatik tekrar yoktur. Kaynağı veya modeli değişmiş işe devam edilmez.

CLI (repo dizininden):

```sh
.venv/bin/python -m meeting_os openrouter-import '/absolute/path/meeting.m4a' --title 'Toplantı' --model openai/gpt-transcribe --allow-upload
.venv/bin/python -m meeting_os openrouter-import --resume MEETING_ID --allow-upload
.venv/bin/python -m meeting_os analyze MEETING_ID
```

## İşleme ve sınırlar

Dosya yerelde mono 16 kHz WAV kopyasına dönüştürülür; orijinal dosya değiştirilmez. Sherpa konuşmacı ayrımı ayrı, bellek korumalı yerel süreçte çalışır. Konuşmacı aralıkları en fazla 30 saniyeye bölünür; çakışan konuşma iki kez yüklenmez, belirsiz konuşmacı olarak etiketlenir. Metin GPT Transcribe’dan gelir. Zamanlar ses parçalarının sınırlarıdır, kelime zamanları değildir. Güven puanı uydurulmaz. Yerel voiceprint eşleştirmesi korunur; otomatik profil kaydı yapılmaz. Sesler yalnız kullanıcı başlattığında OpenRouter üzerinden sağlayıcıya gönderilir. UI kaydı başlatmaz. Aynı anda tek OpenRouter işi çalışır.

Varsayılan model `microsoft/mai-transcribe-2` (≈ $0,10/saat, konuşmacı ayrımı var); uygulamanın kayıt sonrası bulut yolu bu modeli kullanır. Menüde GPT Transcribe, Deepgram Nova-3, GPT-4o Transcribe, GPT-4o Mini Transcribe, Whisper Large V3 ve Whisper Large V3 Turbo da seçilebilir. (Python tarafındaki `STT_MODEL` sabiti hâlâ `openai/gpt-transcribe`; model verilmeden çağrılan CLI yolunda bu geçerlidir, uygulama her zaman seçili modeli açıkça geçirir.) Liste 9 Eylül 2026’da resmî transkripsiyon kataloğu ve her modelin aktif endpointleriyle doğrulandı. GPT modelleri OpenAI; Whisper Large V3 DeepInfra/Together/Groq; Turbo DeepInfra/Groq üzerinden sunuluyor. Arayüz yalnız doğrulanmış beş modeli listeler; katalog otomatik yenilenmez. Sağlayıcı/model mevcudiyeti değişebilir; hata halinde sessiz model veya doğrudan OpenAI API fallback’i yoktur. Seçilen model API isteğinde, toplantı metadata’sında ve parça metriklerinde saklanır. Devam eden işin modeli değiştirilemez; başka model yeni toplantı gerektirir. Eski checkpoints GPT Transcribe’a bağlı olarak taşınır. Doğrulanmamış sözlük/prompt seçenekleri gönderilmez. Ses kaydı en fazla dört saat olabilir; 30–40 dakika için planlama testi vardır, canlı kalite/süre garantisi yoktur. Yerel diarization ve analiz modellerinin daha önce kurulmuş olması gerekir.

## Doğrulanan kaynaklar — 9 Eylül 2026

- [OpenRouter model sayfası](https://openrouter.ai/openai/gpt-transcribe): $0.0045/dakika; 30 dakika yaklaşık $0.135, 40 dakika $0.18. Analiz burada yereldir. Gerçek faturalama sağlayıcı kullanımına bağlıdır.
- [OpenRouter STT](https://openrouter.ai/docs/guides/overview/multimodal/stt): `/api/v1/audio/transcriptions`, JSON base64, kullanım verisi; uzun sesleri bölme önerisi. Top-level prompt kullanılmıyor.
- Genel katalog API’si ve `/api/v1/models/openai/gpt-transcribe/endpoints` doğrudan sorgulandı; model ve aktif OpenAI sağlayıcısı doğrulandı. Bu, kullanıcının anahtar/bakiye erişiminin canlı testi değildir.

## Kişi tanıma ve okunabilir transkript (9 Eylül 2026 akşamı)

- Puan = profil merkezine benzerlik ile en yakın tek örneğe benzerliğin ortalaması. İsim eşiği 0.87, marj 0.05. 0.83–0.87 arası ve marjı yeten kümeler “Sol Üst?” diye önerilir; paragraf başlığındaki **Onayla** tek tıkla adı verir ve örnek ekler.
- Kendini besleyen profil: 0.93 üstü benzerlik, 0.10 üstü marj ve 10 s üstü küme her toplantıda bir örnek ekler (kişi başına en fazla 8, `auto:<toplantı>:<küme>` kaynaklı).
- Kısa onay kümeleri (“hı hı”, toplam ≥2 s) parçaları birleştirilerek tek vektörle eşlenir.
- Okuma görünümü: aynı kişinin ardışık bölümleri tek paragraf; başka kişinin 1.5 s altı, ≤2 kelimelik araya girişleri paragrafın altına katlanır (“N kısa onay katlandı · Göster”). Bölümler görünümü ham kayıtları gösterir. Bulut bayrakları toplantı başına tek bilgi satırında; kart altında yalnız olağandışı bayraklar (yankı, belirsiz konuşmacı).
- Analiz girdisinden yankı bölümleri ve ≤2 kelimelik/1.5 s altı onaylar çıkarılır.

## Özerk oturum eklemeleri (9 Eylül 2026, 05:00–)

- **Mikrofon kapısı:** mikrofon parçası, kaydın `mic-gate.jsonl` günlüğündeki açık pencerelerle 1,0 sn’den az kesişiyorsa hiç yüklenmez; `cloud_chunks.usage = {"skipped":"mic_gated"}` olarak checkpoint’lenir, `metadata.mic_gated_windows` sayar. Günlüğü olmayan (eski) kayıtlarda davranış değişmez. Parça kırpılmaz: bir saniyelik gerçek kesişme parçayı bütün olarak tutar.
- **Yankı atlama:** mikrofon 30 s pencereleri, 50 ms ses-zarfı korelasyonu ile sistem sesine karşı ölçülür; ≥0.5 (yankı 0.72–0.88, ilgisiz konuşma 0.07 ölçüldü) ise yüklenmez, `cloud_chunks.usage = {"skipped":"echo"}` olarak checkpoint’lenir; `metadata.echo_windows_skipped`.
- **Bulut analiz:** `analyze/prepare/ask --openrouter-model` (`openai/gpt-4.1-mini` varsayılan; `gpt-4o-mini`, `gemini-2.5-flash`). Yerel bellek kapısından geçmez. Model alıntıları `locate_quote` ile kaynak metnin birebir parçasına eşlenir (büyük/küçük harf, noktalama, tek kelime farkı), eşlenemeyen alıntı analizi reddettirir. Uygulama OpenRouter modundayken analiz otomatik başlar ve bu modeli kullanır. İlk gerçek koşu: 69 s toplantı, 6 s, doğru Türkçe özet ve risk maddeleri.
- **Kontrol sekmesi:** `review_queue` — onay bekleyen isim, isimsiz konuşmacı (toplam süre ve en yakın profil), çakışan konuşma, kısa sesle tanıma, emin olunmayan ASR, sahibi belirsiz görev; her madde neden şüpheli olduğunu ve tek eylemi gösterir.
- **Kalite seti:** `quality report` (metin düzeltmelerinden WER, kimlik karnesi: otomatik doğru/yanlış, öneri onay/red, kaçırılan) ve `quality compare --model … --allow-upload` (düzeltilen bölümleri seçilen modellerle yeniden çevirip kullanıcı metnine karşı WER ve maliyet). Model eğitilmez; hafızadır.
- **Kayıt sırasında ekran uykusu engellenir** (IOPM display-sleep beyanı): ekran uyuyunca ScreenCaptureKit akışı ölüyordu (“Failed to find any displays”).
- Ajan katkısı: aynı dosyayı tekrar işlememe (`check_duplicate`, `register_import_digest`), yeniden açılışta kurtarılabilir toplantının otomatik seçimi, Depolama paneli (`storage_report`).

## 05:20 sonrası eklemeler

- Parçalar 3 paralel yüklenir (`UPLOAD_WORKERS`), her başarılı parça kardeşi hata verse de checkpoint’lenir; parça planı yalnız ücretsiz (sessiz/yankı) checkpoint’ler varken değişebilir.
- Aynı toplantı içinde parçalar arası kümeler ses vektörüyle bağlanır (≥0.90; ölçüm 0.991 aynı, ≤0.85 farklı) ve tek “Konuşmacı N” etiketi alır.
- ⌘M işaretleri `capture_dir/markers.jsonl` → `metadata.markers` → Kontrol kuyruğunda `marker` maddeleri.
- Okuma görünümünde dolgu sesleri gizlenir (`Fillers.clean`); kayıt, arama ve kanıt alıntıları ham metni korur. Modeller arası fark ölçümü (MAI vs GPT Transcribe, 3×60 s): WER 0.04–0.20, farkın çoğu dolgu sesleri.
- Gündem taslağı: `agenda` eylemi/CLI, son 5 tamamlanmış toplantı.

## Hata mesajları

HTTP hataları koda göre ayrışır: 401 anahtar reddedildi, 402 bakiye yetersiz, 429 hız sınırı, 5xx hizmet hatası. Her mesaj HTTP kodunu ve “otomatik tekrar yapılmadı; tamamlanan parçalar korunuyor” notunu içerir. Anahtar veya yanıt içeriği mesaja girmez.

## Test durumu

65 Python testi (bulut-only finalize/içe aktarma, diarization istek gövdesi ve bölüm ayrıştırma, checkpoint/sürdürme, model kilidi dahil) ve 47 Swift testi. Önceki 58 Python testi (56 önceki + Anahtar Zinciri zaman aşımı/red ayrımı + HTTP mesajları): beş modelin istekle eşleşmesi, model değişiminde checkpoint reddi, eski checkpoint geçişi, istemci kontratı, onaysız gönderim engeli, hatalarda gizli veri sızdırmama, yeniden yönlendirme engeli, parça checkpoint/devam, değişen kaynak reddi, 40 dakikalık parça planı, dosya import fixture’ı, mevcut masaüstü/metin aktarımı ve kaynaklı analiz testleri. 44 Swift testi geçti. Gerçek API çağrısı, özel ses yükleme veya canlı Türkçe doğruluk benchmark’ı yapılmadı. Keychain’e gerçek anahtar yazılmadı.

Model fiyatları aynı birimle dönmüyor: GPT-4o modellerinde token bazlı, Whisper modellerinde sağlayıcıya bağlı bilgiler var. Menü GPT Transcribe fiyatını yalnız o seçildiğinde gösterir; diğer seçeneklerde doğrulanmamış dakika tahmini yerine ilgili resmî model/fiyat bağlantısını açar.
