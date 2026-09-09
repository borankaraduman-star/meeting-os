# Meeting OS — ekip rehberi

## Ne yapar

- Zoom (ya da başka) toplantısını Mac’inizde kaydeder: mikrofonunuz ve karşı taraf ayrı iki ses akışı.
- Kayıt bitince sesi OpenRouter’a gönderir, Türkçe yazıya çevirir ve konuşanları ayırır.
- Bir kez adlandırdığınız kişiyi ses profilinden sonraki toplantılarda kendiliğinden tanır.
- Transkriptten özet, kararlar, riskler, açık sorular ve görevleri kaynak alıntısıyla çıkarır.
- Hiçbir şeyi kendiliğinden kimseye göndermez: bütün dışa aktarımlar dosya olarak kaydedilir.

## Gizlilik — ne nerede kalır

- **Ses kayıtları ve transkriptler Mac’inizde kalır** (`~/Library/Application Support/MeetingOS/`). Bulutta saklanmaz.
- **OpenRouter’a giden iki şey var:** (1) yazıya çevrilmek üzere ses parçaları (Opus 32 kbps, saatte ≈14 MB), (2) özet/karar/görev analizi için transkriptin ilgili bölümleri (varsayılan `openai/gpt-4.1-mini`). Analizi istemiyorsanız Özet sekmesinde çalıştırmayın; transkript tek başına tamamlanır.
- **Ses profilleri Mac’inizden çıkmaz.** Kişi tanıma bu Mac’te yapılır; profiller yalnız kişinin kendi kararıyla ve ileride eklenecek bir dışa aktarma ile paylaşılabilir. Bugün böyle bir yol yok.
- **Teşhis raporları sayı içerir, metin değil:** süre, parça sayısı, ücret, hata satırı, konuşmacı sayısı. Transkript metni yalnız Ayarlar → Güncelleme ve raporlar → “Raporlara transkript metnini de ekle” açıksa girer (varsayılan kapalı).
- Ekran kareleri saklanmaz; ekran kaydı izni yalnız sistem sesini almak için gerekir.
- Toplantıyı silerseniz sesi, transkripti, özeti, görevleri ve o toplantının raporu birlikte silinir.

## Kurulum (bir kez, ≈30–60 dk)

Ön koşullar: Apple Silicon Mac (M1 ve sonrası), macOS 15+, Xcode Command Line Tools, GitHub deposuna davet.

```sh
git clone -b v0.1 https://github.com/borankaraduman-star/meeting-os.git ~/meeting-os
sh ~/meeting-os/scripts/install.sh
```

Betik gerekli araçları (Homebrew, python3.12, ffmpeg, cmake) eksikse kurar, Python ortamını ve modelleri hazırlar, uygulamayı derler, **adınızı** ve **OpenRouter API anahtarınızı** sorar, sonunda kurulum denetimi yapar. Tekrar tekrar çalıştırılabilir; Zoom’un kapalı olması gerekmez, `sudo` ile çalıştırmayın.

İki şey elle gerekebilir:

1. **Kod imzalama sertifikası.** Uygulama macOS izinlerini koruyabilmek için sabit bir imzayla derlenir. Betik sertifika bulamazsa ne yapacağınızı yazar: Anahtar Zinciri Erişimi → Sertifika Yardımcısı → Sertifika Oluştur… (Ad: Meeting OS · Kimlik türü: Kendinden imzalı kök · Sertifika türü: Kod İmzalama), sonra betiği tekrar çalıştırın.
2. **OpenRouter anahtarı.** <https://openrouter.ai/keys> adresinden kendi anahtarınızı oluşturun. Betiğe verirseniz Anahtar Zinciri’ne kaydedilir; ilk bulut işleminde macOS “Meeting OS anahtar zincirine erişmek istiyor” diye bir kez sorabilir — **Her Zaman İzin Ver** deyin. Anahtarı betiğe vermezseniz uygulama ilk kullanımda sorar.

## İlk gün

1. `Meeting OS.command` dosyasını çift tıklayın (kurulan uygulama: `build/Meeting OS.app`).
2. Açılış ekranında **adınızı** yazın. Mikrofon kaydınız bu adla etiketlenir ve “Bana ait” görev filtresi bu adı kullanır. Sonradan: Ayarlar (⌘,) → Genel → Adınız.
3. İlk kayıtta macOS **Mikrofon** ve **Ekran ve Sistem Sesi Kaydı** izinlerini isteyecek; ikisini de verin. İzin değişikliğinden sonra uygulamayı yeniden açın. Eksik izin Ayarlar → **Kurulum durumu** kartında kırmızı görünür ve oradan tek tıkla istenir.
4. **⌃⌥R** her yerden kaydı başlatır ve bitirir (Zoom öndeyken de). ⌃⌥M önemli anı işaretler. Kulaklık kullanın: hoparlör sesi mikrofona kaçarsa metin ikizlenir.
5. Kayıt bitince transkript, özet ve görevler birkaç dakikada kendiliğinden gelir. **Kontrol** sekmesinde konuşanlara bir kez adını verin — sonraki toplantılarda aynı ses kendiliğinden tanınır. Bu, aracın en çok işe yarayan tek adımı.

## İlk hafta kontrol listesi

- [ ] En az üç toplantı kaydedin; her birinin Kontrol kuyruğunu boşaltın (isimsiz konuşmacı, isim onayı, sahipsiz görev).
- [ ] Kendi sesinizin ve sık görüştüğünüz 3–5 kişinin adı bir kez verilmiş olsun.
- [ ] **Görevlerim → Bana ait** listesinin gerçekten sizin sözlerinizi gösterdiğini doğrulayın; sahibi yanlışsa Düzenle ile düzeltin.
- [ ] Bir kez **Gün sonu özeti…** ve bir kez **Beklediklerim** çıktısı alın; işinize yaramıyorsa söyleyin.
- [ ] Ayarlar → **Sözlük ve sesler**: sık geçen ürün/proje/kişi adlarını yazın; yazım hataları belirgin biçimde azalır. Ekip klasörü verildiyse sözlük ekipçe ortaklaşır.
- [ ] Ayarlar → **Depolama**: ses ≈2 GB/saat yer kaplar; “Eski toplantıların sesi” seçeneğini (varsayılan 30 gün) kendinize göre ayarlayın.
- [ ] Bir haftalık **maliyeti** Ayarlar → Güncelleme ve raporlar → Bulut maliyeti kartından görün.

## Bir şey çalışmazsa

1. **Ayarlar (⌘,) → Kurulum durumu**: izinler, OpenRouter anahtarı, sözlük, sürüm ve rapor klasörü tek listede. Kırmızı madde olmadan kayıt/güncelleme çalışmaz.
2. **Güncelleyin:** kenar çubuğundaki “Güncelle ve yeniden başlat”, ya da terminalden `sh ~/meeting-os/scripts/update.sh`. Kurulum bozulduysa `sh ~/meeting-os/scripts/install.sh` yeniden çalıştırılabilir.
3. Hâlâ olmuyorsa Boran’a şunu gönderin (sırayla, elinizde ne varsa):
   - Kenar çubuğu → **Tanılama raporu kaydet** ile kaydettiğiniz JSON (toplantı içeriği yoktur, yalnız sürüm/bellek/disk sayıları).
   - `~/Library/Application Support/MeetingOS/last-job.log` (son işin günlüğü).
   - Kurulum sırasında hata aldıysanız `~/meeting-os/installation.log`.
   - Ekip klasörü ayarlıysa toplantı raporunuz zaten `<ekip klasörü>/reports/<mac-adı>/` altındadır; yalnız hangi toplantı olduğunu söylemeniz yeter.

## Maliyet

Yazıya çevirme ≈ **$0,10/saat** (MAI-Transcribe 2). Özet/görev analizi 40 dakikalık bir toplantı için ≈1 cent. Ödemeyi kendi OpenRouter hesabınız yapar; sessiz ve yankı olan parçalar hiç yüklenmez. Gerçek harcama: Ayarlar → Güncelleme ve raporlar → **Bulut maliyeti**.

## Ekip klasörü (isteğe bağlı)

Ayarlar → Sözlük ve sesler → **Ekip klasörü**: ortak bir klasör (Dropbox, Drive, paylaşılan disk) seçerseniz proje sözlüğü ekipçe ortaklaşır ve teşhis raporlarınız oraya da yazılır. Sözlükte yerel kaydınız her zaman önceliklidir; ekip dosyası yalnız sizde olmayan terimleri ekler. Toplantı içeriği, ses ve ses profilleri bu klasöre **girmez**.
