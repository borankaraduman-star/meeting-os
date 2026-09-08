# OpenRouter transkripsiyon modelleri

Bu seçenek isteğe bağlı, ücretli ve bulut tabanlıdır. Yerel kayıt/STT varsayılanları değişmedi. Native optimizasyon otomasyonu hâlâ duraklatılmıştır.

## Kullanım

1. Sol menüde **OpenRouter ile ses aç**.
2. OpenRouter API anahtarını güvenli alana girip **Anahtarı kaydet**. Anahtar macOS Anahtar Zinciri’nde `local.boran.meeting-os.openrouter`, hesap `openrouter` olarak saklanır. İlk backend kullanımında macOS erişim sorabilir. Anahtar CLI argümanlarına, SQLite’a veya loglara yazılmaz. CLI ayrıca `OPENROUTER_API_KEY` ortam değişkenini kabul eder; başka uygulamaların anahtarları aranmaz.
3. Transkripsiyon modelini, dosyayı ve başlığı seçin. Varsayılan GPT Transcribe’dır. Gönderim/ücret kutusunu işaretleyip **Yükle ve yazıya çevir**.
4. Transkript tamamlanınca konuşmacı etiketlerini düzeltin. **Özet** sekmesinden özet, karar ve görevleri yerel modelle hazırlayın. 16 GB Mac’lerde mevcut davranış gereği analiz otomatik başlatılmaz. Metinde desteklenmeyen sorumlu/tarih üretilmemesi için mevcut kaynak-alıntısı doğrulamaları kullanılır; sonuçlar yine incelenmelidir.
5. Ağ hatasında tamamlanmış parçalar saklanır. Aynı toplantıyı seçip **İşlemi sürdür**. Belirsiz ağ hatasından önce sunucu ücret kesmiş olabilir; otomatik tekrar yoktur. Kaynağı veya modeli değişmiş işe devam edilmez.

CLI (repo dizininden):

```sh
.venv/bin/python -m meeting_os openrouter-import '/absolute/path/meeting.m4a' --title 'Toplantı' --model openai/gpt-transcribe --allow-upload
.venv/bin/python -m meeting_os openrouter-import --resume MEETING_ID --allow-upload
.venv/bin/python -m meeting_os analyze MEETING_ID
```

## İşleme ve sınırlar

Dosya yerelde mono 16 kHz WAV kopyasına dönüştürülür; orijinal dosya değiştirilmez. Sherpa konuşmacı ayrımı ayrı, bellek korumalı yerel süreçte çalışır. Konuşmacı aralıkları en fazla 30 saniyeye bölünür; çakışan konuşma iki kez yüklenmez, belirsiz konuşmacı olarak etiketlenir. Metin GPT Transcribe’dan gelir. Zamanlar ses parçalarının sınırlarıdır, kelime zamanları değildir. Güven puanı uydurulmaz. Yerel voiceprint eşleştirmesi korunur; otomatik profil kaydı yapılmaz. Sesler yalnız kullanıcı başlattığında OpenRouter üzerinden sağlayıcıya gönderilir. UI kaydı başlatmaz. Aynı anda tek OpenRouter işi çalışır.

Varsayılan model `openai/gpt-transcribe`. Menüde GPT-4o Transcribe, GPT-4o Mini Transcribe, Whisper Large V3 ve Whisper Large V3 Turbo da seçilebilir. Liste 9 Eylül 2026’da resmî transkripsiyon kataloğu ve her modelin aktif endpointleriyle doğrulandı. GPT modelleri OpenAI; Whisper Large V3 DeepInfra/Together/Groq; Turbo DeepInfra/Groq üzerinden sunuluyor. Arayüz yalnız doğrulanmış beş modeli listeler; katalog otomatik yenilenmez. Sağlayıcı/model mevcudiyeti değişebilir; hata halinde sessiz model veya doğrudan OpenAI API fallback’i yoktur. Seçilen model API isteğinde, toplantı metadata’sında ve parça metriklerinde saklanır. Devam eden işin modeli değiştirilemez; başka model yeni toplantı gerektirir. Eski checkpoints GPT Transcribe’a bağlı olarak taşınır. Doğrulanmamış sözlük/prompt seçenekleri gönderilmez. Ses kaydı en fazla dört saat olabilir; 30–40 dakika için planlama testi vardır, canlı kalite/süre garantisi yoktur. Yerel diarization ve analiz modellerinin daha önce kurulmuş olması gerekir.

## Doğrulanan kaynaklar — 9 Eylül 2026

- [OpenRouter model sayfası](https://openrouter.ai/openai/gpt-transcribe): $0.0045/dakika; 30 dakika yaklaşık $0.135, 40 dakika $0.18. Analiz burada yereldir. Gerçek faturalama sağlayıcı kullanımına bağlıdır.
- [OpenRouter STT](https://openrouter.ai/docs/guides/overview/multimodal/stt): `/api/v1/audio/transcriptions`, JSON base64, kullanım verisi; uzun sesleri bölme önerisi. Top-level prompt kullanılmıyor.
- Genel katalog API’si ve `/api/v1/models/openai/gpt-transcribe/endpoints` doğrudan sorgulandı; model ve aktif OpenAI sağlayıcısı doğrulandı. Bu, kullanıcının anahtar/bakiye erişiminin canlı testi değildir.

## Test durumu

56 Python testi: beş modelin istekle eşleşmesi, model değişiminde checkpoint reddi, eski checkpoint geçişi, istemci kontratı, onaysız gönderim engeli, hatalarda gizli veri sızdırmama, yeniden yönlendirme engeli, parça checkpoint/devam, değişen kaynak reddi, 40 dakikalık parça planı, dosya import fixture’ı, mevcut masaüstü/metin aktarımı ve kaynaklı analiz testleri. 44 Swift testi geçti. Gerçek API çağrısı, özel ses yükleme veya canlı Türkçe doğruluk benchmark’ı yapılmadı. Keychain’e gerçek anahtar yazılmadı.

Model fiyatları aynı birimle dönmüyor: GPT-4o modellerinde token bazlı, Whisper modellerinde sağlayıcıya bağlı bilgiler var. Menü GPT Transcribe fiyatını yalnız o seçildiğinde gösterir; diğer seçeneklerde doğrulanmamış dakika tahmini yerine ilgili resmî model/fiyat bağlantısını açar.
