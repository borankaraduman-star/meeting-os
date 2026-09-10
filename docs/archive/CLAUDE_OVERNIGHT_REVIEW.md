## En yüksek riskli arayüzler

**Swift UI ↔ Python IPC sınırı** en kırılgan nokta: Protokol tanımlı değil (stdin/stdout JSON-lines mi, unix socket mu?). Bu belirsizken "robust jobs/recovery" iddiası boş. Somut soru: Python süreci crash olduğunda ses kaybı var mı, yoksa capture sürekli diske mi yazılıyor ve Python sadece tüketici mi? Eğer ses buffer'ı yalnızca Python process belleğindeyse, crash = kayıp toplantı. Bunu mimari olarak kilitlemeden UI'ya geçmek yanlış önceliklendirme.

**sherpa-onnx diarization iddiası doğrulanmamış varsayım.** "Publicly officially distributed" denmiş ama sherpa-onnx'in segmentation+embedding pipeline'ının orijinal 2.5s-pencere hatasını (tek konuşmacının 2-5 kümeye bölünmesi) gerçekten çözdüğü henüz kanıtlanmadı — sadece "pyannote gated, o yüzden bunu kullanacağız" mantığıyla seçilmiş. Bu, projenin fatal baseline sorununu çözmeden bütün UI/job/recovery katmanını inşa etmek riskidir. **Codex'in ilk işi UI değil, bu tek regresyon testini geçirmek olmalı** — geçmezse üstüne inşa edilen her şey yeniden yazılır.

**Live-tentative → final-refined transcript reconciliation.** Canlı yayında basit VAD/pencere ile geçici speaker etiketleri gösterilecek, sonra tam diarization ile "doğru" etiketler gelecek. Kullanıcı ekranda gördüğü "Konuşmacı 2" etiketinin finalize sonrası "Konuşmacı 5" olarak değişmesi UX'te güven kırar ve corrections tablosuyla çakışabilir (kullanıcı canlıda düzelttiği bir etiket, finalize geçince silinir mi, korunur mu?). Bu davranış tanımlanmadan "transcript playback/labels" özelliği yarım kalır.

**Profil eşleştirme eşiği (conservative identity).** "Full-utterance recognition works" ile "conservative persistent identities" arasında somut karar kuralı yok: Yeni diarization kümesi mevcut profile ne zaman birleştirilir, ne zaman "yeni/bilinmeyen konuşmacı" olarak bırakılır? Bir toplantı ortamında **yanlış birleştirme (iki kişiyi tek kişi sanmak) yanlış bölmeden çok daha kötü** — biri diğerinin sözlerine sahip çıkmış gibi görünür. Eşik/margin sadece full-utterance testinde kalibre edilmişse, kısa/gürültülü segmentlerde davranışı bilinmiyor.

## Somut kabul testleri

**Uzun capture (3+ saat):**
- 90. dakikada Mac uyku moduna geçsin/çıksın veya mikrofon başka bir uygulama tarafından kapılsın; final transcript'te süreklilik kaybı, kopyalanmış veya eksik segment olmamalı.
- Python süreci recording sırasında kill -9 ile öldürülsün; SQLite'ta resumable job kaydı olmalı, ham ses dosyası bozulmamış olmalı.
- 3 saatlik run boyunca Python RSS ve disk kullanımı sınırlı büyümeli (unbounded buffer regresyonu yakalanmalı).

**Offline garantisi:**
- Ağ arayüzü tamamen kapalıyken (airplane mode + firewall) live capture → finalize → diarization → export tam akışı çalışmalı; bu sırada herhangi bir outbound bağlantı denemesi (packet capture ile) sıfır olmalı.
- Model dosyaları ilk kurulumda açıkça ayrı bir "indirme" adımıyla gelmeli, süreç arka planda sessizce network'e çıkmamalı.

**Identity/diarization regresyonu:**
- Orijinal fatal-bug klibi (tek TTS sesi) yeni sherpa-onnx pipeline'ından geçirilsin: sonuç **tek küme** olmalı, 2 veya 5 değil. Bu geçmeden hiçbir UI çalışması "tamamlandı" sayılmamalı.
- Sentetik iki-konuşmacı overlap segmenti (aynı anda konuşma) verilsin: sistem ya baskın konuşmacıyı seçmeli ya da açık "overlap/belirsiz" bayrağı koymalı, sessizce yanlış kişiye atamamalı.
- Aynı enrolled profil, farklı simüle mikrofon/gürültü koşullarında iki ayrı sentetik toplantıda görünsün: false-accept ve false-reject oranı ölçülmeli, sadece "full utterance recognition works" tek örnekle yetinilmemeli.
- Enrolled olmayan yeni bir ses profili tanıtılsın: sistem bunu mevcut profillerden birine zorla eşlemek yerine yeni/bilinmeyen kimlik olarak açmalı (margin'in düşük konuşmacı sayısında yanlış birleştirmeye yol açmadığını kanıtlar).

## Eksik kalırsa yanıltıcı MVP olur

- **Corrections'ın kalıcılığı ve geriye etkisi tanımlı değil**: Kullanıcı bir etiketi düzelttiğinde bu sadece o transcript'te mi kalır, yoksa profil eşleştirmesini de mi etkiler (online öğrenme var mı yok mu)? Tanımsız bırakılırsa kullanıcı "düzelttim ama hep aynı hatayı tekrar görüyorum" der.
- **Import**: farklı sample rate/format/kanal sayısına sahip geçmiş ses dosyaları test edilmeden "import" özelliği iddia edilmemeli.
- **Search**: finalize sonrası transcript'lerin indekslenmesi (konuşmacıya göre, kelimeye göre) olmadan "search" özelliği demo'da çalışır ama gerçek kullanımda (yüzlerce toplantı) yavaş/eksik kalır — bu ölçekte test edilmeli.
- **İzin iptali UX'i**: Mikrofon veya ekran kaydı izni toplantı ortasında kullanıcı tarafından iptal edilirse (System Settings'ten), CLI'da sessizce crash olan davranış SwiftUI'da kullanıcıya görünür, kurtarılabilir bir hata olarak sunulmalı — yoksa "tam kullanılabilir uygulama" iddiası sahadaki ilk gerçek kesintide çöker.
