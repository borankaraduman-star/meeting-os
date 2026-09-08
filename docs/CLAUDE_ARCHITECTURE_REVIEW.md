**En yüksek somut arıza riskleri (5)**

**1. Mikrofon/sistem sesi arasında saat kayması (clock drift)**
ScreenCaptureKit (sistem sesi) ve mikrofon yakalaması muhtemelen farklı alt saatler/API'ler kullanıyor. Ayrı ayrı zaman damgalı WAV parçaları, uzun toplantılarda kümülatif drift nedeniyle sessizce hizadan çıkabilir; JSONL zaman damgaları tutarlı görünse de gerçek ses hizası kayar, bu da diarization ve segment eşlemesini bozar ama hata görünür bir crash üretmez.
*Aksiyon:* Her iki akış için ortak bir monotonic referans saat kullanın ve periyodik olarak (örn. her N saniyede) drift ölçüp loglayın; benchmark setine kasıtlı uzun (>30dk) bir kayıt ekleyin.

**2. Model değişince konuşmacı profillerinin sessizce yetim kalması**
Model-özel isim alanları (namespace) çapraz-model cosine karşılaştırmasını doğru şekilde engelliyor, ama bu aynı zamanda kullanıcı Resemblyzer/ECAPA/pyannote arasında geçiş yaptığında önceden enroll edilmiş profillerin o yeni model için hiç var olmaması anlamına geliyor. Sonuç: konuşmacı "unknown" olarak işaretlenir, ama kullanıcıya *neden* olduğu net değildir — bu bir bug değil ama davranışı bilmeyen kullanıcı için bug gibi görünür.
*Aksiyon:* CLI, aktif diarization modeli için enroll edilmemiş bilinen profilleri (başka modelde var olan) açıkça uyarsın: "Bu model için N profil eksik."

**3. M4/16GB'de sıralı model yüklemenin birleşik bellek çakışması**
MLX (Metal) ve whisper.cpp (Metal) karşılaştırmaları, "sıralı yükleme" varsayımına rağmen önceki modelin belleğinin tam serbest bırakıldığını garanti etmez (MLX lazy allocator, Metal driver cache). pyannote + büyük Whisper + embedding modeli zincirlemesi 16GB unified memory'de OOM veya termal throttle'a yol açabilir, özellikle benchmark koşusu sırasında arka arkaya modeller değiştiğinde.
*Aksiyon:* Her model geçişinde process izolasyonu (ayrı alt-process, tam bellek serbest bırakma) veya en azından peak RSS + Metal residual memory ölçümünü benchmark script'ine explicit assert olarak koyun.

**4. VAD segment sınırı kesintisi + vocabulary-prompt tasarımının birleşik etkisi**
Silero VAD sınırlı segmentler ürettiğinde, konuşma cümle ortasında kesilirse hem WER hem vocabulary recall doğrudan bundan zarar görür — tam da ölçmeye çalıştığınız metrikler. Orijinal segment metni değişmeden kaldığı ve düzeltme sadece post-hoc etiket seviyesinde olduğu için, sınır-kesintisi kaynaklı hatalar ASR çıktısında kalıcılaşır ve hiçbir mekanizma bunu telafi etmez.
*Aksiyon:* VAD segment sınırlarına küçük bir padding/overlap (örn. 200-300ms) ekleyip ASR'ye context penceresi olarak verin; sınır-kesintili segmentleri benchmark raporunda ayrı bir kategori olarak işaretleyin.

**5. Küçük değerlendirme seti + sızıntı riski + sentetik ikame baskısı**
3-5 gerçek toplantı, DER/kimlik false-accept/reject gibi metrikler için istatistiksel olarak zayıf bir temel oluşturur. Asıl risk teknik değil süreçsel: held-out speaker/session ayrımı test harness'inde *gerçekten* uygulanmazsa (örn. enroll sesi ile eval sesi aynı oturumdan geliyorsa), sonuçlar iyimser yanlılık taşır. Ayrıca zaman baskısı altında "sentetik fixture'lar kalite kanıtı değildir" ilkesinin ihlal edilip kalite iddialarının erken yapılması olası bir kayma noktası.
*Aksiyon:* Held-out ayrımını kod seviyesinde zorlayın (enroll ve eval konuşmacı/oturum ID'leri kesişmesin diye bir assert), ve raporlarda sentetik ile gerçek veri sonuçlarını asla aynı tabloda birleştirmeyin.

**Genel not:** Kapsam disiplini (özet/agent/yükleme yok) net ve doğru; en kırılgan noktalar zaman hizalaması, model-geçiş durumları ve ölçüm metodolojisinin kendisi — kod karmaşıklığından değil, sessizce yanlış varsayımlardan kaynaklanıyor.
