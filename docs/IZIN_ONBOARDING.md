# İzin kurulumu (onboarding): ürün sözleşmesi

Meeting OS'un bir kayıt için dokunduğu üç macOS izni şunlardır: **Mikrofon**, **Sistem sesi** (Ekran Kaydı /
Ekran ve Sistem Sesi Kaydı) ve **Erişilebilirlik**. Kullanıcı bu izinleri tek ekranda, kart kart verir. Bu belge
o ekranın ürün sözleşmesidir. Kodda karşılığı `desktop/Sources/MeetingOS/PermissionContract.swift` dosyasıdır:
tipler, `PermissionProviding` protokolü, saf `PermissionFlow.reduce` ve `PermissionCardModel`. Testleri
`desktop/Tests/MeetingOSTests/PermissionContractTests.swift` içindedir. Sözleşme yalnız ekleme yoluyla genişler.
Native sağlayıcı ve SwiftUI kartları bu dosyaya karşı yazılır.

İlkeler (AGENTS.md): **kullanıcı asla ortada kalmaz** (her kartta çalışan bir düğme vardır, istenirse geçilebilir,
kurulum her an bitirilebilir), **kayıt asla kaybolmaz** (kayıt sürerken yeniden açma yapılmaz), **izin varmış
gibi gösterilmez** (rozet her zaman gerçek durumu gösterir; geçilen ya da isteğe bağlı bir izin yeşile boyanmaz).
Sahte onay kutusu ya da hiçbir şey yapmayan "Etkinleştir" düğmesi bulunmaz. Yapılacak eylem yoksa düğme hiç çizilmez.

## (a) Granola eşleme tablosu

Kaynak: `/Users/boran/dev/meetingos-granola/permissions/03a-izin-arayuz-akisi.md` (arayüz, `03a`) ve
`03b-izin-handler-native.md` (ana süreç ve native, `03b`). Hedef: `/Applications/Granola.app/Contents/Resources/app.asar`,
sha256 `17046e95777b85a211b1e6676ac86bd5835c30b51928051411a796017a1302b9`. REA MCP `analyze_javascript_application` bu
paket üzerinde çalıştı (4 JS ayrıştırıldı, 0 hata, anlamsal graf kısmi); kaynak metinleri ASAR başlığından salt okunur
bayt kesitiyle okundu ve hash'leri REA kayıtlarıyla eşleşti. Native taraf için `tcc.node` ve `macos_audio_capture`
arm64 dilimleri REA/Ghidra ile açıldı (`TCCAccessPreflight` @ `0x808`, `RequestSystemAudioPermission` @ `0x20c70`).
Yalnız **davranış** eşlendi; Granola'nın kodu, metni, markası ve varlığı kopyalanmadı. Kısaltma `L<satır>:C<sütun>` =
`main/index.js`; `primary:477:…` = `dist-app/assets/primary-RB5K54tJ.js` (sha256 `f4e9cb70…5508`) satır:sütun.

**Dürüstlük notları.** (1) Hak sahibinden izin alındığı kullanıcı beyanıdır; bağımsız doğrulanmış belge yoktur.
(2) REA, ASAR içindeki **8 companion dosyada bütünlük uyuşmazlığı** kaydetti (`@napi-rs/xattr-*` ×2,
`better-sqlite3-multiple-ciphers` ×2, `electron-click-drag-plugin` ×2, `keyspy/runtime/MacKeyServer`, `registry-js`;
`record-and-continue`). İncelenen JS dosyalarının hash'leri tutarlıdır, ama **paket özgünlüğü doğrulanmış sayılmaz.**
(3) Uygulama çalıştırılmadı; istem, Sistem Ayarları, TCC önbelleği ve görsel düzen gözlenmedi. Bu yüzden "benzer
deneyim" **akış ve sözleşme düzeyindedir**, piksel düzeyinde değil. (4) `setup-vmHe1Hio.js` izin dosyası **değildir**
(Hermes sohbet botu deposu, `03a` B0); izin ekranı `primary-RB5K54tJ.js` içindedir. Sınıflar: **statik** = kodda
doğrudan okundu, **çıkarım** = statik kanıttan akıl yürütme, **bilinmeyen** = kanıttan çıkmıyor.

| # | Granola bulgusu | Araç · dosya/hash · konum | Sınıf | Meeting OS karşılığı (dosya:sembol) |
|---|---|---|---|---|
| 1 | Tek ekran, üç satırlı kart: mikrofon, sistem sesi, (bayrakla) erişilebilirlik; satırda "Enable …" düğmesi, verilince "Enabled" rozeti | `03a` B3 · `primary` · `primary:477:179549`–`477:182775` | statik | `PermissionOnboardingView.swift:PermissionOnboardingView`, `PermissionCardView.swift:PermissionCardView/PermissionBadge`, `PermissionContract.swift:PermissionCardModel.make` |
| 2 | Adım sırası giriş → izin → takvim; izin adımının ölçütü yalnız mikrofon + sistem sesi, erişilebilirlik dışarıda | `03a` B1, B2 · `primary:146:21406`, `146:22093` | statik | `PermissionSnapshot.readyToRecord` ve `missingRequired` (`PermissionContract.swift`); `PermissionPolicy.shouldPresent` |
| 3 | Erişilebilirlik satırı varsayılan kapalı bayrakla gelir, gerekçe ipucu metni "daha iyi tanır" der (isteğe bağlılık açık) | `03a` B7 · `cache-B8uVNU4r.js` `cache:2:43181`; `primary:477:182775` | statik | `PermissionPolicy.need(.accessibility)` = `conditional`/`optional`; `PermissionCardModel.reason`. Meeting OS ayrıca **koddan** değerlendirdi: gereklilik (b) bölümünde (yalnız `ZoomMute`) |
| 4 | Erişilebilirlik yokken konuşmacı tespiti atlanır, kayıt sürer (`…speaker-detection-no-accessibility`) | `03b` C5 · `main/index.js` `L95:C18318`, `L95:C37808` | statik (sonuç: çıkarım) | `MicGate.state` + `meeting_os/cloud_finalize.py:844-847` (kapı hiç açılmadıysa iz atılmaz); bkz. (b) |
| 5 | Mikrofon: tıkla → istek → `true/false`; reddedilince yalnız toast, ekranda Ayarlar düğmesi yok | `03a` B4 · `primary:477:180746`, `probe:71:27550` | statik | **Bilerek ayrışır:** reddedilen mikrofonda kart "Sistem Ayarları'nı aç" düğmesi verir (`PermissionFlow.primaryAction`, `denied` → `openSettings`) |
| 6 | Mikrofon durumu sorgulanmaz, yalnız istek sonucu saklanır; `denied/restricted/notDetermined` ayrımı yok | `03b` D2, G · `L286:C92446` (yalnız Windows); `tcc.node`'da mikrofon servisi yok | statik | **Bilerek ayrışır:** durum istekten ayrı okunur, istemsiz: `LivePermissionProvider.status` → `microphoneStatus(AVAuthorizationStatus)`; 4 durum tam eşlenir (`PermissionStatus`) |
| 7 | Mikrofon isteği AVFoundation `requestAccess` (≥13 yerel süreçte), Ayarlar yolu `Privacy_Microphone` | `03b` D1, D3 · `L286:C121108`, `L286:C119171`; Ghidra `macos_audio_capture` `0x20998` | statik | `LivePermissionProvider.request(.microphone)` (yalnız `notDetermined` iken sorar), `PermissionKind.paneAnchor` |
| 8 | Sistem sesi: ikinci tıklamadan itibaren toast, üçüncüden itibaren kalıcı yardım bloğu + "Edit in System Settings" + "yeniden başlat" | `03a` B5 · `primary:477:181619`–`477:184245` | statik | `PermissionFlow.reduce` (`requestFinished` → `waitingForSettings`), `PermissionPresentation.settingsGuideText`, kart dipnotu; yardım bloğu sayacı yerine **durum** esaslıdır |
| 9 | Pane adı sürüme göre: "Screen & System Audio Recording" (core_audio açık) / "Screen Recording" | `03a` B5 · `primary:454:94476`; `03b` F1 (`Ky/qy/Jy` bayrakları) | statik | `PermissionSettingsLink.paneName/path(os:)` (macOS 15+ adı); alt sürümler `unsupported` (`PermissionPolicy.minimumOS`) |
| 10 | Sistem sesinde ayrı pane yok; Ekran Kaydı paneli (`Privacy_ScreenCapture`) açılır; `Privacy_AudioCapture` kodda yok | `03b` B2 · `main/index.js` içinde `Privacy_` geçen 6 yer | statik (sonuç: çıkarım) | `PermissionKind.paneAnchor` (`Privacy_ScreenCapture`). Meeting OS Core Audio tap kullanmaz (`ScreenCaptureKit`), bkz. (c) |
| 11 | İstek: macOS ≥14.2'de Core Audio tap'i kısa başlatarak, değilse `SCShareableContent` ile | `03b` B3 · Ghidra `0x20f60`, `0x2111c` | statik (SCK kolu: çıkarım) | **Ayrışır:** `CGRequestScreenCaptureAccess()` (`LivePermissionProvider.request(.systemAudio)`); özel SPI ya da tap yok |
| 12 | Durum için özel `TCC.framework` SPI'si (`TCCAccessPreflight`); `0→authorized, 1→denied`, gerisi `unknown` | `03b` B1 · Ghidra `tcc.node` `0x808` | statik | **Ayrışır:** yalnız herkese açık API: `CGPreflightScreenCaptureAccess` (`ScreenGrantMemory.resolve`), `AXIsProcessTrusted` (`ZoomMute.trusted`) |
| 13 | `unknown`/`process-error` sistem sesinde izinli sayılabilir (fail-open) | `03b` B4, G · `L22:C24641` (`enforce_tcc_system_audio_permission` varsayılan `false`) | statik | **Ters yön:** okunamayan durum asla "verildi" olmaz: `PermissionStatus.unknown` → rozet "Okunamadı", eylem "Yeniden kontrol et" |
| 14 | `restricted` (MDM) ayrımı hiçbir kanalda yok | `03b` G | bilinmeyen | `PermissionStatus.restricted` ("Yönetici kısıtlamış", eylem yok) — Meeting OS'a özgü; Granola'dan alınmadı |
| 15 | İzin sonrası "çık ve yeniden aç" beklentisi; Granola otomatik yeniden başlatmaz, panel yönlendirir | `03a` B5 (çıkarım) · `03b` B6, E3 · `L271:C2620` (`U1`), `L286:C129018` (`relaunch-app`) | statik / çıkarım | `ScreenGrantMemory.resolve` → `.needsRelaunch` **yalnız kanıtla** (istek + Ayarlar + dönüş + hâlâ kapalı); kart "Meeting OS'u yeniden aç"; kayıt sürerken reddedilir |
| 16 | Geri dönünce yeniden kontrol: `refetchOnWindowFocus`, 500 ms yoklama (erişilebilirlik); sistem sesi 1 sn, 120 sn sınır; kamera adımı focus + visibility | `03a` B8, B11, B12 · `time:1:5423`; `03b` B7 · `L278:C29689` (`gnt=1e3`, `_nt=12e4`) | statik | `PermissionFlowModel` (`NSApplication.didBecomeActiveNotification` → `returnedFromSettings`; zamanlayıcı `pollTick`), `PermissionPolicy.pollInterval = 1`, `pollLimit = 120` (`PermissionFlow.swift`) |
| 17 | Erişilebilirlik isteği: sistem istemi (`isTrustedAccessibilityClient(true)`) + Ayarlar'ı doğrudan açma; durum istemsiz (`AXIsProcessTrustedWithOptions`) | `03b` C1, C3 · `L30:C9775`, `L35:C46091`; Ghidra `0xbcc`, `0x28bb` | statik (istem değeri: çıkarım) | `LivePermissionProvider.request(.accessibility)` = `ZoomMute.requestTrust()` + `openSettings(.accessibility)`; durum `ZoomMute.trusted()` + `PermissionPromptLedger` (hiç sorulmadıysa `notDetermined` → "İzin iste" istemi çalıştırır; test `PermissionFirstAskTests`) |
| 18 | "Enable accessibility" sürükle-bırak yüzen panel, Ayarlar penceresinin köşesine oturur; verilince Sistem Ayarları'nı `SIGTERM` ile kapatır | `03a` B9 · `overlay:1:3885`; `03b` C4 · `L35:C46091`–`C49800` | statik (neden: çıkarım) | **Alınmadı:** yüzen pencere, pencere izleme ve başka uygulamayı kapatma yoktur. Yerine kart dipnotu yol tarif eder; Ayarlar'ı kapatmak kullanıcının işidir |
| 19 | Ayarlar URL'leri: yeni kimlik rehberli akışta, eski kimlik düz düğmede; erişilebilirlik için geri dönüş yok, ekran kaydı için `Security.prefPane` | `03b` B5, C3, D3, E2 · `L271:C1383`, `L286:C117599` | statik | `PermissionSettingsLink.candidates(_:os:)` (13+ yeni, sonra eski), sonra `fallbackURL(os:)`; hepsi yoksa `settingsOpenFailed` + elle yol (`PermissionSettingsOpener.openPane`) |
| 20 | Ayarlar açıldıktan sonra `open -b com.apple.systempreferences` ile öne alma | `03b` E1 · `L286:C117867` (`K9`) | statik | Alınmadı: `NSWorkspace.shared.open(url)` Ayarlar'ı zaten öne getirir (denenmedi) |
| 21 | Ana ekranda "Skip" yok; "Continue" mikrofon + sistem sesi gelmeden pasif; erişilebilirlik bir kez denendiyse "Continue anyway" | `03a` B6 · `primary:477:184730` | statik | **Ayrışır (ilke: kullanıcı ortada kalmaz):** `finish` her an mümkün; eksik zorunlu izin varsa `allRequiredGranted=false` kalır. İsteğe bağlı izin `skip` ile geçilir, rozet "· geçildi" der |
| 22 | Kamera adımı: reddedilmişse düğme istek yerine Ayarlar'ı açar; "Skip for now" ancak 2. denemeden sonra | `03a` B11 · `primary:494:12129`–`494:19764` | statik | `PermissionFlow.primaryAction` (`denied` → `openSettings`); kayıt izinleri için atlama zorunlu izinde sunulmaz |
| 23 | Durum tri-state (`undefined/true/false`); `undefined` iken uyarı gösterilmez | `03a` B8, B15 · `time:1:5423`, `primary:538:41610` | statik | `PermissionStatus.unknown` ayrı bir durumdur ve açıkça gösterilir (rozet "Okunamadı"); yanlış yeşil yok |
| 24 | Açılışta eski `true` kayıtlar sessizce yeniden istenir; izin deposu yalnız "istek sonucu" tutar | `03a` B13 · `probe:71:27780` | statik | **Kısmen alındı:** açılışta istem yok (`appear` yalnız `refresh`); kalıcı olanlar `permissionOnboardingCompletedVersion` ve uygulamanın istemi açıp açmadığı (`PermissionPromptLedger`, `permissionPromptAsked.<tür>`) — sorulmamış ekran/AX izni `notDetermined` okunur, ilk tıklama gerçek istemi çalıştırır |
| 25 | Toplantı içi sarı uyarı: "izin gerekli → Grant permission"; günlük sıklık sınırı ve kapatma | `03a` B14 · `portrait:164:27609`, `time:1:12610` | statik | Kayıt yönlendirmesi ve Ayarlar kartı (s5 entegrasyonu); Granola'daki öneri kartı sıklık sınırı alınmadı |
| 26 | Kayıt sürerken izin isteği yok sayılır (`…-while-capturing-mac`, `true`) | `03b` B4, D4 · `L36:C22711` | statik | `relaunch` kayıt varken reddedilir; kayıt başındaki `requestAccess` güvenlik ağı korunur (g) |

**Açık (kanıtlanmadı).** `watch-system-settings` yerel uygulaması, `accessibility_process`'in kütüphanesi,
`AXTrustedCheckOptionPrompt` değeri, `isPermissionRequest:1` bayrağı ve SCK kolunun başarı ölçütü incelenmedi
(`03b` H). Gerçek istem, "Kapat ve Yeniden Aç" sayfası, TCC önbellek gecikmesi ve Türkçe pane adları gözlenmedi.

## (b) Erişilebilirlik gerçekten gerekli mi? (koddan)

**Hayır, kayıt için gerekli değil.** Yalnız bir özelliğin ("Zoom'u izle" mikrofon kapısı) doğruluğunu artırır.

- Tek kullanıcısı `desktop/Sources/MeetingOS/ZoomMute.swift`. `ZoomMute.read()` zoom.us'un menü çubuğunda
  **Meeting / Toplantı** menüsünü bulur ve oradaki "Mute Audio / Unmute Audio" ("Sesi Kapat / Sesi Aç")
  satırını okur. Bunun için `AXIsProcessTrusted()` gerekir. İzin yoksa okuma `nil` döner. İsteme yolu
  `ZoomMute.requestTrust()` (`AXIsProcessTrustedWithOptions` + prompt).
- `MicGate.state` (`MicGate.swift`) yalnız `zoom` modunda `zoomMuted` değerine bakar: `zoomOpen && zoomMuted==false`.
  `manual` ve `always` modları bu değeri hiç okumaz. `nil` (izin yok) "kapalı" sayılır ve kapı açılmaz.
- Kapı hiç açılmamışsa ses kaybolmaz: `meeting_os/cloud_finalize.py:844-847` şöyle der: "A gate that never
  opened once is not a gate… The track is only discarded on evidence the gate was really watched AND closed."
  İzin olmayan bir Mac'te Zoom modunda bütün mikrofon izi yazıya çevrilir (KULLANIM 1.2.87). Kaybedilen tek şey
  sessizdeyken konuşulanların ayıklanmasıdır. Bir istisna var: kullanıcı ⌃⌥V ile kapıyı elle açarsa kapı
  "izlenmiş" sayılır ve kapalı geçen parçalar düşer. Bu, bugünkü davranışla aynıdır.
- Kısayollar bu izne bağlı değildir. `QuickControl.swift` `import Carbon.HIToolbox` ve `RegisterEventHotKey`
  kullanır. Satır 73'teki yorum: "need no Accessibility grant". Uygulamada başka hiçbir `AX*` çağrısı yoktur:
  `grep AXIsProcess` yalnız `ZoomMute.swift` sonucunu verir.
- Bu nedenle `PermissionPolicy.need(.accessibility)` şöyle tanımlıdır: `zoom` modunda (bilinmeyen mod da `zoom`
  sayılır) **`conditional`** ("“Zoom'u izle” modunda gerekli"), `manual`/`always` modlarında **`optional`**.
  Hiçbir zaman `required` olmaz. Eksik olması tamamlanmayı ve kaydı engellemez. Kartın gerekçe metni bunu açıkça
  yazar: yalnız menü satırı okunur, tuş vuruşu ya da ekran okunmaz, kısayollar izinsiz de çalışır. Zoom modunda
  izin yoksa ses kaybolmaz, tamamı kaydedilir. Diğer modlarda izin isteğe bağlıdır. Kartta her zaman gerçek bir
  eylem bulunur: `request` (macOS istemi + Sistem Ayarları), `openSettings` ya da isteğe bağlıysa `skip`.

**İlk istek: "henüz sorulmadı" defteri.** Ekran kaydı ve Erişilebilirlik için macOS'ta üç durumlu bir API yoktur;
`CGPreflightScreenCaptureAccess()` ve `AXIsProcessTrusted()` yalnız `Bool` döner. Hiç sorulmamış bir Mac ile "hayır"
demiş bir Mac aynı `false` değerini verir. Bu değeri `denied` saymak her yeni kullanıcıyı doğrudan Sistem Ayarları'na
gönderiyordu; oysa Meeting OS'u o listeye ekleyen tek şey istem çağrısının kendisidir (`CGRequestScreenCaptureAccess`,
`AXIsProcessTrustedWithOptions` + prompt). Bu yüzden uygulama kendi sorduğunu hatırlar (`PermissionPromptLedger`,
`UserDefaults` anahtarı `permissionPromptAsked.<tür>`; `PermissionService.swift`):
- izin açık → `authorized` (defterden bağımsız);
- kapalı ve uygulama hiç sormadı → `notDetermined` → kart "Henüz sorulmadı" + **"İzin iste"**; tıklama gerçek istemi
  çalıştırır (`LivePermissionProvider.request`). Erişilebilirlikte ardından pane de açılır; sistem sesinde
  macOS'un kendi istemi Ayarlar düğmesini taşıdığı için uygulama onunla yarışmaz, ama bekleme kartında ikincil
  "Sistem Ayarları'nı aç" hep vardır (istem daha önce yardımcı tarafından gösterilmişse kullanıcı ortada kalmaz);
- kapalı ve sorulmuş → `denied` → "Sistem Ayarları'nı aç"; istem bir daha çağrılmaz.
Defter yalnız "uygulama istemi açtı mı" bilgisini tutar; TCC okunmaz. Altı sistem çağrısı `PermissionSystemCalls`
ile enjekte edilir; testler bu yolu gerçek `LivePermissionProvider` + sahte çağrılarla sürer (`PermissionFirstAskTests`).
Granola karşılığı: satır 24 (izin deposu istek sonucunu tutar) ve satır 17 (istem + Ayarlar).

## (c) Mikrofon ve sistem sesi: zorunlu

Bir kayıt iki ayrı ses izinden oluşur. İkisi de `required` sayılır (`PermissionSnapshot.readyToRecord`).

**Hangi süreç izinden sorumlu?** Kaydı uygulama başlatır: önce `Process` ile Python (`meeting_os`) çalışır,
o da `meeting_os/live.py:140` içinde `subprocess.Popen` ile `MeetingCapture` yardımcısını başlatır. TCC izni
"sorumlu uygulamaya" (`local.boran.meeting-os`) aittir (`docs/MACOS_PERMISSIONS.md`). Bu yüzden uygulamanın
kendi okuduğu durum, yardımcının kullanacağı izinle aynıdır. Terminal'den başlatılan bir test bunu doğrulamaz.

**Mikrofon.** Uygulamadaki `AVCaptureDevice.authorizationStatus(for:.audio)` değerinin karşılıkları:
`.notDetermined` → `notDetermined`, `.denied` → `denied`, `.restricted` → `restricted`, `.authorized` → `authorized`.
İstek `AVCaptureDevice.requestAccess`. Bu, uygulama içinde cevaplanan tek istemdir; `completion` kullanıcının
cevabını getirir. Pane: `Privacy_Microphone`.

**Sistem sesi.** Yardımcı `SCShareableContent` ve `SCStream` ile çalışır (`capture/.../main.swift:300-315`,
`capturesAudio`, `captureMicrophone`). macOS sistem sesini Ekran Kaydı iznine bağlar. Ekran görüntüsü
saklanmaz (2×2 piksel, 1 fps). Durum `CGPreflightScreenCaptureAccess()` ile okunur (istem açmaz), istek
`CGRequestScreenCaptureAccess()` ile yapılır. İstek hemen döner ve kullanıcıyı Sistem Ayarları'na yönlendirir.
Bu yüzden `PermissionKind.grantedInSettings` değeri doğrudur: istek bittikten sonra akış `waitingForSettings`
durumuna geçer ve yoklar. Core Audio process tap (`kTCCServiceAudioCapture`, "Yalnız sistem sesi kaydı" listesi)
**kullanılmaz** (`grep AudioHardwareCreateProcessTap` sonuç vermez). Meeting OS üstteki ekran+ses listesinde olmalıdır.

| macOS | Pane adı (kartta) | URL (13+: önce `…settings.PrivacySecurity.extension?<anchor>`, sonra bu) | Not |
|---|---|---|---|
| ≤12 | Sistem Tercihleri → Güvenlik ve Gizlilik → Gizlilik → Ekran Kaydı | `…preference.security?Privacy_ScreenCapture` | Desteklenmez (uygulama 15+). SCK ses 13+ olduğu için sistem sesi `unsupported` olur. |
| 13 | Sistem Ayarları → Gizlilik ve Güvenlik → Ekran Kaydı | aynı | Desteklenmez (uygulama 15+). |
| 14 | Sistem Ayarları → Gizlilik ve Güvenlik → Ekran Kaydı | aynı | Desteklenmez (uygulama 15+). |
| 15+ (26 dahil) | Sistem Ayarları → Gizlilik ve Güvenlik → **Ekran ve Sistem Sesi Kaydı** | aynı | Desteklenen tek sürüm. Pane iki listeye ayrılır. |

- Uygulamanın desteklediği en düşük sürüm **macOS 15.0**'dır: `Package.swift`, `LSMinimumSystemVersion` ve
  yardımcının `captureMicrophone` özelliği bunu gerektirir. `PermissionPolicy.minimumOS` bu değeri taşır. 13/14
  satırları yalnız `paneName`/`path` metinlerinin ve `unsupported` mantığının doğru olması için tutulur.
- İki biçim denenir (`PermissionSettingsLink.candidates`): macOS 13+ için önce
  `x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?<anchor>`, sonra eski
  `x-apple.systempreferences:com.apple.preference.security?<anchor>` (uygulama bunu 1.0'dan beri kullanır,
  `SetupStatus.openPane`). Granola da iki kimliği birlikte kullanır (`03b` B5). Her macOS sürümünde doğru pane'e indiği bu adımda
  ayrıca denenmedi (gerçek Ayarlar açılmaz).
  Anchor'lar: `Privacy_Microphone`, `Privacy_ScreenCapture`, `Privacy_Accessibility`. Geri düşüş (g) bölümündedir.
- macOS'un Türkçe arayüzündeki pane adları (özellikle "Ekran ve Sistem Sesi Kaydı") gerçek bir Mac'te **gözle
  doğrulanmadı**. Ayrıca macOS 15'in ScreenCaptureKit uygulamalarından dönemsel olarak yeniden onay isteyip
  istemediği ve bunun sıklığı **bilinmiyor**. Kanıt adımı ya da sürüm QA'sı netleştirmelidir.

**`needsRelaunch` nereden gelir?** `CGPreflightScreenCaptureAccess()` izin verildikten sonra da süreç yeniden
açılana kadar `false` dönebilir. macOS bu yüzden "Çık ve Yeniden Aç" önerir. Yalın bir `false` değerinden
"aslında verildi" sonucu **çıkarılmaz**:
- Sağlayıcı `needsRelaunch` değerini **yalnız kanıt varsa** döndürür. Örnek: yardımcının günlüğünde son kayıtta
  `{"event":"permission","kind":"screen_audio","state":"granted"}` görülmüş, uygulamanın preflight'ı ise hâlâ
  `false`. Bu durumda kartın birincil eylemi `relaunch` olur.
- Kanıt yoksa reducer şu durumda yalnız **öneri** ekler (`relaunchSuggested`): kullanıcı sistem sesi için
  Ayarlar'dan döndü ve durum hâlâ kapalı. Rozet "Sistem Ayarları'nda bekleniyor…" ya da "Kapalı" olarak kalır.
  İkincil düğme "Meeting OS'u yeniden aç" olur. Gerçek bir izin geldiğinde öneri kendiliğinden kalkar.
- Yardımcı her kayıtta yeni bir süreçtir. Bu yüzden uygulamanın preflight'ı eski kalsa bile yardımcı izni
  görebilir. Bu **çıkarımdır ve denenmedi**. Yeniden açma bu yüzden zorunlu değil, önerilen bir eylemdir.

## (d) Durum makinesi

Sözleşmedeki durumlar `PermissionFlowPhase`: `idle → active ⇄ requesting / waitingForSettings → finished`. Olaylar:
`appear`, `primaryTapped(kind)`, `requestFinished(kind,status)`, `returnedFromSettings`, `pollTick`, `skip(kind)`,
`finish`, `reopen`. Bunlara ek olarak `refreshed(snapshot)`, `actionTapped(action,kind)` ve
`settingsOpenFailed(kind)` vardır. Reducer yan etki yapmaz. Sürücünün yapacağı işleri `state.effects` içine yazar:
`refresh`, `request(k)`, `openSettings(k)`, `relaunch`, `persistCompletion`.

| Olay | Sonuç |
|---|---|
| `appear` | `idle` → `active`, `refresh` |
| `primaryTapped(k)` | o anki birincil eylem `actionTapped` olarak işlenir. `requesting` sırasında yok sayılır (aynı anda tek macOS sorusu) |
| `request` | `requesting`, `pending=k`, efekt `request(k)` |
| `requestFinished(k,st)` | durum her zaman kaydedilir (geç gelen cevap da kanıttır). `pending==k` ise: izin verildiyse `active`; ekran/AX ise `waitingForSettings` + yoklama; mikrofon reddedildiyse `active` + `requestDenied` notu. Efekt: `refresh` |
| `openSettings` | `waitingForSettings`, `pollsLeft=pollLimit`, efekt `openSettings(k)` |
| `pollTick` | yalnız yoklama sürerken: `pollsLeft-1`, `refresh` |
| `returnedFromSettings` | her durumda `refresh`. Bekleniyorsa `returnedFromSettings=true` |
| `refreshed(s)` | snapshot güncellenir. `pending` verildiyse (ya da kısıtlıysa veya `needsRelaunch` ise) bekleme biter. Sistem sesi için dönüldüyse ve hâlâ kapalıysa `relaunchSuggested` eklenir. `pollsLeft==0` ise bekleme biter ve `noChangeSeen` notu düşülür |
| `settingsOpenFailed(k)` | bekleme biter, `settingsUnavailable` notu (elle izlenecek yol yazılır) |
| `skip(k)` | `skipped`'e eklenir. Bekleniyorsa yoklama durur. Rozet gerçek durumu "· geçildi" ekiyle gösterir |
| `finish` | `finished`, yoklama durur, efekt `persistCompletion`. Eksik zorunlu izin varsa da bitirilebilir, ama `allRequiredGranted=false` kalır ve Ayarlar kartı kırmızıyı gösterir |
| `reopen` | `active`, `skipped` temizlenir, `refresh`. Kaydedilmiş tamamlanma bilgisi silinmez |

Odak (`focus`) şu sırayla ilk "yapılacak" izindir: mikrofon → sistem sesi → Erişilebilirlik. Verilen, geçilen ve
sistemce kilitli (`restricted`/`unsupported`) izinler odak almaz. Odak `nil` ise "Bitti" sunulur.

**Kart metni, rozet ve eylem** (`PermissionCardModel.make`; tonlar: success/waiting/warning/error/neutral):

| Durum | Rozet | Ton | Birincil | İkincil | Dipnot |
|---|---|---|---|---|---|
| authorized | İzin verildi | success | — | — | — |
| notDetermined | Henüz sorulmadı | neutral | İzin iste | isteğe bağlıysa Şimdilik geç | — |
| denied | Kapalı | gerekliyse error, değilse warning | Sistem Ayarları'nı aç | isteğe bağlıysa Şimdilik geç, değilse Yeniden kontrol et | "<yol> içinde Meeting OS'u açın." |
| restricted | Yönetici kısıtlamış | gerekliyse error | — | — | "…cihaz yönetimi tarafından kilitlenmiş; BT yöneticinize başvurun." |
| unknown | Okunamadı | warning | Yeniden kontrol et | isteğe bağlıysa Şimdilik geç | "Durum okunamadı…" |
| unsupported | Bu macOS'ta yok | neutral | — | — | "Meeting OS macOS 15 ve sonrasını gerektirir." |
| needsRelaunch | Yeniden açılış gerekiyor | warning | Meeting OS'u yeniden aç | — | "…yeniden açılınca uygular. Kayıt sürerken yeniden açılmaz." |
| (requesting) | macOS soruyor… | waiting | — | — | — |
| (waitingForSettings) | Sistem Ayarları'nda bekleniyor… | waiting | Yeniden kontrol et | Sistem Ayarları'nı aç / öneri varsa yeniden aç | "<yol> içinde anahtarı açın; listede yoksa + ile ekleyin. Döndüğünüzde kendiliğinden kontrol edilir." |
| (geçildi) | <gerçek durum> · geçildi | neutral | gerçek eylem kalır | — | — |

Başlık ve gerekçe metinleri izne göre değişir:
- **Mikrofon** (Gerekli): "Toplantıda kendi sesinizi kaydetmek için gerekir. Mikrofon yalnız kayıt sürerken kullanılır."
- **Sistem sesi (karşı tarafın sesi)** (Gerekli): "Karşı tarafın sesi (Zoom'dan hoparlöre giden ses) macOS'ta
  yalnız bu izinle alınabilir. Ekran görüntüsü alınmaz, saklanmaz."
- **Erişilebilirlik (Zoom'daki sessiz durumu)** ("“Zoom'u izle” modunda gerekli" ya da "İsteğe bağlı"):
  metin (b) bölümündedir.

## (e) Tetikleme kuralları

- `request` ve `openSettings` **yalnız kullanıcı tıklamasıyla** çalışır. Bunlar `primaryTapped` ve
  `actionTapped` olaylarıdır. `appear`, `reopen`, `returnedFromSettings` ve `pollTick` hiçbir zaman istem açmaz
  ya da Ayarlar'ı açmaz; yalnız `refresh` üretir. Uygulama açılışında, kayıt başında ya da arka planda istem yoktur.
- Kontrol iki yoldan yinelenir. (1) Uygulama yeniden aktif olunca (`NSApplication.didBecomeActiveNotification`)
  sürücü `returnedFromSettings` gönderir. (2) Akış `waitingForSettings` durumundayken (`state.isPolling`) sürücü
  her `PermissionPolicy.pollInterval` (1 sn) bir `pollTick` gönderir, en çok `pollLimit` (120) kez. Sınır dolunca,
  izin gelince, geçilince ya da bitirilince zamanlayıcı durur. Açık unutulan bir pane arkada zamanlayıcı bırakmaz.
- `status` okumaları ucuzdur ve istem açmaz. `ZoomMute.read` gibi engelleyici AX gezintisi yoklamaya girmez;
  yalnız `AXIsProcessTrusted()` okunur.
- `relaunch` yalnız kayıt yokken uygulanır. Sürücü `recording` ya da `recordProcess != nil` iken bunu reddeder
  ve kullanıcıya nedenini söyler.

## (f) Tamamlanma ve yeniden açma

- `finish` → efekt `persistCompletion` → sürücü `UserDefaults.standard` içine
  `permissionOnboardingCompletedVersion = PermissionPolicy.onboardingVersion` (şimdilik 1) yazar.
- Gösterim kuralı: `PermissionPolicy.shouldPresent(storedVersion:snapshot:)`. Saklanan sürüm güncelden küçükse
  **ve** zorunlu izinlerden biri eksikse gösterilir. Zaten kayıt yapan bir Mac'e tur gösterilmez. Yeni bir izin
  ya da yeniden yazılmış bir adım eklendiğinde `onboardingVersion` artırılır.
- Yeniden açma: **Ayarlar → Sistem → "İzin kurulumunu yeniden aç"**. Bu, `reopen` olayıdır: geçilenler temizlenir,
  durumlar yeniden okunur, kaydedilmiş tamamlanma silinmez. Kurulum durumu kartındaki eski izin satırları da
  aynı `PermissionCardModel` metnini kullanmalıdır, böylece iki yer aynı durumu farklı sözlerle anlatmaz.

## (g) Hata kurtarma

- **URL açılamazsa:** sağlayıcının `openSettings(k)` adımı (`PermissionSettingsOpener.openPane`) önce
  `PermissionSettingsLink.candidates` listesini sırayla dener (13+: yeni, eski), sonra
  `PermissionSettingsLink.fallbackURL(os:)` genel Gizlilik adresine geri düşer: 13+ için
  `x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension`, eski sürümlerde
  `…preference.security?Privacy`. İkisi de açılmazsa `false` döner. Sürücü bunun üzerine `settingsOpenFailed`
  gönderir ve kart elle izlenecek yolu yazar ("Sistem Ayarları açılamadı. Elle açın: Sistem Ayarları →
  Gizlilik ve Güvenlik → …"). Yoklama başlamaz, kullanıcı beklemede kalmaz.
- **Ayarlar'da değişiklik yok:** `pollLimit` dolunca `noChangeSeen` notu gösterilir. Kart "Yeniden kontrol et"
  düğmesiyle kullanılabilir kalır.
- **Okunamayan durum:** `unknown` için birincil eylem "Yeniden kontrol et"tir; hiçbir zaman "verildi" denmez.
- **Yardımcının `requestAccess` kararı:** `MeetingCapture` (`main.swift:295`) her kayıtta
  `AVCaptureDevice.requestAccess(for:.audio)` çağırmaya **devam eder**; değiştirilmez. Nedenleri:
  (1) İzin uygulamaya aittir. Onboarding'de verilmişse çağrı istem açmadan hemen `true` döner.
  (2) Onboarding'i geçen yeni bir Mac'te istem kayıt başında çıkar. Bu durum zaten ele alınıyor: yardımcı
  `permission requested/granted/denied` olaylarını yazar, `CaptureSessionState` bunu `awaitingPermission`
  ("İzin bekleniyor · macOS sorarsa ‘İzin Ver’i seçin") olarak gösterir ve bu sırada süre ile stall saati
  işlemez (`live.py:62`). (3) Reddedilen izin yardımcıda anlamlı bir hatayla sonlanır ve uygulamada Türkçe
  yönlendirmeye dönüşür. Onboarding bu istemi kayıttan **önceye** taşır; güvenlik ağını kaldırmaz.

## (h) Test stratejisi

- **Gerçek TCC yok.** Testler `PermissionProviding` protokolüne uyan bir sahte sağlayıcı ve sentetik
  `PermissionSnapshot` geçişleri kullanır. İzin istemi açılmaz, Sistem Ayarları açılmaz, TCC veritabanı ya da
  gerçek `UserDefaults` okunmaz. macOS sürümü `OperatingSystemVersion` olarak enjekte edilir (12/14/15 dalları).
- `PermissionContractTests`: notDetermined→request→authorized; denied→openSettings→poll→returned→authorized;
  sistem sesi isteği → Ayarlar'da bekleme → dönüş → yeniden açma önerisi (rozet yeşil olmaz); pollLimit sonu;
  mikrofon istemi reddi; isteğe bağlı Erişilebilirlik'i geçme (rozet "Kapalı · geçildi"); beklerken geçme;
  finish + reopen; Ayarlar açılamadı; restricted/needsRelaunch; geç gelen cevap; mod → need; macOS'a göre
  pane/URL; `shouldPresent`; sahte sağlayıcıyla uçtan uca sürücü döngüsü.
- `PermissionFirstAskTests`: gerçek `LivePermissionProvider`, sahte `PermissionSystemCalls`, geçici `UserDefaults`.
  Hiç sorulmamış Erişilebilirlik → kart "İzin iste" → tıklama `accessibilityRequest` (istem) + Erişilebilirlik pane'i
  → bekleme → dönüşte "İzin verildi"; sorulmuş-kapalı → yalnız Ayarlar, istem tekrar yok; hiç sorulmamış sistem sesi →
  tıklama `screenRequest` (`CGRequestScreenCaptureAccess`) → bekleme + ikincil Ayarlar → `denied`; `needsRelaunch`
  kanıt zinciri; mikrofon yalnız `notDetermined` iken sorar; `SetupStatus.fixPermission` da istemlere ulaşır.
  Tıklama, kartın düğmesinin gönderdiği olayla (`.actionTapped`) yapılır: onboarding ve Ayarlar → Sistem aynı yolu kullanır.
- Hedefli koşturma: `cd desktop && swift build && swift test --filter Permission` (82 test, 0 hata; 16 Ekim 2026).
- Son doğrulama (16 Ekim 2026, bu ağaç): `cd desktop && swift build && swift test` → "Executed 473 tests, with 0
  failures"; `cd capture && swift build && swift test` → "Build complete!", "Executed 4 tests, with 0 failures".
  Python tam paketi (`MEETING_OS_TEST_IGNORE_PRESSURE=1 .venv/bin/python -m unittest discover -s tests`) bu işte
  Python değişmediği için worker tarafından koşulmadı; teslimden hemen sonra JEV aynı ağaçta koşar.
- Native sağlayıcının eşlemeleri (AVAuthorizationStatus → PermissionStatus; ekran/AX `false` → sorulmadıysa `notDetermined`, sorulduysa `denied`) saf yardımcı
  fonksiyonlara çıkarılıp ayrıca test edilir. SwiftUI kartları `PermissionCardModel` üzerinden test edilir;
  UI testi yoktur. Görsel kontrol gerekirse fixture render ile yapılır, gerçek uygulama açılmaz.
