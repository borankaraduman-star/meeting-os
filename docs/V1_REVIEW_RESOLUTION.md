# Claude Code incelemesi — V1

Claude Code, mevcut Max aboneliğiyle Sonnet üzerinde yalnızca dar kod/dizayn bağlamını inceledi. Gerçek toplantı metni veya ses verilmedi. API anahtarları devre dışı; araçlar ve MCP kapalı. Codex uyguladı; Claude aynı işi tekrar implement etmedi.

İlk mimari inceleme: kaynak eskimesi, atomik görev/analiz yazımı, taslağa aşırı güven ve eski dışa aktarımlar. Kaynak hash kontrolü ve SQLite BEGIN IMMEDIATE eklendi; düzenleme geçmişi ve görev durumu korunuyor. Taslaklar inceleme gerektirir ve kendiliğinden gönderilmez. Handoff sürüm/zaman/hash içerir ve eski görev dışa aktarımını reddeder. Tam eşleşen alıntıyı gevşetme önerisi uygulanmadı; olmayan alıntıyı kabul etmek istemiyoruz.

Kod checkpoint bulguları:
1. Konuşmacı adı karşılaştırmasında Türkçe normalizasyon eksikliği: düzeltildi.
2. Parça dışındaki alıntıların doğrulanması: izin verilen segmentler sınırlandı.
3. Hafıza yanıtlarında kesilmiş bağlam yerine tam kaynakla doğrulama: artık aynı kesilmiş metin doğrulanıyor.
4. MCP arama çıktısının diğer listelerden farklı olması: protokol zorunluluğu değil, ancak tutarlılık için items/next_offset biçimine getirildi.
5. JSON dışında model önsözü: keyfi metin içinden ilk JSON'u çekme önerisi uygulanmadı. Yanlış/hatalı yapı sessizce kabul edilmiyor; model yeniden deneniyor, yine doğrulanmazsa kayıt yazılmıyor. Model çıktısı ayrıca gerçek yerel testlerde ölçülüyor.

Codex ek kontrolü: aynı kaynak üzerinde yeni analizde kaldırılan görevlerin de eski işaretlenmesi; yanıt hazırlanırken kaynak değişikliğinin reddi; görev taslağı hazırlanırken eşzamanlı düzenleme kontrolü.

İkinci dar checkpoint (uzun toplantı / taslak yaşam döngüsü):
- Eşzamanlı iki hazırlığın çift taslak kaydetmesi: işlem kilidi içindeki ikinci kontrol eklendi; yarış simülasyonu testi kırmızıdan yeşile geçti.
- Kısa “PRD yaz” başlığının iptal kontrolünde atlanması: kısa anlamlı terimler de dahil edildi; regresyon testi geçti.
- Tamamlanmış/kaldırılmış görevin handoff edilmesi: CLI/bridge engeli ve UI devre dışı bırakma eklendi; test geçti.

Gerçek yerel model testleri ek bulgular buldu: serbest JSON biçimi eksik kanıt üretiyordu (Outlines üretim kısıtı eklendi); taslakta uydurma takvim tarihi vardı (sahip/tarih uygulamadan ekleniyor, sayısal kaynak kontrolü var); özet birleştirmede alıntı yeniden yazılıyordu (birleştirme yalnızca mevcut alıntı/segment çiftlerini üretebilir). Kurgu testlerde bu hatalar giderildi; genel anlamsal doğruluk garantisi verilmez.

Son taslak regresyonları: yarım JSON yeniden denenir; alan uzunlukları ve rakam üretimi sınırlandırılır; kaynak sayıları uygulamanın alıntısında korunur. Karakter sınırında kesilen cümle parçası son çıktıya konmaz. Bu testler de geçti.
