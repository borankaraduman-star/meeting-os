# Meeting OS — ekip rehberi

## Ne yapar

- Zoom (ya da başka) toplantısını Mac’inizde kaydeder: mikrofonunuz ve karşı taraf ayrı iki ses akışı.
- Kayıt bitince sesi OpenRouter’a gönderir, Türkçe yazıya çevirir ve konuşanları ayırır.
- Bir kez adlandırdığınız kişiyi ses profilinden sonraki toplantılarda kendiliğinden tanır.
- Transkriptten özet, kararlar, riskler, açık sorular ve görevleri kaynak alıntısıyla çıkarır.
- **Kendiliğinden dışarı çıkan iki şey var:** (1) ses ve transkript OpenRouter’a gider, (2) sayısal teşhis raporu ekip klasörüne yazılır (rapor paylaşımı varsayılan olarak açık). Bunların dışında hiçbir şey gönderilmez; özet, görev ve transkript dışa aktarımları dosya olarak kaydedilir. Tek istisna: bir görevi **Hatırlatıcılar’a ekle** derseniz görev başlığı, sahibi ve toplantı adı Apple Hatırlatıcılar’a (iCloud’la eşitlenir) yazılır; toplantıyı silince tamamlanmamış olanlar kaldırılır.

## Gizlilik — ne nerede kalır

- **Ses kayıtları ve transkriptler Mac’inizde kalır** (`~/Library/Application Support/MeetingOS/`). Ses hiçbir yerde saklanmaz; transkript metni yalnız “Raporlara transkript metnini de ekle” açıksa rapora (iCloud/ekip klasörü) girer. OpenRouter isteklerinde sağlayıcıdan veri saklamaması istenir (`data_collection: deny`); hesabınızın kendi gizlilik ayarını da <https://openrouter.ai/settings/privacy> adresinden kontrol edin.
- **OpenRouter’a giden iki şey var:** (1) yazıya çevrilmek üzere ses parçaları (Opus 32 kbps, saatte ≈14 MB), (2) özet/karar/görev analizi. Analiz her toplantıdan sonra **kendiliğinden başlar** ve transkriptin tamamını, konuşmacı adlarıyla birlikte, ≈2800 token’lık gruplar hâlinde `openai/gpt-4.1-mini` modeline gönderir — “ilgili bölümler” değil, hepsi. Bunu istemiyorsanız tek yol Ayarlar → Sistem → Yazıya çevirme → **Yerel model**: o zaman ses de metin de OpenRouter’a gitmez.
- **Ses profilleri Mac’inizden çıkmaz.** Kişi tanıma bu Mac’te yapılır; profiller yalnız kişinin kendi kararıyla ve ileride eklenecek bir dışa aktarma ile paylaşılabilir. Bugün böyle bir yol yok.
- **Teşhis raporları sayısaldır:** süre, parça sayısı, ücret, hata satırı, konuşmacı sayısı ve puanlar. Toplantı başlığı ve konuşmacılara verdiğiniz adlar 1.2.37’den itibaren yalnız “Raporlara transkript metnini de ekle” açıkken rapora girer (kapalıyken konuşmacılar S1, S2… olarak geçer). Transkript metninin kendisi yalnız Ayarlar → Sistem → **Gelişmiş** → “Raporlara transkript metnini de ekle (varsayılan kapalı)” açıksa girer. Rapor yazma varsayılan olarak **açıktır**; kapatmak için Ayarlar → Sistem → **Gelişmiş** → “Her toplantıdan sonra teşhis raporunu paylaşılan klasöre yaz” anahtarını kapatın.
- Ekran kareleri saklanmaz; ekran kaydı izni yalnız sistem sesini almak için gerekir.
- Toplantıyı silerseniz sesi, transkripti, özeti, görevleri, geçici yeniden-deneme kopyaları, o toplantının raporu (önceki rapor klasörlerindeki dahil) ve Hatırlatıcılar’daki tamamlanmamış aktarımları birlikte silinir; veritabanı silinen sayfaları sıfırlar.

## Asla paylaşmayın

- **OpenRouter API anahtarınız.** Faturayı sizin hesabınız öder; anahtarı gören herkes sizin adınıza harcama yapabilir. Yanlışlıkla bir yere yapıştırdıysanız <https://openrouter.ai/keys> adresinden hemen iptal edip yenisini oluşturun.
- **`build/signing-identity.json` ve “Meeting OS Local” özel anahtarı.** Bunlar bu Mac’e özeldir; başka bir Mac’te işe yaramaz, paylaşınca yalnız risk doğurur.
- **`~/Library/Application Support/MeetingOS/` içeriği** — ses kayıtları, transkriptler, `meeting-os.sqlite`. Teşhis için hiçbir zaman gerekmez; sorun bildirirken tanılama raporu ve günlük dosyaları yeter (aşağıya bakın).

## Kurulum (bir kez, ≈30–60 dk)

Ön koşullar: Apple Silicon Mac (M1 ve sonrası), macOS 15+, yönetici (admin) hesabı, kurulu Xcode Command Line Tools. Kurulu değilse önce Terminal’de `xcode-select --install` çalıştırın, açılan pencerede kurulumu bitirin (≈10 dk), sonra aşağıdaki komutlara geçin. Depo şu an herkese açık; klonlamak için GitHub girişi gerekmez.

```sh
git clone -b v0.1 https://github.com/borankaraduman-star/meeting-os.git ~/meeting-os
sh ~/meeting-os/scripts/install.sh
```

Betik gerekli araçları (Homebrew, python3.12, ffmpeg, cmake) eksikse kurar, Python ortamını ve modelleri hazırlar, uygulamayı derler, **adınızı** ve **OpenRouter API anahtarınızı** sorar, sonunda kurulum denetimi yapar. Tekrar tekrar çalıştırılabilir; Zoom’un kapalı olması gerekmez, `sudo` ile çalıştırmayın. **Meeting OS açıksa önce tamamen kapatın** (⌘Q): açık uygulamanın üzerine yazılmaz, kurulum “Application is running” diyip durur.

İki şey elle gerekebilir:

1. **Kod imzalama sertifikası.** Uygulama macOS izinlerini koruyabilmek için sabit bir imzayla derlenir. Mac’te hiç sertifika yoksa betik kendisi “Meeting OS Local” adıyla bir tane oluşturur (bu adımda macOS bir kez pencerede parola sorar). **İmzalama anahtarına kalıcı izin verme adımı ise sertifikanın nereden geldiğine bakmaksızın her kurulumda çalışır** — betiğin oluşturduğu “Meeting OS Local” sertifikasında da, Xcode’dan gelen “Apple Development” sertifikasında da, `MEETING_OS_SIGNING_IDENTITY` ile sabitlenmiş bir kimlikte de. İzin, giriş (login) anahtar zincirindeki **bütün imzalama anahtarlarına** uygulanır; tek bir sertifikaya daraltılamaz. Bunun için terminalde bir kez Mac parolanız sorulur (parola saklanmaz). Bu adım atlanırsa her derleme ve her güncellemede “codesign anahtar zincirinizdeki anahtarı kullanmak istiyor” penceresi çıkar ve **Her Zaman İzin Ver tutmaz**; o durumda bir kez `sh ~/meeting-os/scripts/fix-signing-prompts.sh` çalıştırın ve Mac parolanızı girin. (Adım başarılı olunca `~/Library/Application Support/MeetingOS/signing-partition.ok` dosyası yazılır; `update.sh` ve Öz-test buna bakar, bu dosya yoksa güncelleme başlamadan durup aynı komutu söyler.) Kurulum kendi kendine çalışmaz: masadan kalkmayın. Betik sertifikayı kendiliğinden oluşturamazsa ne yapacağınızı yazar: Anahtar Zinciri Erişimi → Sertifika Yardımcısı → Sertifika Oluştur… (Ad: Meeting OS · Kimlik türü: Kendinden imzalı kök · Sertifika türü: Kod İmzalama), sonra betiği tekrar çalıştırın.

   Bu pencerelerden birini **İptal** ederseniz sertifika yarım kalmış olabilir. O zaman Anahtar Zinciri Erişimi’ni açın, **giriş (login)** anahtar zincirinde “Meeting OS Local” sertifikasını **ve** onun altındaki özel anahtarı silin, sonra `sh ~/meeting-os/scripts/install.sh` komutunu yeniden çalıştırın. Silmeden tekrar çalıştırırsanız Mac’te iki sertifika olur ve kurulum “birden fazla sertifika var” diyerek durur.
2. **OpenRouter anahtarı.** <https://openrouter.ai/keys> adresinden kendi anahtarınızı oluşturun. Betiğe verirseniz iki yere yazılır: uygulamanın kendi klasöründeki yalnız size açık dosyaya (`openrouter.key`, 0600) ve yedek olarak Anahtar Zinciri’ne. Uygulama ve bütün işler o dosyayı okur, bu yüzden **yeni bir kurulumda Anahtar Zinciri penceresi hiç çıkmaz**. Anahtar dosyası olmayan (daha önce kurulmuş) bir Mac’te macOS “Meeting OS anahtar zincirine erişmek istiyor” diye **bir kez** sorar — Ayarlar → Sistem ilk açıldığında ya da ilk bulut işinde — orada **Her Zaman İzin Ver** deyin; uygulama o tek okumadan sonra anahtarı aynı dosyaya alır ve bir daha Anahtar Zinciri’ne dokunmaz (her güncelleme uygulamanın imzasını değiştirdiği için macOS aksi hâlde her seferinde yeniden soruyordu). Anahtarı betiğe vermezseniz Ayarlar → Sistem → **OpenRouter anahtarı** satırından girebilirsiniz.

## İlk gün

1. `Meeting OS.command` dosyasını çift tıklayın (kurulan uygulama: `build/Meeting OS.app`). İlk açılışta macOS **bildirim izni** ister; **İzin ver** deyin — Zoom toplantı penceresi açılınca gelen “Kaydı başlat” hatırlatması ve iş bitince gelen “toplantı hazır” bildirimi bununla çalışır.
2. Açılış ekranında **adınızı** yazın ve **⏎** ile onaylayın. Ad ancak Enter’a bastığınızda (ya da açılış ekranından çıktığınızda) kaydedilir; onaylamadan uygulamayı kapatırsanız mikrofon kaydınız varsayılan **“Boran”** adıyla etiketlenir ve “Bana ait” görev filtresi sizin değil Boran’ın görevlerini gösterir. Sonradan düzeltmek için: Ayarlar (⌘,) → Genel → **Sizin adınız**.
3. **İzinleri ilk kayıttan önce verin.** Ayarlar (⌘,) → **Sistem → Kurulum durumu** kartında mikrofon ve **Ekran kaydı (toplantı sesi)** satırlarındaki **İzin iste** düğmesine basın (reddedilmiş bir izinde düğme **Ayarları aç** olur). Ekran kaydı iznini verdikten sonra uygulamayı kapatıp yeniden açın; macOS bu izni ancak yeniden açılışta tanır. İzinsiz başlatılan kayıt sessizce boş biter: sonunda “Bu denemede ses parçası alınmadı” yazar ve o toplantıdan geriye hiçbir şey kalmaz.
4. **⌃⌥R** her yerden kaydı başlatır ve bitirir (Zoom öndeyken de). ⌃⌥M önemli anı işaretler. Kulaklık kullanın: hoparlör sesi mikrofona kaçarsa metin ikizlenir.
5. Kayıt bitince transkript, özet ve görevler birkaç dakikada kendiliğinden gelir. Transkriptin üstündeki **İsimler** kartında her sese bir kez adını verin (yazıp ⏎ ya da öneriyi onaylayın) — sonraki toplantılarda aynı ses kendiliğinden tanınır. Bu, aracın en çok işe yarayan tek adımı.

## İlk hafta kontrol listesi

- [ ] En az üç toplantı kaydedin; her birinde İsimler kartını boşaltın ve Kontrol sekmesindeki şüpheli yerlere (sahipsiz görev, çakışan konuşma) bir kez bakın.
- [ ] Kendi sesinizin ve sık görüştüğünüz 3–5 kişinin adı bir kez verilmiş olsun. Profil, İsimler kartındaki ya da bir paragraftaki **Düzelt → “Adlandır ve öğren”** ile kaydedilir; kişi başına bir kez yeter. Kayıtlı profilleri Ayarlar → **Sesler ve sözlük → Kaydedilmiş sesler** altında görürsünüz.
- [ ] **Görevlerim → Bana ait** listesinin gerçekten sizin sözlerinizi gösterdiğini doğrulayın; sahibi yanlışsa Düzenle ile düzeltin.
- [ ] Bir kez **Gün sonu özeti…** ve bir kez **Beklediklerim** çıktısı alın; işinize yaramıyorsa söyleyin.
- [ ] Ayarlar → **Sesler ve sözlük → Sözlük**: sık geçen ürün/proje/kişi adlarını her satıra bir tane yazıp **Sözlüğü kaydet** deyin; yazım hataları belirgin biçimde azalır. Ekip klasörü verildiyse proje sözlüğü ekipçe ortaklaşır.
- [ ] Ayarlar → **Sistem → Depolama**: kayıt sırasında ses geçici olarak ≈2 GB/saat yer kaplar, sıkıştırıldıktan sonra ≈150 MB/saat kalır (ölçülen bir toplantı: 41 dakika = 82 MB). Toplam kullanım ve en büyük toplantılar bu karttadır. Diskte birkaç GB boş tutun; “Eski toplantıların sesi” seçeneğini Ayarlar → Sistem → **Gelişmiş** altında kendinize göre ayarlayın. Disk dolduğu için durmuş bir kayıtta hiçbir şey kaybolmaz, ama yazıya çevrilebilmesi için önce birkaç GB yer açmanız gerekir.
- [ ] Bir haftalık **maliyeti** Ayarlar → Sistem → **Bulut maliyeti** kartından görün.

## Bir şey çalışmazsa

1. **Ayarlar (⌘,) → Sistem → Kurulum durumu**: izinler, OpenRouter anahtarı, sözlük, sürüm ve rapor klasörü tek listede. Kırmızı madde olmadan kayıt/güncelleme çalışmaz.
2. **Güncelleyin:** kenar çubuğundaki “Güncelle ve yeniden başlat”, ya da terminalden `sh ~/meeting-os/scripts/update.sh`. Kurulum bozulduysa `sh ~/meeting-os/scripts/install.sh` yeniden çalıştırılabilir.
3. Hâlâ olmuyorsa Boran’a şunu gönderin (sırayla, elinizde ne varsa):
   - Kenar çubuğunda Ayarlar’ın yanındaki **⋯ → Tanılama raporu kaydet** ile kaydettiğiniz JSON (toplantı içeriği yoktur, yalnız sürüm/bellek/disk sayıları).
   - Ayarlar → Sistem → **Gelişmiş** → **Öz-test** düğmesine basıp sonucun ekran görüntüsü.
   - `~/Library/Application Support/MeetingOS/last-job.log` (son işin günlüğü; 1.2.33’ten itibaren toplantı metni içermez, ama göndermeden önce açıp bakın).
   - Güncelleme yarıda kaldıysa `~/Library/Application Support/MeetingOS/update.log` ve `update-status.json`.
   - Kurulum sırasında hata aldıysanız `~/meeting-os/installation.log`.
   - Ekip klasörü ayarlıysa toplantı raporunuz zaten `<ekip klasörü>/reports/<mac-adı>/` altındadır; yalnız hangi toplantı olduğunu söylemeniz yeter.

## Maliyet

Yazıya çevirme ≈ **$0,10/saat** (MAI-Transcribe 2). Özet/görev analizi 40 dakikalık bir toplantı için ≈1 cent. Ödemeyi kendi OpenRouter hesabınız yapar; sessiz ve yankı olan parçalar hiç yüklenmez. Gerçek harcama: Ayarlar → Sistem → **Bulut maliyeti**.

## Ekip klasörü (isteğe bağlı)

Ayarlar → Sesler ve sözlük → **Ekip klasörü**: ortak bir klasör (Dropbox, Drive, paylaşılan disk) seçerseniz proje sözlüğü ekipçe ortaklaşır ve teşhis raporlarınız oraya da yazılır. Sözlükte yerel kaydınız her zaman önceliklidir; ekip dosyası yalnız sizde olmayan terimleri ekler. Ses ve ses profilleri bu klasöre **girmez**; ama teşhis raporları girer — ve rapor toplantı başlığını ve konuşmacılara verdiğiniz adları içerir (“Raporlara transkript metnini de ekle” açıksa transkriptin tamamını da). Klasörü gören herkes bunları görür: `<ekip klasörü>/reports/<mac-adı>/`.
