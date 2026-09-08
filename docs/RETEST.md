# Yeniden test sonuçları

## Geçenler

- 31 otomatik test yeniden geçti.
- Gerçek cihazla 20 ve 35 saniyelik kayıt alındı: mikrofon mono, sistem stereo,
  ikisi de 48 kHz. Temiz kapanış, sıfır yarım WAV, korunmuş kaynak zamanları.
- Açık Türkçe FLEURS örneği uygulamadan oynatıldı; sistem sesinden transkript üretildi.
- 35 saniyelik gerçek kayıtta canlı metin → kuyruk boşaltma → final metin akışı
  tamamlandı. En yüksek gözlenen canlı gecikme 5,10 sn; final işleme 8,41 sn.
- Üç saatlik hızlandırılmış parça birleştirme ve kaydedicinin stdout bağlantısı
  kesildikten sonra kendi günlüğünden toparlanması yeniden geçti.
- Kalıcı kimlik: temiz 24/24; gürültüde yanlış kişi ataması 0, isimsiz bırakma 13.
- Dört gerçek sesin oluşturulmuş sıralı testinde 12/12 bölüm doğru gruba atandı.

## Açık kalanlar ve kalite kusuru

Mac uygulamasının kendi mikrofon/sistem sesi izin adımı hâlâ bekliyor. Arayüzden
kayıt denendi ve izin beklerken iptal doğru çalıştı. Gerçek cihaz kayıtları,
komut satırının mevcut izinleriyle yapıldı; uygulamanın izni değiştirilmedi.

“Meşhed” yer adı yanlış yazıldı. Sayıların rakamla yazılması da katı WER hesabını
etkiliyor. İşleyen pipeline, hatasız transkript anlamına gelmiyor. Mikrofon
kanalında gerçek kareler alındı fakat kontrollü bir kişinin mikrofon konuşması
anlaşılırlık testine tabi tutulmadı. Uzun süreli cihaz kaydı, Bluetooth, doğal söz
kesme ve 3–5 gerçek toplantı henüz doğrulanmadı.

Ses kayıtları ve test DB’leri yalnızca yerel MeetingOS test önbelleğinde kaldı;
bu rapor mikrofon transkriptini veya ses vektörlerini içermez. Ayrıntılı sayısal
kanıt: RETEST.json. Uygulama kodunda bu test turunda değişiklik yapılmadı.
