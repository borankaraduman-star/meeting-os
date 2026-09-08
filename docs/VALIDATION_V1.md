# V1 doğrulama — 8 Eylül 2026

M4 / 16 GB / macOS üzerinde çalıştırıldı. Kod/test: Codex; mimari ve iki dar kod
incelemesi: Claude Code Sonnet, mevcut Max oturumu. Gerçek özel toplantı içeriği
Claude'a verilmedi. Varsayılan uygulama modelleri yereldir.

| Kontrol | Gözlenen sonuç | Sınır |
|---|---|---|
| Otomatik regresyon | 62 test, tamamı geçti | Model doğruluğu yerine işlev, protokol, kayıt ve veri bütünlüğü |
| Yerel analiz modeli | Üç kurgu senaryo geçti, 17,2 / 18,0 / 29,8 sn | Doğal toplantı precision/recall değildir |
| Görev sahipleri | Sprint: Boran, Ece, belirsiz; 3 görev | Küçük ve açık taahhütlü test |
| İptal/öneri | İptal edilen migration ve kabul edilmemiş demo görev olmadı | Tüm doğal konuşma çeşitlerini kapsamaz |
| Gömülü talimat | Saldırı metni yürütülmedi; yalnız gerçek raporlama taahhüdü çıkarıldı | Modelin zaten araç/mesaj yetkisi yok |
| Uzun toplantı parçaları | 6 kaynaklı not → 3 not; daha sonraki iptal görevi kaldırdı; 11,1 sn | Kurulmuş parçalar, doğal uzun toplantı değil |
| STT bağımlılık regresyonu | 22,2 sn açık FLEURS sesi, 6,62 sn işleme | Tek kayıt; yeni accuracy tahmini değil |
| Analiz → taslak → yanıt → yeniden okuma | İzole SQLite + gerçek yerel modelde geçti, 90,5 sn | Kurgu metin; uzunluk sınırındaki son cümle koruması ayrıca uygulandı/test edildi |
| MCP | Gerçek CLI alt işleminde initialize, tools/list ve okuma geçti | Harici AI istemcisine bağlantı kurulmadı |
| Mac arayüzü | Özet/görevler, yerel taslak, taslak düzenleme, dosya export ve kaynaklı hafıza yanıtı geçti | Açıkça etiketlenmiş kurgu örnek |

Ham kanıtlar: `TEST_RESULTS_V1.txt`, `ANALYSIS_BENCHMARK.json`,
`ASSISTANT_SMOKE.json`, `LONG_ANALYSIS_SMOKE.json`, `STT_V1_SMOKE.json`,
`MCP_SMOKE.json`, `UI_V1_SMOKE.json`. GUI'den kaydedilen kurgu görev paketi `DEMO_TASK.md`.

## Testlerin bulduğu ve düzeltilen hatalar

Serbest üretim eksik alıntı/yanlış JSON veriyordu. Outlines üretim sırasında
JSON şeklini sınırlar; gerçek alıntı ayrıca doğrulanır. Birleştirme aşamasında
alıntı yeniden yazımı görüldü; artık yalnızca mevcut alıntı/segment çiftleri
seçilebilir. Başarısız analiz kalıcı başarılı sonuç gibi kaydedilmez.

Taslak modelinin “yarın” sözünden uydurma bir tarih ürettiği görüldü. Sahip ve
tarih modelden alınmıyor; doğrulanmış görevden uygulama ekliyor. Kaynakta
olmayan sayısal içerik reddediliyor ve tekrar deneniyor. Bu koruma tüm anlamsal
uydurmaları tespit etmez. Taslak ve özet hâlâ insan incelemesi gerektirir.

Claude'un son incelemesinde bulunan çift taslak yarışı, kısa başlıkların iptal
kontrolünde atlanması ve tamamlanmış görevin handoff edilmesi için önce hatayı
üreten test yazıldı, sonra düzeltildi. Detay: `V1_REVIEW_RESOLUTION.md`.

## Ses doğrulamasının durumu

Önceki gerçek cihaz testinde mikrofon mono / sistem stereo ayrı 48 kHz kayıt,
20/35 saniye temiz durdurma ve canlı→nihai akışı geçti (`RETEST.md`). GUI'nin
kendi macOS izin akışı kullanıcı onayı bekliyor; aşılmadı. İlk 12 açık Türkçe
okuma kaydında large WER %8,2 / turbo %11,9 sonucu `VALIDATION.md` içinde.
Bunlar doğal toplantı ölçümü değildir.

3–5 gerçek toplantı, uzun duvar saati kaydı, akustik echo, üst üste konuşma,
Bluetooth/uyku dönüşü ve kişi isimlerinin bütün koşullarda doğruluğu doğrulanmış
sayılmaz. `BENCHMARK.md` ses ve insan değerlendirmeli özet/görev metrikleri için
çalıştırılabilir harness'i açıklar. İnsan referansı olmadan bu skorlar uydurulmadı.

## Maliyet ve yerellik

STT, konuşmacı modelleri, analiz, taslak ve hafıza yanıtı bu Mac'te çalışır.
Hugging Face/ücretsiz paket indirmeleri kurulum sırasında yapıldı; ücretli
inference API'si eklenmedi. MCP örneği otomatik bağlanmadı. Görev paketini
başka istemciye elle verirseniz veriyi o istemciye vermiş olursunuz.
