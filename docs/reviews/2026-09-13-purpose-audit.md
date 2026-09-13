# Meeting OS: amaç ve uygulama denetimi — 13 Eylül 2026

Başlangıç: `aa40789`, sürüm 1.2.87. İnceleme, Claude Code devir notları,
güncel sürüm kararları, Python/Swift kodu ve geçici veritabanlarında yeniden
üretilen hatalar üzerinden yapıldı. Eski yerel model planları güncel ürün
kararı olarak alınmadı.

## Ürünün amacı

Toplantıyı yavaşlatmadan ve ses kaybına yol açmadan kayıt almak; Türkçe metni,
konuşmacıları, özeti ve görevleri kaynaklarıyla birlikte kullanılabilir hale
getirmek; kullanıcının açık düzeltmelerini koruyup sonraki kullanımlardan
ölçülü biçimde öğrenmek. Ekip arkadaşının terminal kullanması gerekmemeli.

Bu yüzden öncelik, yeni ekran ve model eklemekten önce kayıt güvenliği,
kullanıcı kararlarının kalıcılığı, doğru öğrenme sinyali ve gereksiz arka plan
işlerinin azaltılmasıdır. Transkript ve analiz bulut kararını, mevcut model ve
ses kimliği eşiklerini, yalnız birebir otomatik kelime düzeltmesini ve kaldırılmış
yüzen panel kararını koruduk.

## Bu turdaki düzeltmeler

| Sorun | Etki | Değişiklik ve kanıt |
|---|---|---|
| Özet birleştirme önceden yeni madde kimliği veriyordu; kaydetme eski maddeyle eşleştirmeyi atlıyordu. | Aynı içeriğin başka kelimelerle yazılması düzeltmeyi veya kaldırma kararını kaybediyordu. | Kaydetme sırasında önceki analizle yeniden eşleştirme; genişlemiş, olgusu değişmiş veya belirsiz içerikte kararı otomatik taşımama. `test_learning_preservation.py`. |
| Görevin yeniden yazılması yeni görev oluşturuyordu. | Onaylanan tarih, düzeltilmiş sahip ve görev durumu geride kalıyor; aynı iş iki kez görünebiliyordu. | Tek ve kaynakla desteklenen eşleşmede yalnız açık kullanıcı kararlarını taşıma, önceki satırı geçmişte koruyarak emekliye ayırma. |
| Aynı başlık ve alıntıya dayanan farklı sahipli görevlerin kimliği çakışıyordu. | İki görevden biri diğerinin üzerine yazılıyordu. | Çakışmada sahip ve tarih ile kararlı ayrım; önceki kullanıcı kararının doğru göreve bağlı kalması ve sıralamadan bağımsız sonuç için regresyon testleri. |
| Taşınan görev geçmişi yeni insan düzeltmesi sayılıyordu. | Tek hata yeniden analizlerle beş hataya dönüşüp gereksiz inceleme kurallarını açabiliyordu. | `carried_from` satırlarını öğrenme sayımından çıkarma. |
| Bellek önbelleği diğer SQLite bağlantılarının yazdıklarını fark etmiyordu. | Analiz sürerken yapılan düzeltmeye rağmen eski kaynakla analiz kaydedilebiliyordu. | `PRAGMA data_version` ile dış bağlantı değişikliklerini de izleme. |
| Ses sıkıştırma, veritabanı yeni yolu kaydetmeden WAV'ı siliyordu. | Veritabanı yazımı başarısız olduğunda oynatma yolu olmayan dosyaya işaret ediyordu. | Önce FLAC doğrulama ve veritabanına kaydetme, sonra özgün WAV temizliği; eski kesintiler için doğrulanmış kardeş FLAC yolunu kurtarma. `test_archive_reliability.py`. |
| Bakımın kayıt algısı rapor paylaşımına bağlıydı ve uzun arşiv turu yeni kayda bırakmıyordu. | Paylaşım kapalıyken veya yeni kayıt başladığında arşiv işi toplantıyla kaynak yarışına giriyordu. | Paylaşımdan bağımsız özel kayıt nabzı; toplantılar ve ses blokları arasında duraklama kontrolü. |
| Boyut sınırı nedeniyle atılan ekip raporları her eşitlemede tekrar indiriliyordu. | Gereksiz ağ ve disk işi. | İndirmeden önce aynı sayı/boyut sınırına göre seçim; değişen ve yanlışlıkla kaybolan dosyaları yeniden alma. Beş dosyalı 45 baytlık testte ilk tur iki indirme, sonraki değişmeyen tur sıfır indirme. `test_team_report_cache.py`. |
| Analiz, yedek model cevap verse de seçilen modelin adını kaydediyordu. | Kalite ve süre değerlendirmesi yanlış modele atfediliyordu. | Her analiz kapsamındaki cevap veren modelleri ayrı izleme; paralel karışık sonuçları ve kullanım verisi gelmeyen cevapları doğru kaydetme. Tanılama yalnız doğrulanmış model kimliklerini paylaşır. `test_analysis_provenance.py`. |
| Kayıt ve arka plan işi ortak iptal/hata alanlarını kullanıyordu. | Yeni kayıt önceki iptali başarısızlık gibi gösterebiliyor; önceki işin iptali kayıt hatasını gizleyebiliyordu. | Her süreç için ayrı sonuç durumu, dört bağımsız yaşam döngüsü testi. `JobLifecycleTests.swift`. |

README'nin başlangıcındaki güncel Mac arayüzüyle çelişen yerel model yönergeleri
düzeltildi; yeni ekip üyeleri terminalsiz paket rehberine yönlendirildi.
Analiz ilerlemesindeki `2/1` gibi toplamı aşan sayılar da düzeltildi.

Eşleştirme bilinçli olarak temkinlidir: anlamı değişmiş veya birden fazla
önceki maddeye uyabilecek yeniden yazımlar kullanıcı kararını otomatik
devralmaz. Önceki düzeltme geçmişi korunur. Eski kimlik çakışmasıyla üzerine
yazılmış bir görev ancak sonraki analiz onu yeniden çıkarırsa geri gelir;
bu tur gerçek toplantılara toplu yeniden analiz uygulanmadı.

## Doğrulama

Başlangıç Python takımı: 1.260 test, başarılı; iki mevcut atlama.
Başlangıç Swift takımı: 348 test, başarılı. Yeni hatalar önce başarısız olan
geçici veritabanı, sentetik ses, sahte sağlayıcı veya yerel HTTP testleriyle
gösterildi. Gerçek toplantı metni API'ye gönderilmedi.

Birleşik Python takımı: **1.308 test başarılı, iki mevcut atlama**. Testler
`MEETING_OS_TEST_IGNORE_PRESSURE=1` ile çalıştırıldı; bu yalnız test ortamındaki
bellek baskısı kapısını atlar. Çalışma klasöründeki önbellek okumaları beklediği
için son koşuda ayrı geçici Python önbelleği kullanıldı. Mevcut bağımlılıkların
deprecation/ResourceWarning mesajları sürüyor; test hatası oluşmadı.

Birleşik Swift takımı: **352 test, sıfır hata**. Son koşu ayrı geçici derleme
diziniyle tamamlandı. Değişiklikler ayrıca bağımsız ajan incelemesinden geçti;
`git diff --check` temiz.

Asıl proje ve kurulu uygulamanın çalışma kaynağı:
`/Users/boran/Library/Application Support/MeetingOS/repo-v0.1`.
İnceleme dalı: `codex/meeting-os-purpose-audit`.

## Sonraki kabul çalışmaları

- Gerçek Zoom görüşmesinde mikrofon kapısı, uyku/uyanma ve pencere gizliliği.
- İkinci Mac'te temiz paket kurulumu, davet ve sürüm yükseltme. 1.2.72–1.2.86
  paketlerinin kendini güncelleyememe sorunu için bir defalık elle kurulum hâlâ
  gereklidir; bugünkü değişiklikler bunu uzaktan düzelttiği iddiasını taşımaz.
- Altı gerçek boyutlu senaryonun üç tekrarlı ücretli kalite kıyası. Model ve
  eşik değişikliği ancak bu ölçüm ve gerçek toplantı doğrulamasıyla yapılmalı.
- Developer ID ve noterleme, ayrı dağıtım çalışmasıdır.

Bu maddeler bu turda canlı doğrulanmış kabul edilmemelidir.
