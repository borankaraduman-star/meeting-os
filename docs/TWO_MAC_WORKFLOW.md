# İki Mac akışı: kullanım Mac’i ↔ geliştirme Mac’i

## Kullanım Mac’inde (günlük toplantılar)
- Uygulama açılışta ve her 6 saatte bir `git fetch` ile GitHub `v0.1` dalını kontrol eder. Yeni commit varsa kenar çubuğunda “Yeni sürüm hazır · N değişiklik” kartı ve **Güncelle ve yeniden başlat** düğmesi çıkar.
- Ayarlar → Sistem → **Gelişmiş** → “Yeni sürüm bulununca açılışta kendiliğinden güncelle (kayıt yokken)” açılırsa kayıt/iş yokken açılışta otomatik güncellenir.
- Güncelleme `scripts/update.sh` ile uygulamanın dışında koşar ve **sıra şudur: önce kapılar, sonra hedef, en sonda çalışma kopyası** — kilit (`update.lock.d`, 30 dk sonra bayat) → kayıt sürüyor mu (`recording-heartbeat.json` 3 dakikadan taze mi, `MeetingCapture` açık mı) → uygulamanın kapanmasını bekle → yerel değişiklik yok mu → `git fetch --tags --force` → **hedef: `origin/v0.1` üzerinden erişilebilen en yüksek `vX.Y.Z` etiketi** → imzalama işareti (`signing-partition.ok`) var mı → `git merge-base --is-ancestor HEAD <etiket>` ile ileri sarılabilir mi → **ancak bundan sonra** `git merge --ff-only` → gerekirse pip / kayıt yardımcısı → `build-desktop.sh` (sabitlenmiş imza kimliği, izinler korunur) → `build/installed-commit` yazılır → uygulama yeniden açılır. Reddeden her şey birleştirmeden **önce** sorulur: yoksa Mac yeni commit'te, eski uygulamayla kalır ve uygulamadaki kontrol “güncel” (behind=0) diyerek düğmeyi gizler. Sonuç `~/Library/Application Support/MeetingOS/update-status.json` ve `update.log` (1 MB'ı geçince `update.log.1` olarak döner); bir sonraki açılışta “Güncelleme tamam · a → b” görünür. Yerel değişiklik varsa güncelleme yapılmaz.
- Her transkript ve analiz sonunda toplantı raporu `iCloud Drive/MeetingOS-Reports/<mac-adı>/<tarih>_<toplantı>.json` dosyasına yazılır (Ayarlar’dan kapatılabilir). İçerik: süre, parça/ücret, yankı, konuşmacı küme/benzerlik/isim, kontrol kuyruğu sayıları, analiz sayıları, kimlik karnesi, son hata satırları (yollar maskelenir) ve `capture` bloğu (kaynak başına parça dosyası sayısı, süreden beklenen sayı, günlükteki `gap`/`error` olayları ve toplam boşluk saniyesi, birleştirilmiş `*-full.wav` boyutları). Transkript metni yalnız “metni de ekle” açıksa girer.
- Toplantıdan bağımsız nabız: `.venv/bin/python -m meeting_os reports heartbeat` (ya da köprüde `{"action":"heartbeat"}`) aynı klasöre `<mac-adı>/heartbeat.json` yazar ve her seferinde üzerine yazar. İçerik: yazılma zamanı, **kurulu uygulamanın sürümü** (`app_version` — uygulamanın kendi `CFBundleShortVersionString` değeri, deponunki değil), **deponun sürümü** (`repo_version`), **deponun commit'i** (`commit`), **son güncellemenin durumu** (`update_status`: `state`/`message`/`time`), **imzalama işareti** (`signing_partition`), toplantı sayısı ve durum dağılımı, son tamamlanan toplantı, recordings/imports/sqlite boyutları, boş disk, bellek baskısı, `pmset -g therm` CPU_Speed_Limit, yük ortalaması, son 5 hata satırı ve **ekip bilgisi sayıları** (`team_profiles`/`team_words`: ekip klasöründen alınanlar, `shared_profiles`/`shared_words`: bu Mac'in oraya koyduğu) — yalnız sayılar, ad ya da kelime değil. Rapor paylaşımı kapalıysa yazılmaz.

### Ekip bulutu (1.2.67+): iCloud artık şart değil, ekip klasörü isteğe bağlı

Ortak bilgi tabanının kökü artık kendiliğinden bulunur ve sırası şudur: **seçilmiş ekip klasörü → ekip bulutu →
iCloud**. Bir ekip klasörü seçilmemişse ve bu Mac'te bir OpenRouter anahtarı (ya da `team.token`) varsa kök,
sunucuyla eşitlenen yerel ayna olur: `~/Library/Application Support/MeetingOS/team/`. Klasör düzeni birebir aynıdır
(`team-words.jsonl`, `glossary.jsonl`, `profiles/<mac-adı>.jsonl`, `reports/<mac-adı>/…`), yani `team_knowledge`,
`glossary` ve `reports` hiç değişmedi: hepsi hâlâ bir klasöre yazıp bir klasörden okuyor.

Pratik sonuçları:

- **İkinci Mac için iCloud Drive gerekmiyor.** İki Mac'te de aynı OpenRouter anahtarı varsa profiller, kelimeler,
  sözlük ve raporlar birbirine ulaşır — iCloud kapalı olsa bile. (iCloud yalnız bulut da klasör de yoksa yedek
  olarak kalır ve yalnız gerçek veri klasörü için okunur.)
- **Ekip klasörü isteğe bağlıdır**, kaldırılmadı: seçiliyse her zaman kazanır.
- Teşhis raporları ve nabız aynanın `reports/<mac-adı>/` klasörüne yazılır ve oradan sunucuya çıkar; geliştirme
  Mac'i onları kendi aynasında görür (`reports summarize` aynı komut).
- Ağ çağrısı hiçbir zaman hızlı köprüde yapılmaz: adlandırma/öğretme kancaları arka plan geçişini tetikler,
  bloklayan eşitleme yalnız açılışta ve saatlik bakımda koşar. Sunucu düşerse hata yalnız
  `team-cloud-state.json` dosyasına ve kurulum kartına düşer; öğrenilenler yerelde durur.
- Ayrıntı ve protokol: `docs/TEAM_CLOUD.md`; kullanıcıya bakan anlatım: `docs/EKIP.md`.

### Ekip klasöründeki iki ortak dosya (1.2.62+)

Ayarlar → Sesler ve sözlük → **Ekip klasörü** doluyken sözlüğün yanında iki dosya daha ortaklaşır ve **her Mac ikisine de yazar, ikisini de okur**: `<ekip klasörü>/team-words.jsonl` (öğretilen kelimeler: `original`, `replacement`, `host`, `created`, `updated` — satır başına bir JSON nesnesi) ve `<ekip klasörü>/profiles/<mac-adı>.jsonl` (ses profilleri: `name`, `model`, `vector`, `duration`, `created`, `host`). İkisinde de **ses, transkript, toplantı adı ve toplantı numarası yoktur**; ikisi de varsayılan açıktır (`share_words`, `share_profiles`). Yazma sırası her yerde aynı: **önce yayınla, hemen ardından oku** — bir kelime öğretilir öğretilmez, bir kişi adlandırılır adlandırılmaz yayınlanır; okuma açılışta, saatlik bakım geçişinde (`storage_housekeeping`, kayıt yokken) ve her yayından hemen sonra yapılır, böylece aynı anda düzelten iki kişi bir turda buluşur.

**Geriye dönük doldurma:** yayınlama, o anki yerel durumun tamamının anahtarlanmış bir kopyasıdır — özellik açılmadan önce öğretilmiş bütün kelimeler ve kaydedilmiş bütün ses örnekleri (`team:` kaynaklı olanlar hariç) ilk yayında birlikte gider. Aynı durum ikinci kez yayınlandığında dosya değişmez (satır çoğalmaz), bu yüzden açılış ve saatlik geçiş bedava sayılır. Ayarlar → Sesler ve sözlük başlığında “ekipten N profil, M kelime” satırı ne kadarının ekipten geldiğini söyler.

Çakışma kuralları:

- **Kelimeler** `(mac-adı, kelime)` ile anahtarlanır; bir Mac yayın yaparken önce dosyayı yeniden okur ve başkasının satırını asla silmez (sözlükteki `merge_into` ile aynı mantık, geçici dosya + `rename`). Aynı kelimeyi iki Mac farklı öğretmişse **yereldeki kazanır**; iki ekip arkadaşı arasında **en yenisi** (`updated`) kazanır. Kaybeden satır Ayarlar’daki listede öğreten Mac’in adıyla yine görünür (`word_rules` → `source: "team"`, `host`, `active`). Satır bazında kapatma yereldir (`team_words.enabled`), ekip dosyasına yazılmaz. Bir Mac bir kelimeyi **unutunca** kendi satırı dosyadan çıkar ve bir sonraki okumada diğer Mac’lerde de uygulanmaz olur.
- **Profiller** içerik özetiyle (ad + model + vektör → sha256) anahtarlanır, bu yüzden aynı dosyayı iki kez okumak hiçbir şey eklemez; içe alınan örnek `provenance='team:<mac-adı>:<özet>'` ile durur. Kişi başına üst sınır 8 örnektir ve **önce yereldeki örnekler doldurur**: ekipten gelen bir örnek yerel bir örneğin üzerine asla yazmaz. Yerelde **reddedilmiş** (`rejections`) bir ad hiç alınmaz, **silinmiş** bir kişi (`team_profile_blocks`) yeniden gelmez, kimlik eşiği (`person_threshold`) değişmez — yani yerel düzeltme her zaman ekipten gelene üstündür. Her Mac yalnız **kendi** oluşturduğu örnekleri yayınlar (`team:` ile başlayan sağlama yeniden yayınlanmaz), böylece bir satırın tek sahibi olur.
- Toplantıdan bağımsız nabız: `.venv/bin/python -m meeting_os reports heartbeat` (ya da köprüde `{"action":"heartbeat"}`) aynı klasöre `<mac-adı>/heartbeat.json` yazar ve her seferinde üzerine yazar. İçerik: yazılma zamanı, **kurulu uygulamanın sürümü** (`app_version` — uygulamanın kendi `CFBundleShortVersionString` değeri, deponunki değil), **deponun sürümü** (`repo_version`), **deponun commit'i** (`commit`), **son güncellemenin durumu** (`update_status`: `state`/`message`/`time`), **imzalama işareti** (`signing_partition`), toplantı sayısı ve durum dağılımı, son tamamlanan toplantı, recordings/imports/sqlite boyutları, boş disk, bellek baskısı, `pmset -g therm` CPU_Speed_Limit, yük ortalaması ve son 5 hata satırı ve **hata günlüğü özeti** (`error_journal`: `last_24h` türüne göre sayılar, `crashes_24h`, `last` — son 5 kaydın zamanı/türü/kısa iletisi; ayrıntı aşağıda). Rapor paylaşımı kapalıysa yazılmaz.

### Hata ve çökme toplama (1.2.63+)

Her Mac kendi `~/Library/Application Support/MeetingOS/errors.jsonl` dosyasına satır satır yazar (0600, 1 MB’da `errors.jsonl.1` olarak döner, aynı `(tür, ileti)` on dakikada bir kez sayılır). Beslendiği yerler: uygulamadaki her hata bandı (`ui` — tek bir `error` setter’ından geçtiği için elli çağrı yerinin hepsi kapsanır), sıfırdan farklı kodla biten iş süreci (`job`, komut adı ve çıkış koduyla) ve CLI’ın en dıştaki hata yakalayıcısı, `note_cloud_failure` (`cloud`), kayıt yardımcısının başlatılamaması / yeniden başlatma sınırı / sıfırdan farklı çıkışı (`capture`), `update-status.json`’daki `failed` durumu (`update`, kendi zamanına göre bir kez alınır) ve macOS çökme raporları (`crash`). Satırda toplantı metni, konuşmacı adı ya da toplantı numarası bulunmaz — toplantı yalnız 8 haneli bir karma olarak geçer ve `/Users/<ad>` her zaman `/Users/…` olur.

`~/Library/Logs/DiagnosticReports/` altındaki `MeetingOS-*.ips` ve `MeetingCapture-*.ips` dosyaları **açılışta ve saatte bir** taranır; `errors-state.json` içindeki su işareti ve görülen olay kimlikleri sayesinde aynı rapor iki kez alınmaz (günlüğü temizlemek bu işareti silmez, temizlenen bir çökme geri gelmez). Her `.ips` bir JSON başlık satırı + bir JSON gövdedir; alınan alanlar: süreç adı, paket sürümü, `exception.type`/`signal`, sonlanma nedeni ve düşen iş parçacığının **yalnız bizim modülümüze ait ilk 8 çağrı adı** (adres yok). Raporun kendisi hiçbir yere kopyalanmaz.

Nabız bunları `error_journal` altında taşır. `reports summarize` her Mac için bir satır basar (`Mac-Adı · hata günlüğü (24s): job 3, cloud 2 · çökme 1 · en son: …`) ve iki yeni uyarı üretir: **`crash`** (son 24 saatte en az bir çökme → hata seviyesi) ve **`error_journal`** (günde 5+ kayıt → uyarı seviyesi). Kullanım Mac’inde aynı bilgi Ayarlar → Sistem → **Hatalar** kartındadır: son 5 kayıt, **Tanılama raporunu dışa aktar** ve **Hata günlüğünü temizle**. Elle bakmak için `.venv/bin/python -m meeting_os errors list` (`--limit`), temizlemek için `… errors clear`. Tanılama raporu (`diagnostics`) günlüğün son 20 kaydını çökme özetleriyle birlikte taşır — bir çökme bildirilirken kullanım Mac’inden istenecek tek dosya odur.

## Geliştirme Mac’inde (bu Mac)
1. Oturum başında `.venv/bin/python -m meeting_os reports summarize` — önce **uyarı listesi** (stderr: 3 gündür nabız yok, disk 3 GB altı, gece öz-testi başarısız, bulutta anahtar/kredi yüzünden bekleyen toplantı, kayıt sürerken parça gelmiyor, bellek baskısı, **kurulu sürüm ile depo sürümü farklı**, **son güncelleme başarısız**, **imzalama izni yok**, **son 24 saatte çökme**, **son 24 saatte 5+ hata kaydı**), ardından Mac başına hata günlüğü satırı, sonra bütün Mac’lerin raporları, hata sayıları, isimsiz konuşmacı oranı, maliyet. Her Mac için `heartbeat` satırı: son görülme, boş disk, termal, kurulu sürüm/depo sürümü (`app_version`/`repo_version`), depo commit'i, son güncelleme durumu, günlük `probe` özeti (`Öz-test temiz` ya da eksik madde). Nabız saatte bir yazılır; öz-test günde bir kez, kayıt yokken, nabızla birlikte koşar (`probe-last.json` önbelleği).
2. Sorunlu raporu aç (`iCloud Drive/MeetingOS-Reports/<mac>/…json`), nedeni bul, düzelt, test et, commit + `git push origin v0.1`.
3. Kullanım Mac’i bir sonraki açılışta günceller (veya kartta tek tık).

### Yarıda kalan güncelleme

Bir güncelleme birleştirip derleyemeden düştüğünde depo yeni commit'te, kurulu uygulama eskidedir. Bu durumun **tek görünür işareti nabızdaki `app_version` ≠ `repo_version`** farkıdır: `summarize` bunu “eski uygulama · güncelleme yarıda kalmış olabilir: sh scripts/update.sh” satırıyla söyler, `update_status.state == "failed"` ise ikinci bir satır da o güncellemenin mesajını gösterir. Uygulamadaki kontrol bu Mac'i “güncel” sayar (yeni commit'te olduğu için `behind=0`), yani düğme çıkmaz — komutu bir kez elle çalıştırmak gerekir. Yeniden çalıştırma güvenlidir: `build/installed-commit` kurulan son commit'i tutar, bu yüzden ikinci deneme pip'i ve kayıt yardımcısını atlamaz (HEAD'e bakan eski sürüm atlıyordu ve yeni uygulamayı eski bağımlılıklarla kuruyordu).

### Etiket, sürüm demektir — release paketi değil

`gh release create vX.Y.Z` ile oluşan **zip ve SHA256 hiçbir güncelleme yolunda kullanılmaz**. Kullanım Mac'i depoyu `git fetch` ile alır ve kaynaktan derler; kurulacak sürümü belirleyen tek şey **etikettir**. Release sayfası insanlar içindir; oradaki dosyayı indirmek, doğrulamak ya da imzalamak akışın parçası değildir.

### Etiket ve dal asla geri alınmaz (force-push yasak)

`git push --force` (ve `git tag -f` + `push --tags --force`) bu dalda yasaktır. Kullanım Mac'i `merge --ff-only` ile ilerler: geçmişi değişmiş bir dal orada **ileri sarılamaz** hâle gelir ve o Mac bir daha hiçbir sürümü kuramaz — düzeltmek için birinin o Mac'in başına oturması gerekir. Yanlış bir yayın çıktıysa çözüm geri almak değil, **düzeltmeyi yeni bir `vX.Y.Z` etiketiyle ileri doğru yayınlamaktır**. (Etiketin sunucuda oynatılmasına karşı `update.sh` ve uygulamadaki kontrol `fetch --tags --force` kullanır; bu yalnızca Mac'in donup kalmasını engeller, force-push'u meşrulaştırmaz.)

### Geri dönüş (rollback) yok

Eski bir sürüme dönmenin desteklenen bir yolu **yoktur**. `git -C <depo> checkout vX.Y.Z && MEETING_OS_UPDATE_UNTAGGED=1 sh scripts/update.sh` işe yaramaz: ölçüldü (10 Eylül 2026, sahte derleme + yerel bare origin ile) — `update.sh` `merge --ff-only` ile **doğrudan en yeni commit'e ileri sarar** ve onu derler; sonuç dönüş değil, aynı yeni sürümdür. Kurulu uygulamayı gerçekten eski bir etikete döndürmenin tek yolu o etikete geçip derleyiciyi elle çalıştırmaktır (`git -C <depo> checkout vX.Y.Z && sh scripts/build-desktop.sh` — **test edilmedi**, ve bir sonraki `update.sh` bunu geri alır). `build/app-backups` bir geri dönüş aracı değildir: oradaki kopya yalnız yerleştirme adımı düşerse geri konur, en yeni ikisi tutulur.

Kullanım Mac’i yalnız **etiketli sürümleri** kurar: hem uygulamadaki kontrol hem `update.sh`, `origin/v0.1` üzerinden erişilebilen etiketleri sürüm sırasına dizip **en yükseğini** hedef alır (`git tag --merged origin/v0.1 'v*' | sort -V | tail -1`); `describe --abbrev=0` kullanılmaz, çünkü o uçtan geriye yürüyüp ilk rastladığı etikette durur ve dalda birden çok etiket varsa kurulu olandan **eski** bir sürümü işaret edebilir; etiketten sonra atılan commit’ler bir sonraki etikete kadar diğer Mac’e gitmez (1.2.36). Bu yüzden her yayın `gh release create vX` ile etiketlenir; etiket sonrası atılan belge commit’leri bir sonraki etikete kadar diğer Mac’e gitmez. Geliştirme Mac’inde `MEETING_OS_UPDATE_UNTAGGED=1 sh scripts/update.sh` bu kapıyı açar.


## Kurulum durumu kartı (1.2.11+)

Kullanım Mac’inde bir şey çalışmıyorsa önce Ayarlar (⌘,) → **Sistem → Kurulum durumu**: izinler, OpenRouter anahtarı, sözlük, sürüm ve teşhis raporu klasörünün yazılabilirliği tek listede; kırmızı maddede “İzin iste” ya da “Ayarları aç” doğrudan ilgili yere götürür. Geliştirme Mac’inde rapor görünmüyorsa kullanım Mac’inde bu karttaki “Teşhis raporları” satırına bakın (kapalı / klasör yok / kaç rapor yazıldı).

## Düğme görünmüyorsa (eski sürümde “güncel” yazıyor ama değil)

1.2.45 öncesi sürümler yerel değişiklik, ayrışma ya da yarıda kalmış güncelleme durumunda düğmeyi gizleyip “güncel” diyordu. Terminal’den güncelleme düğmeden bağımsızdır:

```sh
cd ~/meeting-os
git status --short                 # bir şey listeliyorsa: git stash
git fetch --tags --force origin v0.1
git show origin/v0.1:scripts/fix-signing-prompts.sh > /tmp/fsp.sh && sh /tmp/fsp.sh   # Mac parolası bir kez
# Meeting OS’u ⌘Q ile kapatın, sonra:
sh scripts/update.sh; sleep 60; tail -5 "$HOME/Library/Application Support/MeetingOS/update.log"
```
