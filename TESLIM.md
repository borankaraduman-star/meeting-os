# Meeting OS teslimi

**Aç:** [Meeting OS.command](Meeting%20OS.command)

Bu Mac için uygulama, modeller ve kalıcı Python ortamı hazır. İlk çalıştırmada
macOS mikrofon/sistem sesi izinlerini tamamlayın. İzin penceresi otomasyonla
geçilmedi; arayüzden gerçek kayıt testi bu adımda kaldı.

- Ayrı mic/system kayıt, canlı metin, büyük modelle final transkript.
- Metin/isim düzeltme, sesi dinleme, kalıcı profil ve sonraki kayıtta isim eşleştirme.
- Yerel arşiv, arama, özel sözlük, dosya içe aktarma, JSON/SRT/Markdown export.
- Bağımsız ses günlüğü, kesilen kayıt kurtarma, test/benchmark araçları.
- 31 test geçti; 24 Türkçe insan sesi STT koşusu başarılı. Küçük okuma setinde
  final model WER %8,2. Gerçek toplantı doğruluğu henüz ölçülmedi.

[Kullanım ve kurulum](README.md) · [Ölçümler ve sınırlar](docs/VALIDATION.md) ·
[3–5 toplantı benchmark rehberi](docs/BENCHMARK.md)

Claude Code mimari ve adversarial review yaptı; implementasyon Codex’te kaldı.
API kredisi kullanılmadı, ücretli inference veya toplantı verisini dışarı gönderen
aksiyon eklenmedi. Ses profilleri yalnızca açıkça kaydettiğiniz temiz örneklerle oluşur.

Yerel uygulama ad-hoc imzalıdır; başka Mac’e taşımak için kaynak ve kurulum
scriptleri kullanılır. Akustik echo cancellation yoktur; kulaklık önerilir.
