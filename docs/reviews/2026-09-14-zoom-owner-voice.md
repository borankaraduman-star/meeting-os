# Zoom kaydında yerel konuşmanın kaybolması — 14 Eylül 2026

Kullanıcı diğer MacBook'ta Zoom mikrofonu açıkken konuştuğu bölümlerin
transkripte alınmadığını bildirdi. Etkilenen toplantı ve kullanılan giriş
aygıtı henüz belirtilmedi; gerçek kaydın kök nedeni kesinleştirilmedi.

## Doğrulanan kod hatası ve düzeltme

Bulut transkripti beş dakikalık mikrofon parçasını sistem sesiyle karşılaştırıyor,
ses şiddeti zarflarının korelasyonu 0.8'i aşarsa parçanın tamamını transkripsiyon
öncesinde `echo` olarak atlıyordu. Bu ölçüm, kısa bir yerel konuşma olmadığını
kanıtlamaz.

Yerel sentetik tekrarda 300 saniyenin çoğu yankı, 120–122 saniyeleri ise yalnız
mikrofon sesiydi; bu aralıkta sistem sesi tamamen sıfırdı. Korelasyon 0.85266
olduğu için eski kod yerel konuşmayı da atladı. İki regresyon testi eski kodda
mikrofon satırlarının eksik olması nedeniyle başarısız oldu.

Düzeltme yalnız korelasyona dayalı toplu eleme işlemini kaldırır. Sessiz parçalar
ve mikrofon kapısı tarafından hariç tutulan aralıklar elenmeye devam eder.
Transkript üzerindeki mevcut yankı işaretleme işlemi korunur. Yankı yoğun
kayıtlarda daha fazla ses transkribe edilebilir ve bulut kullanım maliyeti artabilir.

Yarım kalmış bir iş devam ederken yalnız eski ücretsiz `{"skipped":"echo"}`
mikrofon kontrol noktaları yeniden değerlendirilir. Ücretli sistem transkripti,
sessizlik ve mikrofon kapısı kontrol noktaları korunur. Tamamlanmış toplantılar
bu değişiklikle kendiliğinden yeniden işlenmez veya değiştirilmez.

## Gerçek cihazlarda görülenler ve sınır

Ekip sunucusu salt okunur sorgulandı. Diğer iki cihazın son durum raporları
14 Eylül tarihli olsa da uygulama sürümleri 1.2.73 ve son tamamlanan toplantıları
11 Eylül tarihli. Güncel sorunlu toplantının hangisi olduğu bilinmiyor.
`v1.2.73` kaynak etiketi de aynı toplu yankı elemesini içeriyor; Zoom'un sessiz
durumunu izleyen `MicGate.swift` o sürümde henüz yok. Bu yüzden o sürümde Zoom'u
açmak bu sonradan uygulanan ses elemesini devre dışı bırakmıyor.

`THP6729HT2` cihazının 22 dakika 47 saniyelik 11 Eylül raporunda mikrofon ve
sistem için 114'er parça, sıfır kayıt hatası ve bir atlanmış ses parçası var.
Bu, mikrofon verisi bulunduğunu gösterir; konuşmanın o kanala ulaştığını veya
kullanıcının sorununun bu elemeden kaynaklandığını tek başına kanıtlamaz.
Paylaşılan raporda ham ses ve kanal bazında transkript bulunmuyor.

Diğer MacBook'a doğrudan çalışma erişimi bulunmadı. Düzeltmeyi o cihazda kurmak
ve etkilenen kaydın saklanan mikrofon sesinden konuşmayı kurtarmak için cihaz ve
toplantı eşleştirmesi gerekiyor. Kaydedilmemiş ses metinden geri üretilemez.

## Doğrulama

- Regresyon: 300 saniyelik yankıya karışan kısa yerel ses transkripte ulaşır.
- Eski ücretsiz yankı atlamasından devam etmek mikrofon satırlarını geri getirir;
  ücretli sistem satırları bire bir korunur.
- Bulut sonlandırma ve mikrofon kapısı dahil odaklı 77 test başarılı.
- Genel Python takımı: 1319 test, 2 atlama, başarılı. Bu koşuda projenin
  `MEETING_OS_TEST_IGNORE_PRESSURE=1` ayarı yalnız test komutuna uygulandı;
  uygulamanın bellek korumaları değiştirilmedi. Önceki genel koşu gerçek
  macOS bellek baskısında 7 başarısızlık ve 33 hata vermişti. Sonraki salt okunur
  ölçüm normal basınç gösterdi; eski kodda iki temsili işçi testi de geçti.
- Genel test günlüğünde bir `ResourceWarning` vardı; sonuç yine başarılıydı.
- Testlerde yalnız sentetik ses ve sahte dış transkripsiyon istemcisi kullanıldı;
  gerçek toplantı sesi kaydedilmedi veya yeni bir servise yüklenmedi.
