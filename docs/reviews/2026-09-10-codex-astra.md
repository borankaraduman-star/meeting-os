**Önerim: sonraki sürümleri yeni özelliklere değil, ekip bulutunun güvenilirliğine ayırın.** Yerel düzeltme, geri alma, kayıt kurtarma ve kanıt gösterme tarafında değerli bir temel var. Fakat 1.2.67’de “bu Mac’te öğrendi” ile “ekibin tamamı doğru ve güncel bilgiyi kullanıyor” arasında açıklar bulunuyor.

İnceleme yalnız dosya okumaya dayanıyor; kod değiştirmedim, test veya canlı senaryo çalıştırmadım. Aşağıda koddan doğrudan çıkan davranışlarla canlı doğrulama gerektiren riskleri ayırdım. Python 865 / Swift 228 sayılarını bu incelemede doğrulanmış sonuç olarak kullanmıyorum; son checkpoint ayrıca disk nedeniyle sekiz Python test hatası kaydediyor.

**1. P0 — Bulut paylaşımı açık, fakat kapatma anahtarları kullanılamıyor**

- **Sorun / kanıt:** Bulut yapılandırıldığında `team_dir` boş kalıyor, etkin yol `_mirror` üzerinden çözülüyor: [reports.py:64–70](meeting_os/reports.py:64). Ancak sözlük, kelime ve profil anahtarlarının üçü de `teamDir.isEmpty` olduğunda devre dışı: [SettingsSheet.swift:61–81](desktop/Sources/MeetingOS/SettingsSheet.swift:61). Kullanıcı “Seçilmedi” görürken verisi buluta gidebiliyor. Ayrıca paylaşımı kapatmak mevcut ekip kelimelerini/profillerini kullanımdan çıkarmıyor; tanıma ve düzeltme kayıtlı DB satırlarını okumaya devam ediyor.
- **Kullanıcı etkisi:** İlk gün uygulamanın ne paylaştığını yanlış anlar. İlk hafta paylaşımı durdurmak istediğinde arayüzden bunu yapamaz; bir ayarın kapalı olmasıyla beklediği davranış da örtüşmez.
- **En küçük öneri:** “Ekip klasörü” bölümünü etkin hedefi gösteren **Ekip paylaşımı** bölümüne dönüştürün: bulut, klasör veya kapalı. Anahtarlar hedefin türünden bağımsız çalışsın. “Yeni paylaşımı durdur”, “ekip bilgisini kullanma” ve “önceden paylaşılanı kaldır” davranışları açıkça tanımlansın; kullanıcıya üç yeni pencere açmak gerekmiyor. Mevcut varsayılan açık tercihi korunabilir.
- **Doğrulama:** `team_dir=""`, geçerli token ve önceden içe aktarılmış bilgilerle başlayın. Anahtarı UI’dan kapatın; yeni yükleme, indirme ve uygulama davranışlarını ayrı sınayın. Python ayar testi yanında Swift görünüm testi gerekli.
- **Risk:** Yalnız düğmeleri etkinleştirmek gizlilik sorununu tamamlamaz. Önceden yüklenen profil, kelime ve hata dosyaları için `_push_deletions` bugün yalnız raporları ele alıyor: [team_cloud.py:410–417](meeting_os/team_cloud.py:410).

**2. P0 — Ekip ve cihaz kimliği, saklanan verinin sınırı olmalı**

- **Sorun / kanıt:** `join()` yalnız token dosyasını değiştiriyor; ayna hep `data_dir/team`, durum dosyası hep aynı: [team_cloud.py:95–133](meeting_os/team_cloud.py:95). Yeni tokenla eşitleme eski aynadaki kendi profil ve raporlarını yeni ekibe yükleyebilir. API anahtarı değişikliği de açık `team.token` yoksa ekip kimliğini değiştiriyor. Cihaz kimliği ise değiştirilebilir `LocalHostName`: [reports.py:157–164](meeting_os/reports.py:157). Sunucu sahipliği, istemcinin gönderdiği host başlığıyla yolun eşitliğine dayanıyor: [sync_server.py:379–382](server/sync_server.py:379).
- **Kullanıcı etkisi:** İlk kurulumda aynı adlı iki Mac birbirinin dosyalarını değiştirebilir. İlk hafta anahtar yenilemek veya ekibe katılmak eski ekip bağlamındaki raporların farklı bir ekibe taşınmasına yol açabilir.
- **En küçük öneri:** Ekip tokenını ilk kurulumdan sonra API anahtarından bağımsız, kalıcı tutun. Ayna, eşitleme durumu ve içe aktarılmış kayıtlar ekip kimliğiyle ayrışsın. Cihaz için kalıcı rastgele kimlik kullanın; Mac adı yalnız görünen ad olsun. Sunucunun “başkasının dosyasına yazamaz” garantisi korunacaksa cihaz kimliği ayrıca cihaz kimlik bilgisine bağlanmalı.
- **Doğrulama:** A ekibinde rapor/profil oluştur → B ekibine geç → B sunucusunda A’dan taşınmış hiçbir dosya bulunmamalı. Aynı görünen adlı iki cihaz, cihaz yeniden adlandırma ve API anahtarı yenileme senaryolarını ekleyin.
- **Risk:** Göç sırasında yanlış sahiplik atamak mevcut bilgiyi kaybettirebilir. Eski aynayı yeni ekibe otomatik yüklemek yerine kendi ekip kimliği altında korumak gerekir. Tek ortak bearer token, tek cihazı erişimden çıkarma olanağı da sağlamıyor.

**3. P0 — Silinen veya düzeltilen ses örneği diğer Mac’lerde yaşamaya devam ediyor**

- **Sorun / kanıt:** `pull_profiles()` yalnız örnek ekliyor; kaynak anlık görüntüsünden çıkarılan örnekleri DB’den kaldırmıyor: [team_knowledge.py:325–348](meeting_os/team_knowledge.py:325). Bulutun `_sweep()` işlemi dosyaları kaldırıyor, öğrenilmiş DB satırlarını değil. Mevcut silme testi, **alıcıda** profil silip yeniden gelmesini engellemeyi sınamış: [test_team_knowledge.py:228–239](tests/test_team_knowledge.py:228).
- **Kullanıcı etkisi:** İlk gün yanlış kişiye öğretilen ses ekibe yayılır. İlk hafta kaynak Mac’te düzeltilse veya geri alınsa bile başka bir arkadaş aynı yanlış eşleşmeyi görür. Profil silme beklentisi de eksik karşılanır.
- **En küçük öneri:** Her başarılı kaynak profil anlık görüntüsünü, o kaynağa ait `team:` örnekleriyle uzlaştırın: ekle, değiştir, artık bulunmayanı kaldır. Yerel örnekler korunmalı. İçerik karmasının yanına kalıcı kaynak örnek kimliği koymak, yeniden adlandırma ve vektör düzeltmesini daha güvenilir yapar.
- **Doğrulama:** A öğretir → B içe alır → A örneği düzeltir/siler/⌘Z yapar → B eşitlenir. Hem `samples` hem yeni bir sesin tanıma sonucu kontrol edilmeli. B çevrimdışıyken yapılan değişiklik de sonradan ulaşmalı.
- **Risk:** Eksik indirme veya erişilemeyen klasör “kaynak boş” sayılamaz. Silme yalnız tamamlanmış ve doğrulanmış anlık görüntüye dayanmalı; aksi hâlde düzeltme veri kaybı üretir.

**4. P0 — Yarım indirme, uygulanmamış bilgiyi “alındı” diye işaretleyebiliyor**

- **Sorun / kanıt:** `_pull_words()` her dosyayı aldığında `pulled[path]` karmasını güncelliyor; birleşik kelime dosyasını ancak bütün indirmelerden sonra yazıyor: [team_cloud.py:431–454](meeting_os/team_cloud.py:431). İkinci dosyada bütçe biterse ilk dosyanın içeriği bellekte kalırken karması durum dosyasına kaydediliyor: [team_cloud.py:526–529](meeting_os/team_cloud.py:526). Sonraki tur onu değişmemiş sanabilir. Sözlükte de benzer yazım sırası var.
- **Kullanıcı etkisi:** İlk gün dolu bir ekibe katılan arkadaş bazı düzeltmeleri alamaz. İlk hafta ağ düzelmiş olsa bile eksik bilgi kendiliğinden tamamlanmayabilir; durum başarılı görünebilir.
- **En küçük öneri:** “İndirildi” ve “yerelde uygulandı” durumlarını ayırın. Kaynak dosyaları ayrı atomik dosyalara indirin; birleşik görünümü bunlardan oluşturun. İlerlemenin kalıcı kaydı, içerik kalıcılaştıktan sonra yapılsın.
- **Doğrulama:** Üç cihazlı testte ilk kaynak indirildikten hemen sonra ikinci isteği zaman aşımına uğratın; süreci yeniden başlatın. Bütün kelimelerin tam bir kez uygulanmasını doğrulayın. Mevcut bütçe testi sıfır bütçeyle başlamayı sınamış, bu ara kesintiyi değil: [test_team_cloud.py:349–363](tests/test_team_cloud.py:349).
- **Risk:** Atomik dosya yazımı tek başına dosya + durum tutarlılığı sağlamaz. Geçici indirmelerin disk bütçesi sınırlı olmalı; kayıt başlatma bu işlemi beklememeli.

**5. P0 — Aynı başlıklı, farklı vadeli görevler tek göreve düşebiliyor**

- **Sorun / kanıt:** `duplicate_index()` eşit/alt dize başlıklarda vade kontrolüne ulaşmadan birleşme kararı veriyor: [intelligence.py:269–282](meeting_os/intelligence.py:269). İkinci katman `dedupe_actions()` da sahip ve başlık benzerliğiyle birleştiriyor; iki dolu, farklı `due_text` değerini engellemiyor: [memory.py:86–114](meeting_os/memory.py:86). Örneğin aynı kişinin “Durum raporunu gönder” görevleri pazartesi ve cuma için ayrı taahhütler olabilir.
- **Kullanıcı etkisi:** İlk gün temiz görünen bir listede görev eksilir. İlk hafta arkadaş verdiği ikinci sözü takip edemez; bu doğrudan “kimseyi yarı yolda bırakmama” hedefini etkiler.
- **En küçük öneri:** Her iki birleştirme katmanında, açık vade çatışması varsa otomatik birleşmeyi durdurun. Belirsiz tekrarları ayrı tutmak ilk küçük değişiklik için yeterli. Sonradan “aynı görev olabilir” önerisi eklenebilir.
- **Doğrulama:** Aynı başlık/sahip + farklı vade, farklı miktar, ayrı tekrar dönemi; ayrıca gerçekten aynı görevin iki anlatımı. Hem `merge_records` hem DB’ye kaydetme sonrası görev sayısı ve alanları sınanmalı.
- **Risk:** Bazı kopyalar görünür kalabilir; bu, gerçek görevin sessizce kaybolmasından daha düşük maliyetli. Birleştirme sırasında iki kaynaktan gelen `needs_review` bilgisinin de korunması gerekir.

**6. P0 — Buluta çıkan tanılama içeriğinin garantisi belgelerden daha zayıf**

- **Sorun / kanıt:** Hata metnindeki maskeleme yalnız kullanıcı dizinini değiştirip metni kısaltıyor: [errors.py:58–62](meeting_os/errors.py:58). Bağlam anahtarları olay türüne göre beyaz listeyle sınırlandırılmıyor. Bu günlük buluta ham dosya olarak yükleniyor: [team_cloud.py:379–385](meeting_os/team_cloud.py:379). Ayrıca rapor, ayar açıksa transkript taşıyor ve varsayılan durumda bile toplantı kimliği içeriyor: [reports.py:399–414](meeting_os/reports.py:399). Buna karşılık ekip rehberinde “transkript/toplantı numarası hiçbir zaman gitmez” deniyor. **Gerçek bir içerik sızıntısı gözlemlemedim; kod bu mutlak garantiyi sağlamıyor.**
- **Kullanıcı etkisi:** İlk gün paylaşım kapsamını yanlış öğrenir. İlk hafta bir hata mesajı hassas dosya adı, sunucu yanıtı veya içerik parçası taşıdığında bunun da ekibe gidebileceğini bilmez.
- **En küçük öneri:** Bulut tanılamasında olay kodu + izinli sayısal/teknik alanlar kullanın; serbest hata ayrıntısı yerelde kalsın. Mevcut rapor ayarını gerçek yükleme sınırında uygulatın. EKIP/KULLANIM/ayar açıklamalarını aynı veri sözleşmesine göre düzeltin; eski metinli raporların yeni ayarda nasıl ele alınacağını da tanımlayın.
- **Doğrulama:** Hata metnine kurgusal token, kişi adı, toplantı cümlesi ve hassas dosya adı enjekte edin. Sunucuya ulaşan yükte bulunmamalılar. `share_text` açık→kapalı geçişini eski rapor dosyalarıyla sınayın.
- **Risk:** Fazla sade tanılama hata çözmeyi zorlaştırabilir. Yerelde ayrıntı + açıkça dışa aktarılan teşhis paketi alternatifini koruyun; bütün hata metinlerini daha büyük regex listeleriyle temizlemeye güvenmeyin.

**7. P0 doğrulama kapısı — Göze batmama garantisi canlı olarak kanıtlanmalı**

- **Sorun / kanıt:** Paylaşım algısı yalnız Zoom pencere sahipliği ve belirli pencere adlarına bakıyor: [QuickControl.swift:16–41](desktop/Sources/MeetingOS/QuickControl.swift:16). Algı `false` kalırsa yüzen panel görünür: [DiscreetMode.swift:33–45](desktop/Sources/MeetingOS/DiscreetMode.swift:33). Ana pencere koruması `sharingType` bayrağına dayanıyor. Checkpoint bu davranışın canlı doğrulanmadığını açıkça söylüyor. Bu, kanıtlanmış ekran sızıntısı değil; yüksek etkili bir doğrulama açığı.
- **Kullanıcı etkisi:** İlk gün tüm ekranını paylaşan arkadaş panelin veya eski transkriptin görünmediğini varsayar. İlk hafta başka toplantı uygulaması ya da farklı paylaşım biçimi bu varsayımı bozabilir.
- **En küçük öneri:** Göze batmama açıkken kayıt panelini varsayılan gizleyin; kullanıcı isterse geçici açsın. Ana pencerenin dışarıdan gerçekten görünmediğini alıcı cihazdan doğrulayın. Sonuç güvenilir değilse mevcut korumayı “garanti” diye sunmayın; açık bir sunum görünümüyle hassas içeriği örtün.
- **Doğrulama:** İkinci Mac’ten izleyerek Zoom ve kullanılan diğer toplantı uygulamalarında tüm ekran/pencere paylaşımı; paylaşım sırasında kayıt başlatma, ayar açma, bildirim, ekran/Space değiştirme. Kabul ölçütü alıcının gördüğü görüntüdür.
- **Risk:** Paneli gizlemek kullanıcının kaydın sürdüğünü fark etmesini zorlaştırabilir. Menüden açılan süre/sinyal bilgisi ve kısayol geri bildirimi korunmalı; sık ekran taraması eklenmemeli.

**8. P1 — Öğrenimin ekibe ulaşması kalıcı bir iş olmalı; “eşitlendi” durumu dürüst olmalı**

- **Sorun / kanıt:** Swift her köprü çağrısında ayrı Python süreci başlatıyor: [App.swift:58–67](desktop/Sources/MeetingOS/App.swift:58). Adlandırma kancası `sync_async()` çağırıyor; bu bir `daemon=True` iş parçacığı ve köprü yanıtı verdikten sonra süreç kapanıyor: [team_cloud.py:580–597](meeting_os/team_cloud.py:580), [desktop.py:742–753](meeting_os/desktop.py:742). Dolayısıyla anında teslim garanti değil. Kalıcı toparlama açılışta ve saatlik boşta bakımda. Üstelik durum kartı eski `last_ok` varsa yeni `last_error` değerini göstermiyor: [SetupStatus.swift:89–95](desktop/Sources/MeetingOS/SetupStatus.swift:89).
- **Kullanıcı etkisi:** İlk gün “öğrettim” geri bildirimi alır, arkadaşı aynı kelimeyi tekrar düzeltir. İlk hafta bulut günlerdir erişilemiyor olsa bile yeşil durum görebilir.
- **En küçük öneri:** Düzeltme işleminde kalıcı bir “gönderilecek değişiklik var” kaydı bırakın. Swift’in yönettiği tek bir arka plan işi bunu kısa bir birleştirme süresinden sonra göndersin; açılışta devam etsin. Ağdan alınan bilgiler DB’ye de uygulansın. Durum satırı “yerelde kaydedildi / paylaşım bekliyor / son teslim” ayrımını yapsın; hata ve son başarının yaşı dikkate alınsın.
- **Doğrulama:** Gerçek `python -m meeting_os.desktop` alt süreciyle öğretme yapın; ağ yanıtını geciktirin, köprüyü kapatın, uygulamayı yeniden açın. Önerilen hedef: çevrimiçi ve kayıt yokken düzeltmenin diğer Mac’te kullanılabilir olması p95 ≤60 saniye.
- **Risk:** `_PASS` yalnız süreç içi kilit: [team_cloud.py:551–573](meeting_os/team_cloud.py:551). Birden çok köprü süreci aynı aynayı değiştirebilir. Kalıcı iş, süreçler arası tek-yazıcı düzeniyle kurulmalı; çözüm hızlı köprüde ağı beklemek olmamalı.

**9. P1 — Yanlış eşleşmeyi düzeltmek, doğru kişinin bütün ekip öğrenimini kapatmamalı**

- **Sorun / kanıt:** Profil içe aktarma, `rejections` tablosunda adı geçen kişinin **bütün** yeni ekip örneklerini atlıyor: [team_knowledge.py:334–345](meeting_os/team_knowledge.py:334). Oysa yerel tanımada ret belirli vektör benzerliğine uygulanıyor: [store.py:648–656](meeting_os/store.py:648). Mevcut test, farklı bir vektöre verilen ret yüzünden doğru örneğin de alınmamasını özellikle bekliyor. Ayrıca otomatik tanımadan üretilen `auto:` örnekler mevcut yayın filtresinden geçebiliyor.
- **Kullanıcı etkisi:** İlk gün “bu ses Ayşe değil” düzeltmesi yapar. İlk hafta diğer arkadaşların öğrettiği temiz Ayşe örneklerinden yararlanamaz. Ters yönde, otomatik bir yanlış eşleşme ekibin yeni örnekleriyle güçlenebilir.
- **En küçük öneri:** Kişiyi açıkça engelleme ile belirli sesin o kişiye ait olmadığını söylemeyi ayırın. Ret, aynı model ve yakın vektör için geçerli olsun. İlk aşamada ekipte yayımlanan örnekleri insan tarafından adlandırılan/onaylananlarla sınırlayın; otomatik örnekler yerelde kalabilir.
- **Doğrulama:** Ayşe’ye benzemeyen bir ses reddedildikten sonra gerçek Ayşe örneği içe alınabilmeli; reddedilen sese yakın örnek engellenmeli. Üç Mac arasında otomatik yanlış etiketin kendi kendini güçlendirmediğini ölçün.
- **Risk:** Küresel eşikleri düşürmek bu sorunu çözmez, yanlış adlandırmayı artırır. Değişiklik sonrası hem yanlış otomatik ad hem kaçırılan tanıma oranı izlenmeli.

**10. P1 — “Kanıt var” ile “iddia doğru destekleniyor” ayrı ölçülmeli**

- **Sorun / kanıt:** Analiz doğrulaması gerçek alıntı arıyor; bu güçlü bir koruma. Fakat anlamsal destek kontrolü ortak kök sözcük bulunmasına dayanıyor: [intelligence.py:153–202](meeting_os/intelligence.py:153). Gerçek alıntıdaki “göndermeyeceğim” ifadesi, benzer sözcükler taşıyan ters bir iddiayı bu kontrolden tek başına korumaz. Aynı blokta mikrofon kaynaklı çıkarım için yazılan `item['needs_review']=True`, son `clean.update(... needs_review=flagged or abstained)` hesabına katılmıyor.
- **Kullanıcı etkisi:** İlk gün alıntı görünce göreve güvenebilir. İlk hafta olumsuzlanan, koşula bağlı veya başka kişiye devredilen bir işi kendi taahhüdü sanabilir.
- **En küçük öneri:** Önce kaybolan mikrofon inceleme işaretini düzeltin. Sonra mevcut kıyas setine olumsuzlama, koşullu söz, devir, farklı vade ve iptal örnekleri ekleyin. Alıntı doğruluğu, sahip/vade doğruluğu ve iddianın desteklenmesini ayrı puanlayın. Her maddeye ikinci model çağrısı eklemek ilk adım olmasın.
- **Doğrulama:** [benchmark-analysis-cloud.py:96–118](scripts/benchmark-analysis-cloud.py:96) üzerindeki mevcut alan ölçümlerini genişletin. Aynı sürümü birkaç tekrarla kıyaslayın. Kimlik replay’i sabit, kurgusal profil setiyle de çalışsın; canlı profiller silinince `no_profile` artması başarı gibi yorumlanmasın.
- **Risk:** Fazla çekimserlik yararlı görevleri de saklar. Öncelik yanlış kesinliği azaltmak olmalı; görev yakalama oranını beraber ölçün. Gerçek toplantıları ortak test verisi olarak yüklemeyin.

**11. P2 — Disk bütçesi ekip aynasını da kapsamalı; “300 rapor” gerçek saklama sınırı değil**

- **Sorun / kanıt:** Depolama toplamı yalnız kayıtlar, içe aktarılan sesler ve DB’yi sayıyor: [desktop.py:194–209](meeting_os/desktop.py:194). Ekip aynası ve günlükler bu toplamda yok. Bulut en yeni 300 raporu indiriyor fakat daha önce indirilmiş, sunucuda hâlâ bulunan eski raporları kaldırmıyor: [team_cloud.py:481–525](meeting_os/team_cloud.py:481). Dolayısıyla 300, tur başına seçim sınırı; disk üst sınırı değil.
- **Kullanıcı etkisi:** İlk gün önemsiz görünür. Toplantılar biriktikçe ekip raporları her Mac’te çoğalır; kullanıcı Depolama kartındaki toplamla gerçek kullanım arasındaki farkı anlayamaz.
- **En küçük öneri:** “Ses / veritabanı / ekip önbelleği / günlükler” ayrımı gösterin. Başka cihazların raporlarına gerçek adet + bayt sınırı uygulayın. En küçük alternatif, normal ekip cihazlarına yalnız nabızları indirmek; ayrıntılı raporları gerektiğinde almak. Gönderilmemiş kendi verisi önbellek sayılmamalı.
- **Doğrulama:** Beş cihaz, yüzlerce rapor ve tekrar eden eşitlemeyle disk kullanımının sınırda durduğunu sınayın. Bakım sürerken kayıt başlatıp CPU, disk yazımı ve ses boşluklarını ölçün.
- **Risk:** Silme yalnız yeniden indirilebilir dosyalara uygulanmalı. Geliştirme worktree’lerini veya kullanıcının başka uygulama klasörlerini otomatik temizlemeye genişlememeli. Büyük klasör taramaları ana UI yoluna eklenmemeli.

**12. P2 — Düzeltme penceresi yeniden tek ana eyleme indirilmeli**

- **Sorun / kanıt:** Adlandırma penceresinde üç isim eylemi, bölüm seçici, kelime düzeltme ve gelişmiş metin düzenleme birlikte bulunuyor; sabit 520 pt genişlik kullanılıyor: [EditSegmentSheet.swift:46–101](desktop/Sources/MeetingOS/EditSegmentSheet.swift:46). Özet aynı anda durum satırı, bayatlık uyarısı ve ayrı yenileme kartı gösterebiliyor: [Intelligence.swift:122–130](desktop/Sources/MeetingOS/Intelligence.swift:122). Kelime önbelleği sınırlı, fakat LRU değil; erişilen öğe yenilenmiyor: [WordClick.swift:142–155](desktop/Sources/MeetingOS/WordClick.swift:142).
- **Kullanıcı etkisi:** İlk gün “yalnız bölüm / toplantı / öğren” farkını işlem sırasında çözmek zorunda kalır. İlk hafta tekrar eden açıklamalar düzeltmenin kendisinden daha fazla dikkat ister.
- **En küçük öneri:** Konuşmacıya tıklama yalnız kişi düzeltmesini, kelimeye tıklama yalnız kelime düzeltmesini açsın. İsim penceresinde kapsam seçimi + tek birincil eylem bulunsun; kısa sonuç satırı neyin öğrenildiğini söylesin. Özet için tek bayatlık satırı ve tek yenileme düğmesi kullanın. Önbelleği ancak ölçüm fayda gösterirse LRU’ya çevirin.
- **Doğrulama:** Yeni kullanıcıya üç görev verin: kişiyi adlandır, karışık paragrafta tek bölümü düzelt, ürün adını öğret. Süre, yanlış kapsam seçimi ve geri alma ihtiyacını ölçün. Küçük pencere, klavye/VoiceOver ve 100 kelimelik paragrafla canlı kontrol yapın.
- **Risk:** “Yalnız burada” düzeltmesini sessizce küresel öğretmeye çevirmeyin. Kapsam sadeleşirken görünmez olmamalı. Performans kazancı kanıtlanmadan okuma görünümünü yeniden yazmak gereksiz risk taşır.

**YAPMA**

- **Canlı transkript, sürekli analiz veya toplantı sırasında çalışan koç ekleme.** Kayıt yoluna yeni CPU, ağ ve dikkat maliyeti getirir.
- **Daha hızlı öğrensin diye bulanık kelime düzeltmesini otomatikleştirme veya kimlik eşiklerini genel olarak düşürme.** Yanlış öğrenimi ekip çapında büyütür.
- **Ekip hafızası için bütün transkriptleri ortaklaştırma.** Mevcut hedefin büyük bölümü doğrulanmış kelime ve ses örnekleriyle karşılanabilir; içerik paylaşımı ayrı bir ürün kararıdır.
- **Kişileri konuşma süresi veya görev sayısıyla sıralayan performans tablosu kurma.** Konuşma payı toplantıyı anlamaya yarar; bireysel etkinlik puanı değildir.
- **Bu aşamada senkronizasyonu büyük bir platforma dönüştürme veya UI’ı baştan yazma.** Üç–beş kişi için kalıcı işler, açık sahiplik, doğru silme ve birkaç güvenilir durum satırı daha değerlidir.

**Claude Code için uygulama sırası**

| Sıra | Birlikte ele alınacak maddeler | Neden / sürüm kabulü |
|---|---|---|
| **A — Paylaşım kontrolü** | **1 + 6** | Kullanıcı bugün paylaşımı kontrol edebilmeli ve neyin çıktığını doğru bilmeli. Bulut açıkken anahtarlar çalışmalı; kurgusal hassas içerik tanılamaya sızmamalı. |
| **B — Kimlik ve geri çekme** | **2 + 3** | Ekip sınırı ve kaynak sahipliği, silmenin temelidir. Ekip değişiminde eski veri taşınmamalı; kaynakta geri alınan örnek alıcıdan da kalkmalı. |
| **C — Teslim ve toparlanma** | **4 + 8** | Aynı eşitleme durum makinesini değiştiriyorlar. Kalıcı iş, süreçler arası tek yazıcı, yarım indirme ve dürüst durum birlikte bir sürüm eder. |
| **D — Görev güvenilirliği** | Önce **5**, ardından **10** | Önce modelden bağımsız görev kaybını kapatın. Ardından yeni kalite vakaları ve inceleme işareti düzeltmesiyle analiz davranışını doğrulayın. |
| **E — Öğrenme kalitesi** | **9** | Teslim ve geri çekme güvenilir olduktan sonra hangi örneğin öğrenileceği iyileştirilmeli. Sabit replay setinde yanlış tanıma artmamalı. |
| **F — Hafiflik ve sadelik** | **11 + 12** | Gerçek cihaz kullanımından alınan ölçümlerle küçük değişiklikler. Disk sınırı ve düzeltme akışı ayrı ayrı geri alınabilir kalmalı. |

**7 numara, ekip arkadaşlarına dağıtım öncesi bağımsız kabul kapısı olmalı.** Alıcı ekranında doğrulanmadan göze batmama garantisi verilmemeli.

Her sürümde ilgili Python/Swift testlerine ek olarak bir gerçek kullanıcı yolunu tamamlayın. Özellikle ekip bulutu için “test içinde iki sahte host” yeterli son kanıt değil: **iki ayrı uygulama süreci, üçüncü çevrimdışı cihaz, bir düzeltme, bir geri alma ve bir yeniden başlatma** aynı senaryoda çalışmalı.