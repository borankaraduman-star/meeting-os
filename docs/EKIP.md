# Meeting OS — ekip rehberi

> Teknik olmayan ekip arkadaşı için kısa yol: [docs/BASLANGIC.md](BASLANGIC.md) (paketi indir, Uygulamalar'a sürükle, aç). Bu belge ayrıntılı sürümdür.

## Ne yapar

- Zoom (ya da başka) toplantısını Mac’inizde kaydeder: mikrofonunuz ve karşı taraf ayrı iki ses akışı.
- Kayıt bitince sesi OpenRouter’a gönderir, Türkçe yazıya çevirir ve konuşanları ayırır.
- Bir kez adlandırdığınız kişiyi ses profilinden sonraki toplantılarda kendiliğinden tanır.
- Transkriptten özet, kararlar, riskler, açık sorular ve görevleri kaynak alıntısıyla çıkarır.
- **Kendiliğinden dışarı çıkanların tam listesi:**
  1. **OpenRouter’a:** kayıt bitince ses parçaları (yazıya çevirme) ve ardından transkriptin tamamı (özet/görev analizi).
  2. **Paylaşılan rapor klasörüne** (iCloud Drive’daki `MeetingOS-Reports/` ya da ayarlanmışsa ekip klasörü): her toplantıdan sonra o toplantının sayısal raporu, **saatte bir** bu Mac’in nabzı (`heartbeat.json` — disk, bellek, termal, son hata satırları), ve **kayıt sürerken dakikada bir** kayıt nabzı (`recording-heartbeat.json` — geçen süre, parça sayısı, boş disk). Üçü de Ayarlar → Sistem → **Gelişmiş** → “Her toplantıdan sonra teşhis raporunu paylaşılan klasöre yaz” anahtarıyla birlikte kapanır (varsayılan **açık**). Dosya yollarındaki kullanıcı adınız raporlara girmeden önce `/Users/…` olarak kısaltılır.
  3. **Ekip klasörüne** (yalnız Ayarlar → Sesler ve sözlük → **Ekip klasörü**'nde bir klasör seçtiyseniz): öğrettiğiniz kelimeler (`team-words.jsonl`) ve kaydettiğiniz ses profilleri (`profiles/<mac-adı>.jsonl` — kişi adı + ses vektörü). İkisi de varsayılan **açık**, ikisi de aynı bölümdeki anahtarlarla kapanır. **Ses kaydı, transkript, toplantı adı ve toplantı numarası bu dosyalara hiç girmez.**
  4. **GitHub’a:** altı saatte bir sürüm kontrolü (yeni bir sürüm var mı diye sorar; içerik göndermez).
  2. **Paylaşılan rapor klasörüne** (iCloud Drive’daki `MeetingOS-Reports/` ya da ayarlanmışsa ekip klasörü): her toplantıdan sonra o toplantının sayısal raporu, **saatte bir** bu Mac’in nabzı (`heartbeat.json` — disk, bellek, termal, son hata satırları ve **hata günlüğü özeti**: son 24 saatte türüne göre kaç hata, kaç çökme, son birkaç iletinin kısaltılmış hâli), ve **kayıt sürerken dakikada bir** kayıt nabzı (`recording-heartbeat.json` — geçen süre, parça sayısı, boş disk). Üçü de Ayarlar → Sistem → **Gelişmiş** → “Her toplantıdan sonra teşhis raporunu paylaşılan klasöre yaz” anahtarıyla birlikte kapanır (varsayılan **açık**). Dosya yollarındaki kullanıcı adınız raporlara girmeden önce `/Users/…` olarak kısaltılır.
  3. **GitHub’a:** altı saatte bir sürüm kontrolü (yeni bir sürüm var mı diye sorar; içerik göndermez).

  Bunların dışında hiçbir şey gönderilmez; özet, görev ve transkript dışa aktarımları dosya olarak kaydedilir. Tek istisna: bir görevi **Hatırlatıcılar’a ekle** derseniz görev başlığı, sahibi ve toplantı adı Apple Hatırlatıcılar’a (iCloud’la eşitlenir) yazılır; toplantıyı silince tamamlanmamış olanlar kaldırılır.

## Gizlilik — ne nerede kalır

- **Ses kayıtları ve transkriptler Mac’inizde kalır** (`~/Library/Application Support/MeetingOS/`). Ses hiçbir yerde saklanmaz; transkript metni yalnız “Raporlara transkript metnini de ekle” açıksa rapora (iCloud/ekip klasörü) girer. OpenRouter isteklerinde sağlayıcıdan veri saklamaması istenir (`data_collection: deny`); hesabınızın kendi gizlilik ayarını da <https://openrouter.ai/settings/privacy> adresinden kontrol edin.
- **OpenRouter’a giden iki şey var:** (1) yazıya çevrilmek üzere ses parçaları (Opus 32 kbps, saatte ≈14 MB), (2) özet/karar/görev analizi. Analiz her toplantıdan sonra **kendiliğinden başlar** ve transkriptin tamamını, konuşmacı adları ve mikrofon satırlarında Ayarlar’daki kendi adınızla birlikte (1.2.47’den beri; görev sahipliği bundan çıkar), ≈2800 token’lık gruplar hâlinde `openai/gpt-4.1-mini` modeline gönderir — “ilgili bölümler” değil, hepsi. Bunu istemiyorsanız tek yol Ayarlar → Sistem → Yazıya çevirme → **Yerel model**: o zaman ses de metin de OpenRouter’a gitmez.
- **Ses profilleri yalnız ekip klasörüne çıkar, oraya da ses kaydı olarak değil.** Ekip klasörü seçilmemişse hiçbir yere gitmez: kişi tanıma bu Mac’te yapılır. Seçilmişse aşağıdaki “ekip bilgisi” başlığına bakın.
- **Teşhis raporları sayısaldır:** süre, parça sayısı, ücret, hata satırı, konuşmacı sayısı ve puanlar. Toplantı başlığı ve konuşmacılara verdiğiniz adlar 1.2.37’den itibaren yalnız “Raporlara transkript metnini de ekle” açıkken rapora girer (kapalıyken konuşmacılar S1, S2… olarak geçer). Transkript metninin kendisi yalnız Ayarlar → Sistem → **Gelişmiş** → “Raporlara transkript metnini de ekle (varsayılan kapalı)” açıksa girer. Rapor yazma varsayılan olarak **açıktır**; kapatmak için Ayarlar → Sistem → **Gelişmiş** → “Her toplantıdan sonra teşhis raporunu paylaşılan klasöre yaz” anahtarını kapatın.
- **Hata günlüğü (1.2.63+) bu Mac’te kalır.** Bir şey ters gittiğinde `~/Library/Application Support/MeetingOS/errors.jsonl` dosyasına **tek satır** düşer (yalnız size açık, 0600; 1 MB’ı geçince `errors.jsonl.1` olarak döner). Satırda **yalnız şunlar vardır:** zaman, tür (`ui` arayüz · `job` işlem · `cloud` bulut · `capture` kayıt · `update` güncelleme · `crash` çökme), en fazla 300 karakterlik kısa bir ileti, uygulama sürümü ve birkaç küçük alan (komut adı, çıkış kodu, toplantının **karması** — numarası ya da adı değil). **Transkript metni, konuşulan hiçbir söz, konuşmacı adı, toplantı başlığı ve ses asla girmez;** dosya yollarındaki kullanıcı adınız `/Users/…` olarak kısaltılır. Aynı hata on dakika içinde tekrarlarsa tek satır sayılır.
- **Çökme raporları:** macOS bir çökmede zaten `~/Library/Logs/DiagnosticReports/` altına rapor yazar. Uygulama bunlardan yalnız kendi süreçlerine ait olanları (`MeetingOS-*.ips`, `MeetingCapture-*.ips`) açar ve günlüğe **özetini** koyar: süreç adı, sürüm, hata türü/sinyali, sonlanma nedeni ve **yalnız kendi kodumuza ait en fazla 8 çağrı adı** (adres yok). Raporun kendisi hiçbir yere kopyalanmaz.
- **Ne görürsünüz, nasıl silersiniz:** Ayarlar (⌘,) → **Sistem → Hatalar** kartında son 5 kayıt durur; **Hata günlüğünü temizle** hepsini siler. Günlük özeti, rapor paylaşımı açıkken nabızla birlikte paylaşılan klasöre de gider (yukarıdaki liste, madde 2) — kapatmak için aynı anahtar: Ayarlar → Sistem → Gelişmiş → “Her toplantıdan sonra teşhis raporunu paylaşılan klasöre yaz”.
- **Metin saklama süresi ayarlanabilir:** Ayarlar → Sistem → Gelişmiş → **Eski toplantıların yazısı** (varsayılan “silinmesin”) bir süre dolunca toplantının transkriptini, özetini ve görevlerini bu Mac’ten tümüyle siler — teşhis raporunun ekip klasöründeki kopyası da onunla gider.
- Ekran kareleri saklanmaz; ekran kaydı izni yalnız sistem sesini almak için gerekir.

### Ekip bilgisi buluta gider (1.2.67+) — ayarlanacak bir şey yok

Ekip bilgi tabanı artık bir klasöre bağlı değil. Uygulamayı kurduğunuz anda bu Mac ekibin sunucusuna bağlanır;
**kimse bir klasör seçmez, bir adres yapıştırmaz, bir düğmeye basmaz.** Ekip kimliği OpenRouter anahtarınızdan
türetilir (anahtarın kendisi asla dışarı çıkmaz, yalnız geri döndürülemez özeti kullanılır), yani **aynı anahtarla
kurulan Mac'ler aynı ekiptir.**

- **Paylaşılan şey klasör döneminin aynısı:** öğretilen kelimeler, ses profilleri (kişi adı + ses vektörü),
  proje sözlüğü, teşhis raporları ve redakte edilmiş hata günlüğü. **Ses kaydı, transkript metni, toplantı adı ve
  toplantı numarası hiçbir zaman gitmez.** Rapor ve hata günlüğü, “Her toplantıdan sonra teşhis raporunu paylaşılan
  klasöre yaz” anahtarı kapalıysa gönderilmez; kelime ve profil anahtarları da eskisi gibi çalışır.
- **Kim görür:** yalnız aynı ekip belirtecine sahip Mac'ler. Sunucu ekip başına ve Mac başına dosya saklar; her Mac
  yalnız **kendi** dosyalarını yükler, ötekilerinkini indirir. Kimse kimsenin dosyasının üzerine yazamaz.
- **Sunucu kapalıyken hiçbir şey kaybolmaz.** Uygulama her şeyi önce yerel aynaya
  (`~/Library/Application Support/MeetingOS/team/`) yazar ve oradan okur; bağlantı gelince eşitlenir. Kurulum
  durumu kartındaki **Ekip bilgi tabanı** satırı son eşitlemeyi ya da “bulut şu an erişilemiyor” bilgisini söyler.

#### Ekibe katılmak: bir bağlantı, bir tıklama (1.2.68+)

**Terminal gerekmez.** Ekipteki herhangi bir Mac davet üretir, davet gönderilir, alan kişi tıklar. Hepsi bu.

**Gönderen (Boran ya da ekipten biri):**

1. Ayarlar (⌘,) → **Sesler ve sözlük → Ekip**.
2. **Davet bağlantısını kopyala**. Ekip arkadaşınızın kendi OpenRouter anahtarı yoksa önce
   **“OpenRouter anahtarımı da ekle (ekip arkadaşı anahtar girmez)”** kutusunu işaretleyin — o zaman o kişinin
   bulut kullanımı **sizin** hesabınızdan ödenir.
3. Bağlantıyı Slack, WhatsApp ya da e-postayla gönderin. Bağlantıyı kabul etmeyen bir uygulama varsa
   **Davet dosyasını kaydet…** ile aynı daveti `Meeting OS Daveti.meetingos-invite` dosyası olarak kaydedip
   dosyayı gönderin.

**Alan kişi:**

- Bağlantıya **tıklar** (`meetingos://join…`): Meeting OS açılır, “Ekibe katıldınız · ekip `a1b2c3` · 3 Mac”
  penceresi çıkar, ekibin sözlüğü, öğretilen kelimeleri ve ses profilleri arka planda iner.
- Ya da davet dosyasını **çift tıklar** — aynı sonuç.
- Ya da bağlantıyı kopyalayıp uygulamanın **açılış ekranındaki** “Davet bağlantısını buraya yapıştırın”
  alanına yapıştırıp **Katıl** der. Uygulama zaten açıksa: Ayarlar → Sesler ve sözlük → Ekip →
  **Davet yapıştır…**.

Davette anahtar da varsa o kişi OpenRouter anahtarı adımını **hiç görmez**. **Zaten anahtarı olan bir Mac'te
davetteki anahtar kullanılmaz:** var olan anahtarın üzerine hiçbir zaman yazılmaz.

> **Davet bir paroladır.** Ekip belirtecini (ve varsa anahtarı) taşır: **depoya, bir kanala, bir bilete
> yazılmaz** — doğrudan o kişiye gönderilir. Yanlış kişiye gittiyse OpenRouter anahtarını
> <https://openrouter.ai/keys> adresinden iptal edin; ekip belirteci anahtardan türediği için yeni anahtarla
> ekip kimliği de yenilenir.

**Gelişmiş (terminal):** aynı işler komut satırından da yapılır —
`.venv/bin/python -m meeting_os team invite [--with-key]` daveti basar (bağlantı, dosya içeriği ve eski kurulum
satırı birlikte), `meeting_os team join <bağlantı | dosya yolu | belirteç>` katılır, `meeting_os team status`
durumu, `meeting_os team sync` elle eşitlemeyi verir. Hiç kurulu olmayan bir Mac'te kurulum satırı hâlâ
çalışır: `MEETING_OS_TEAM=<belirteç> sh ~/meeting-os/scripts/install.sh`.
- **Ekip klasörü hâlâ çalışıyor.** Ayarlar → Sesler ve sözlük → **Ekip → Gelişmiş → Ekip klasörü seç…**'de bir
  klasör seçiliyse o kazanır (aynı ağdaki bir NAS'ı yeğleyen ekipler için); bulut yalnız hiçbir klasör
  seçilmemişken devreye girer.
- **Ne paylaştığınızı kart söyler.** Ekip kartının ilk satırı her zaman **etkin hedefi** yazar: “Ekip bulutu ·
  `a1b2c3` · 3 Mac · son eşitleme 14:20”, “Ekip klasörü · ~/Ekip” ya da “Kapalı”. Sözlük, kelime ve profil
  anahtarları hedef ne olursa olsun çalışır; yalnız hiçbir hedef yokken kapalıdır (1.2.68'e kadar bulut
  açıkken de kapalı görünüyorlardı).

### Ekip bilgisi — ekip klasörüne ne yazılır, nasıl kapatılır

Ekip klasörü **ortak bilgi tabanıdır**: herkesin adlandırması ve kelime düzeltmesi herkeste birikir. 3–5 kişi kullanınca aynı ürün adını üç kez düzeltmek, aynı kişiyi üç kez adlandırmak gerekmez. Klasöre yalnız iki dosya yazılır ve **ikisinde de ses kaydı, transkript metni, toplantı adı ya da toplantı numarası yoktur**:

| Dosya | İçindeki tek şey | Anahtar (varsayılan) |
| --- | --- | --- |
| `team-words.jsonl` | öğretilen kelime, doğru yazımı, öğreten Mac’in adı, tarih | “Öğretilen kelimeleri ekiple paylaş” (**açık**) |
| `profiles/<mac-adı>.jsonl` | kişi adı, gömme modelinin adı, **ses vektörü** (birim vektör), örneğin kaç saniye olduğu, tarih | “Ses profillerimi ekiple paylaş” (**açık**) |

- **Ses vektörü ses değildir:** iki sesin aynı kişiye ait olup olmadığını söyleyen sayı dizisidir; geri çalınamaz, konuşmaya çevrilemez. Yine de bir kişinin adıyla birlikte durur — ekip klasörünü gören herkes o kişinin adını görür.
- **Kapatmak:** Ayarlar (⌘,) → **Sesler ve sözlük** → Ekip klasörü altındaki iki anahtar. Kapattığınız anda bu Mac o dosyaya ne yazar ne okur. Tümüyle bırakmak için ekip klasörünü **Kaldır** deyin.
- **Tek tek kapatmak:** bir ekip arkadaşınızın öğrettiği kelime size uymuyorsa Ayarlar → Sesler ve sözlük → Öğrenilen kelimeler listesinde o satırdaki **Kapat** düğmesi onu yalnız sizde susturur (onun dosyasına dokunulmaz). Bir kişiyi tanımak istemiyorsanız kişi kartından **Profili sil**: ekipten gelen örnekleri de siler ve o adın yeniden gelmesini engeller.
- **Kimin yazımı geçerli:** kendi öğrettiğiniz yazım her zaman önceliklidir. İki ekip arkadaşı aynı kelimeyi farklı öğretmişse en yeni olan uygulanır; ikisi de listede, öğreten Mac’in adıyla görünür.
- **İlk açılışta hepsi gider:** ekip klasörünü ilk seçtiğinizde o güne kadar öğrettiğiniz bütün kelimeler ve kaydettiğiniz bütün ses profilleri tek seferde yayımlanır — özellikten sonra öğrendikleriniz değil, elinizdekilerin tamamı. Aynı şey ikinci kez yayımlanmaz.
- **Ne kadarı ekipten geldi:** Ayarlar → Sesler ve sözlük → Öğrenilen kelimeler başlığının yanında “ekipten N profil, M kelime” yazar; kişi kartında da “… , N ekipten” görürsünüz.
- Toplantı içeriğinin nereye gittiği değişmedi: OpenRouter ve (açıksa) teşhis raporları. Ekip bilgisi bunların dışındadır.
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

1. **Kod imzalama sertifikası.** Uygulama macOS izinlerini koruyabilmek için sabit bir imzayla derlenir. Mac’te hiç sertifika yoksa betik kendisi “Meeting OS Local” adıyla bir tane oluşturur (bu adımda macOS bir kez pencerede parola sorar). **İmzalama anahtarına kalıcı izin verme adımı ise sertifikanın nereden geldiğine bakmaksızın her kurulumda çalışır** — betiğin oluşturduğu “Meeting OS Local” sertifikasında da, Xcode’dan gelen “Apple Development” sertifikasında da, `MEETING_OS_SIGNING_IDENTITY` ile sabitlenmiş bir kimlikte de. İzin, giriş (login) anahtar zincirindeki **bütün imzalama anahtarlarına** uygulanır; tek bir sertifikaya daraltılamaz. Bunun için terminalde bir kez Mac parolanız sorulur (parola saklanmaz). Bu adım atlanırsa her derleme ve her güncellemede “codesign anahtar zincirinizdeki anahtarı kullanmak istiyor” penceresi çıkar ve **Her Zaman İzin Ver tutmaz**; o durumda bir kez `sh ~/meeting-os/scripts/fix-signing-prompts.sh` çalıştırın ve Mac parolanızı girin. **1.2.41 ve öncesinde bu komutu çalıştırmış olsanız bile dosya yazılmamıştır; bir kez daha çalıştırın** — o sürümlerde izin veriliyordu ama işaret dosyası oluşmuyordu, dolayısıyla güncelleme yine başlamadan duruyor. (Adım başarılı olunca `~/Library/Application Support/MeetingOS/signing-partition.ok` dosyası yazılır; `update.sh` ve Öz-test buna bakar, bu dosya yoksa güncelleme **depoya dokunmadan, birleştirmeden önce** durup aynı komutu söyler.) Kurulum kendi kendine çalışmaz: masadan kalkmayın. Betik sertifikayı kendiliğinden oluşturamazsa ne yapacağınızı yazar: Anahtar Zinciri Erişimi → Sertifika Yardımcısı → Sertifika Oluştur… (Ad: Meeting OS · Kimlik türü: Kendinden imzalı kök · Sertifika türü: Kod İmzalama), sonra betiği tekrar çalıştırın.

   Bu pencerelerden birini **İptal** ederseniz sertifika yarım kalmış olabilir. O zaman Anahtar Zinciri Erişimi’ni açın, **giriş (login)** anahtar zincirinde “Meeting OS Local” sertifikasını **ve** onun altındaki özel anahtarı silin, sonra `sh ~/meeting-os/scripts/install.sh` komutunu yeniden çalıştırın. Silmeden tekrar çalıştırırsanız Mac’te iki sertifika olur ve kurulum “birden fazla sertifika var” diyerek durur.
2. **OpenRouter anahtarı.** <https://openrouter.ai/keys> adresinden kendi anahtarınızı oluşturun. Betiğe verirseniz iki yere yazılır: uygulamanın kendi klasöründeki yalnız size açık dosyaya (`openrouter.key`, 0600) ve yedek olarak Anahtar Zinciri’ne. Uygulama ve bütün işler o dosyayı okur, bu yüzden **yeni bir kurulumda Anahtar Zinciri penceresi hiç çıkmaz**. Anahtar dosyası olmayan (daha önce kurulmuş) bir Mac’te macOS “Meeting OS anahtar zincirine erişmek istiyor” diye **bir kez** sorar — Ayarlar → Sistem ilk açıldığında ya da ilk bulut işinde — orada **Her Zaman İzin Ver** deyin; uygulama o tek okumadan sonra anahtarı aynı dosyaya alır ve bir daha Anahtar Zinciri’ne dokunmaz (her güncelleme uygulamanın imzasını değiştirdiği için macOS aksi hâlde her seferinde yeniden soruyordu). Anahtarı betiğe vermezseniz Ayarlar → Sistem → **OpenRouter anahtarı** satırından girebilirsiniz.

## İlk gün

1. `Meeting OS.command` dosyasını çift tıklayın (kurulan uygulama: `build/Meeting OS.app`). İlk açılışta macOS **bildirim izni** ister; **İzin ver** deyin — Zoom toplantı penceresi açılınca gelen “Kaydı başlat” hatırlatması ve iş bitince gelen “toplantı hazır” bildirimi bununla çalışır.
2. Açılış ekranında **adınızı** yazın ve **⏎** ile onaylayın. **1.2.44’e geçtiğinizde adınız bir kez daha sorulur** (o sürüme kadar kimse yazmadan da bir ad kayıtlı sayılıyordu; artık yalnız sizin yazdığınız ad geçerli). Bir kez daha yazıp ⏎ deyin. Ad ancak Enter’a bastığınızda (ya da açılış ekranından çıktığınızda) kaydedilir; onaylamadan uygulamayı kapatırsanız mikrofon kaydınız kimseye ait olmayan **“Ben”** etiketiyle geçer ve “Bana ait” görev filtresi boş kalır. Sonradan yazabilirsiniz: Ayarlar (⌘,) → Genel → **Sizin adınız** — adı kaydettiğinizde daha önce kaydedilmiş toplantılardaki mikrofon paragrafları da yeni adla yeniden etiketlenir (o toplantıların özeti “güncel değil” olarak işaretlenir, çünkü kimin ne söylediği değişmiştir).
3. **İzinleri ilk kayıttan önce verin.** Ayarlar (⌘,) → **Sistem → Kurulum durumu** kartında mikrofon ve **Ekran kaydı (toplantı sesi)** satırlarındaki **İzin iste** düğmesine basın (reddedilmiş bir izinde düğme **Ayarları aç** olur). Ekran kaydı iznini verdikten sonra uygulamayı kapatıp yeniden açın; macOS bu izni ancak yeniden açılışta tanır. İzinsiz başlatılan kayıt sessizce boş biter: sonunda “Bu denemede ses parçası alınmadı” yazar ve o toplantıdan geriye hiçbir şey kalmaz.
4. **⌃⌥R** her yerden kaydı başlatır ve bitirir (Zoom öndeyken de). ⌃⌥M önemli anı işaretler. Kulaklık kullanın: hoparlör sesi mikrofona kaçarsa metin ikizlenir.
5. Kayıt bitince transkript, özet ve görevler kendiliğinden gelir — ama hemen değil: 45 dakikalık bir toplantı için kabaca **10–20 dakika**. Sırayla ses parçaları üçerli gruplar hâlinde yazıya çevrilir, sonra ses profilleri eşleştirilir, sonra analiz çalışır; kenar çubuğunun altındaki **Son durum** satırı hangi aşamada olduğunu söyler. Bu arada Mac’i kullanabilirsiniz; kapağı kapatırsanız iş durur ve Mac boşta kalınca kaldığı yerden sürer. Transkriptin üstündeki **İsimler** kartında her sese bir kez adını verin (yazıp ⏎ ya da öneriyi onaylayın) — sonraki toplantılarda aynı ses kendiliğinden tanınır. Bu, aracın en çok işe yarayan tek adımı.

## İlk hafta kontrol listesi

- [ ] En az üç toplantı kaydedin; her birinde İsimler kartını boşaltın ve Kontrol sekmesindeki şüpheli yerlere (sahipsiz görev, çakışan konuşma) bir kez bakın.
- [ ] **Kendi sesiniz için profil oluşturmanız gerekmez:** mikrofon ayrı bir ses akışıdır ve doğrudan Ayarlar → Genel → **Sizin adınız** değeriyle etiketlenir. Profil yalnız *karşı taraftaki* kişiler için gerekir; sık görüştüğünüz 3–5 kişinin adı bir kez verilmiş olsun. Profil, İsimler kartındaki ya da bir paragraftaki **Düzelt → kapsam “Bu konuşmacının tamamı” → “Adlandır”** ile kaydedilir; kişi başına bir kez yeter. Kayıtlı profilleri Ayarlar → **Sesler ve sözlük → Kaydedilmiş sesler** altında görürsünüz.
- [ ] **Görevlerim → Bana ait** listesinin gerçekten sizin sözlerinizi gösterdiğini doğrulayın; sahibi yanlışsa Düzenle ile düzeltin.
- [ ] Bir kez **Gün sonu özeti…** ve bir kez **Beklediklerim** çıktısı alın; işinize yaramıyorsa söyleyin.
- [ ] Ayarlar → **Sesler ve sözlük → Sözlük**: sık geçen ürün/proje/kişi adlarını her satıra bir tane yazıp **Sözlüğü kaydet** deyin; yazım hataları belirgin biçimde azalır. Ekip klasörü verildiyse proje sözlüğü, öğrettiğiniz kelimeler ve ses profilleri ekipçe ortaklaşır — bir kişiyi bir kişinin adlandırması herkese yeter.
- [ ] Yanlış yazılan bir ürün/kişi adını bir kez **Düzelt → “Düzelt ve öğret”** ile düzeltin (ya da Kontrol’deki **Kelime** maddesinden); o toplantının tamamı hemen düzelir, sonraki toplantılarda aynı yazım kendiliğinden düzelir; yakın yazımlar Kontrol’e öneri olarak gelir, onaylayınca düzelir ve öğrenilir. Öğrenilenler Ayarlar → **Sesler ve sözlük** altında; yanlış öğrettiyseniz **Unut** hepsini geri alır.
- [ ] Ayarlar → **Sistem → Depolama**: kayıt sırasında ses geçici olarak ≈2 GB/saat yer kaplar, sıkıştırıldıktan sonra ≈150 MB/saat kalır (ölçülen bir toplantı: 41 dakika = 82 MB). Toplam kullanım ve en büyük toplantılar bu karttadır. Diskte birkaç GB boş tutun; “Eski toplantıların sesi” seçeneğini Ayarlar → Sistem → **Gelişmiş** altında kendinize göre ayarlayın. Disk dolduğu için durmuş bir kayıtta hiçbir şey kaybolmaz, ama yazıya çevrilebilmesi için önce birkaç GB yer açmanız gerekir.
- [ ] Bir haftalık **maliyeti** Ayarlar → Sistem → **Bulut maliyeti** kartından görün.

## Bir şey çalışmazsa

1. **Ayarlar (⌘,) → Sistem → Kurulum durumu**: izinler, OpenRouter anahtarı, sözlük, sürüm ve rapor klasörü tek listede. Kırmızı madde olmadan kayıt/güncelleme çalışmaz.
2. **Güncelleyin:** kenar çubuğundaki “Güncelle ve yeniden başlat” — uygulamayı zip olarak indirip Uygulamalar’a sürüklediyseniz güncelleme de uygulamanın kendi içinden gelir: yeni sürümü indirir, doğrular ve kendini değiştirip yeniden açılır; terminale hiç gerek yoktur. Depodan kurulu bir Mac’te aynı düğme derlemeyi yapar, ya da terminalden `sh ~/meeting-os/scripts/update.sh`. Kurulum bozulduysa `sh ~/meeting-os/scripts/install.sh` yeniden çalıştırılabilir.
3. Hâlâ olmuyorsa Boran’a şunu gönderin (sırayla, elinizde ne varsa):
   - Kenar çubuğunda Ayarlar’ın yanındaki **⋯ → Tanılama raporu kaydet** (ya da Ayarlar → Sistem → Hatalar → **Tanılama raporunu dışa aktar**) ile kaydettiğiniz JSON. İçinde sürüm/bellek/disk sayıları **ve hata günlüğünüzün son 20 kaydı** (çökme özetleri dâhil) vardır; **toplantı içeriği yoktur**. Sorun bildirirken gönderilecek ilk dosya budur — bir çökme yaşadıysanız neredeyse her zaman tek başına yeter.
   - Ayarlar → Sistem → **Gelişmiş** → **Öz-test** düğmesine basıp sonucun ekran görüntüsü.
   - `~/Library/Application Support/MeetingOS/last-job.log` (son işin günlüğü; 1.2.33’ten itibaren toplantı metni içermez, ama göndermeden önce açıp bakın).
   - Güncelleme yarıda kaldıysa `~/Library/Application Support/MeetingOS/update.log` ve `update-status.json`.
   - Kurulum sırasında hata aldıysanız `~/meeting-os/installation.log`.
   - Ekip klasörü ayarlıysa toplantı raporunuz zaten `<ekip klasörü>/reports/<mac-adı>/` altındadır; yalnız hangi toplantı olduğunu söylemeniz yeter.

## Maliyet

Yazıya çevirme ≈ **$0,10/saat** (MAI-Transcribe 2). Özet/görev analizi **her çalıştığında ≈3–4 cent** (40–60 dakikalık bir toplantı, `openai/gpt-4.1-mini`; iki saatlik bir toplantı ≈ $0,08). Analiz bir toplantıda birden çok kez çalışabilir: transkript değişirse (isim verme, metin düzeltme) özet bayatlar ve yenilenirken analiz **yeniden ücretlendirilir**. Ödemeyi kendi OpenRouter hesabınız yapar; sessiz ve yankı olan parçalar hiç yüklenmez. Gerçek harcama — yazıya çevirme **ve** analiz ayrı ayrı: Ayarlar → Sistem → **Bulut maliyeti**.

## Ekip klasörü (isteğe bağlı)

Ayarlar → Sesler ve sözlük → **Ekip klasörü**: ortak bir klasör (Dropbox, Drive, paylaşılan disk) seçerseniz orası ekibin **ortak bilgi tabanı** olur — proje sözlüğü, öğretilen kelimeler ve ses profilleri (kişi adı + ses vektörü) ekipçe birikir; teşhis raporlarınız da oraya yazılır. Sözlükte ve kelimelerde yerel kaydınız her zaman önceliklidir; ekip dosyası yalnız sizde olmayanı ekler. Ses kaydı ve transkript bu klasöre **girmez** (ayrıntı: yukarıdaki “Ekip bilgisi” başlığı; kelime ve profil paylaşımı ayrı ayrı kapatılabilir). Teşhis raporları girer; içeriği ayara bağlıdır: varsayılan hâlde yalnız sayılar, puanlar, ücret, model adı ve hata satırları vardır — toplantı başlığı boş geçer ve konuşmacılar S1, S2… diye adlandırılır. Ayarlar → Sistem → **Gelişmiş** → “Raporlara transkript metnini de ekle” açıksa rapor toplantı başlığını, konuşmacılara verdiğiniz adları **ve transkriptin tamamını** taşır. Klasörü gören herkes ne varsa görür: `<ekip klasörü>/reports/<mac-adı>/`.
