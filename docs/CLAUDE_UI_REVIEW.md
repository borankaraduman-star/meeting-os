# Meeting OS Masaüstü Checkpoint — Kritik İnceleme

## 1. Süreç Yaşam Döngüsü (Process Lifecycle)

**Kayıt → finalize arasında "yetim" veri riski (en kritik).** `start()` sadece bir dizin (`recordingDir`) oluşturuyor; DB'de hiçbir meeting satırı yok. Gerçek `Meeting` kaydı yalnızca `finalize` başarıyla tamamlanınca oluşuyor. Eğer:
- `finalize` başarısız olursa (`ok=false`), veya
- uygulama kayıt sırasında ya da finalize tamamlanmadan kapatılırsa,

...capture dizini diskte durur ama hiçbir DB kaydına bağlı değildir. "Son transkripti oluştur / Kurtar" butonu ise `meeting.metadata["capture_dir"]` şartına bağlı — yani zaten var olan bir meeting kaydı gerektiriyor. Meeting hiç oluşmadıysa bu buton hiç görünmez ve kullanıcı o kaydı bir daha asla bulamaz (Finder dışında).
**Düzeltme:** `record` başlarken hemen `status="recording"` ve `capture_dir` alanıyla bir taslak meeting satırı yaz (finalize bunu güncellesin, yeni satır açmasın). Böylece kurtarma UI'si her zaman erişilebilir olur.

**`stop()` bağımsız native recorder'ı senkron durdurmuyor.** `job?.interrupt()` yalnızca Python "record" sürecine SIGINT gönderir; native kayıt alt süreci bağımsız olduğu için (prompt'ta belirtildiği gibi) bu sinyalin native tarafa ulaşıp ulaşmadığı ve son chunk'ın diske flush edildiği garanti değil. `finalize`, `interrupt()` çağrısından hemen sonra terminationHandler tetiklenince başlıyor — journal (`capture-native.jsonl`) henüz son satırı yazmamış ya da yarım satır bırakmış olabilir. Sonuç: son birkaç saniye/dakikanın kaybı veya finalize/play sırasında JSON parse hatası.
**Düzeltme:** Native tarafın "temiz kapanış" işaretini (örn. journal'a son satır olarak `{"closed":true}` veya ayrı bir lock/PID dosyasının kalkması) finalize başlamadan önce bekle; `stop()` bu handshake tamamlanana kadar "Ses parçaları tamamlanıyor…" durumunda kalsın.

**Uygulama kapatılırken yetim süreçler.** `NSApplication` sonlanma sırasında `job` ve olası native alt süreç interrupt edilmiyor; mikrofon açık kalabilir, kayıt yarım kesilebilir.
**Düzeltme:** `applicationWillTerminate`/`NSApplicationDelegate` içinde `job` varsa senkron `interrupt()` + kısa bekleme + gerekirse `terminate()` ekle.

## 2. UI Yenileme (Refresh)

**`refresh()` sonsuza kadar kilitlenebilir.** `refreshing` bayrağı, `invoke()` çağrısı bitene kadar `true` kalıyor (`defer` ancak `await` dönünce çalışır). Aşağıdaki "blocking IPC" maddesinde açıklanan pipe kilitlenmesi gerçekleşirse, bu bayrak asla `false` olmaz ve **timer sonsuza kadar hiçbir şey yenilemez** — kullanıcıya hata bile gösterilmez, arayüz sessizce donmuş görünür.
**Düzeltme:** `invoke()`'a bir zaman aşımı ekle (örn. 5-10 sn sonra process'i `terminate()` edip hata fırlat); `refreshing` bu hatayla da `false`'a dönsün.

**Yeni meeting seçimi sıralamaya bağımlı.** `finalize` sonrası `selected=nil` set ediliyor; bir sonraki `refresh()` `meetings.first?.id`'yi seçiyor. `store.meetings()`'in en yeniyi ilk sıraya koyduğu garanti edilmiyorsa (kod görülmedi), kullanıcı biraz önce bitirdiği toplantı yerine başka birini görebilir.
**Düzeltme:** `finalize` CLI çıktısına yeni meeting id'sini bas, `launch` tamamlanma callback'inde `selected` bu id'ye set edilsin — `meetings.first` varsayımına güvenilmesin.

## 3. Bloklayan IPC (`invoke`)

**Okunmayan `stderr` pipe'ı → kalıcı kilitlenme riski (en kritik teknik bulgu).** `invoke()` içinde `error` pipe'ı oluşturuluyor ama hiçbir yerde okunmuyor. `meeting_os.desktop.main()` normal akışta hataları yakalayıp stdout'a JSON olarak yazıyor, fakat modül import edilirken oluşacak bir hata (syntax hatası, eksik bağımlılık, DeprecationWarning gibi Python uyarıları, bir kütüphanenin doğrudan stderr'e yazması vb.) `try/except` bloğunun dışında kalır ve doğrudan stderr'e basılır. macOS pipe tamponu (~64KB) dolduğunda yazan taraf (Python) bloke olur, `waitUntilExit()` hiç dönmez. Bu, her 2 saniyede bir tetiklenen `snapshot` çağrısında gerçekleşirse tüm uygulama kalıcı olarak donar (yukarıdaki `refreshing` sorunuyla birleşiyor).
**Düzeltme:** `p.standardError = FileHandle.nullDevice` yap (bridge zaten hataları stdout'a JSON olarak döndürüyor), ya da `error` pipe'ını arka planda `readabilityHandler` ile drenaj et. Ayrıca genel bir timeout mekanizması ekle.

## 4. Kimlik/Ses Profili Güvenliği (Identity Safety)

**`enroll` + `label` iki ayrı, atomik olmayan IPC çağrısı.** `saveLabel(enroll:true)` önce `action:"enroll"` sonra ayrı bir `action:"label"` çağırıyor. İlk çağrı başarılı olup ikincisi ağ/süreç hatasıyla başarısız olursa: ses profili bir isme kaydedilmiş olur ama o segmentin görünen etiketi güncellenmez — kullanıcı arayüzde tutarsız bir durum görür ve profilin gerçekten doğru kişiye bağlandığından emin olamaz.
**Düzeltme:** Python tarafında `enroll` action'ı, embedding kaydını ve segment etiketlemesini tek bir DB transaction'ında yapsın; Swift tarafındaki ikinci ayrı `label` çağrısı kaldırılsın.

**İsim çakışması riski.** `dispatch`'te `enroll`, embedding'i doğrudan `request['name']` string'ine bağlıyor; aynı adı taşıyan iki farklı gerçek kişi (örn. iki "Ali") aynı ses profiline karışabilir — bu, gelecekteki toplantılarda yanlış kişiye isim önerilmesi anlamına gelir (yanlış kimlik ataması, tersine çevrilmesi zor).
**Düzeltme (bu gece yapılabilir minimal):** Enroll öncesi `profiles` listesinde aynı isim varsa UI'de "Bu isim zaten kayıtlı, aynı kişi mi?" onayı iste; onaylanmazsa farklı bir görünen ad kullanmasını iste.

---

**Öncelik sırası:** (3) stderr pipe kilitlenmesi ve (1a) yetim recording→meeting bağlantısı en yüksek risk; ikisi de sessiz veri kaybına/donmaya yol açıyor ve düzeltmeleri küçük kapsamlı.
