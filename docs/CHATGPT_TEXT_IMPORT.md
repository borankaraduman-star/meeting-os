# ChatGPT metni aktar

9 Eylül 2026 itibarıyla bu düğme kullanıcı isteğiyle kenar çubuğundan kaldırıldı; backend `transcript_import` yolu ve testleri duruyor, arayüzden erişilemez. Aşağıdaki akış eski arayüzü anlatır. Meeting OS sol menüde **ChatGPT metni aktar** düğmesini açın. **ChatGPT’yi aç** uygulamayı açar; Record kaydını orada kendiniz başlatın. Metni kopyalayıp bu pencereye yapıştırın veya UTF-8 .txt dosyası seçin. Toplantı adı verin → **Önizle** → **Yeni toplantıya kaydet**.

Aktarılan toplantı listede açılır; konuşmada arama ve Düzelt kullanılabilir. Ses yoktur; oynatma veya ses profili kaydetme sunulmaz. Konuşmacı etiketleri ses kimliği doğrulaması değildir.

En fazla1MiB/1000dolu satır. Düz satırlar, `Boran: metin`, `[Boran] metin`, `[00:12] Boran: metin` desteklenir. Başlangıç damgası yoksa zaman eklenmez; bitiş zamanları tahmin edilmez. Ham metin düzeltmelerden bağımsız korunur. Eksik zamanlar nedeniyle SRT dışa aktarma yerine Markdown/JSON kullanın.

Bu hesap entegrasyonu veya ücretsizAPI değildir. Kayıt başlatma ve ChatGPT sonucunu getirme manueldir. Yerel ses optimizasyonu kullanıcı kararıyla duraklatıldı; önceki kayıtlar/modeller/önbellekler silinmedi.

Doğrulama:13Python testi ve44Swift testi geçti. Release derlendi, mevcut imza kimliğiyle yayımlandı ve bu Mac’te açıldı. Görsel tıklama testi yapılmadı; yeni mikrofon kaydı başlatılmadı.
