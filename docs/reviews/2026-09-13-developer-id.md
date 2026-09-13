# Developer ID geçişi — 13 Eylül 2026

Amaç: Meeting OS ve kayıt yardımcısını kullanıcının Developer ID Application
sertifikasıyla imzalamak; sonraki derlemelerde aynı kimliği ve doğru imza
seçeneklerini korumak.

## Tamamlanan hazırlık

- Claude Code'un sertifika hazırlığı ve son devir notları kontrol edildi.
  Hazır CSR'nin öz-imzası doğrulandı ve özel anahtarla eşleştiği görüldü.
- CSR ve özel anahtar, içerikleri günlüğe yazılmadan, `0600` izinli kalıcı
  yedeklere alındı: `~/.appstoreconnect/developer-id-application.csr` ve
  `~/.appstoreconnect/developer-id-application.key`.
- Noter API bilgileri Apple tarafından doğrulandı. `meetingos` profili açıkça
  kullanıcının `login` anahtar zincirine kaydedildi; varsayılan anahtar zinciriyle
  ilk deneme kullanıcı etkileşimine izin vermediği için başarısız olmuştu.
- Noter profili sorgusu başarılı. Anahtar zincirinin geçici erişim hataları
  nedeniyle gönderimde `login.keychain-db` yolu açıkça belirtildi; erişim
  izinleri genişletilmedi.
- Noterleme betiğindeki hata kodlarını gizleyen borular kaldırıldı. Başarı için
  JSON sonucunda tam `Accepted`, imza, staple ve Gatekeeper doğrulaması gerekir.
- Developer ID seçilen yerel derlemeler için güvenli zaman damgası ve hardened
  runtime desteği hazırlandı; eski geliştirme imzasının davranışı korunur.
- Birleşik imzalama takımı: 15 test başarılı; noterleme kısmı 18 çevrimdışı
  senaryoyu içerir. Shell sözdizimi ve `git diff --check` temiz; bağımsız kod
  incelemesinde engel bulunmadı. Testlerde gerçek sertifika veya anahtar zinciri
  kullanılmadı.

## Kurulan Developer ID kimliği

Kullanıcının Apple Developer web oturumuyla G2 Developer ID Application
sertifikası oluşturuldu; CSR, özel anahtar ve sertifikanın açık anahtarları
eşleşti. Sertifika ve anahtar `login` anahtar zincirine kuruldu.

- Kimlik: `Developer ID Application: BORAN KARADUMAN (WHA43MLZN6)`
- SHA-1: `7DF7783FCA518AD2D6E141EB977F3334EBDE064B`
- TeamIdentifier: `WHA43MLZN6` (önceki uygulamayla aynı ekip)
- Apple sertifika kimliği: `3K2QWQ3Y83`
- Son geçerlilik: `2031-09-14T19:18:16Z`
- Sertifika yedeği: `~/.appstoreconnect/developer-id-application.cer`

Kurulu `build/Meeting OS.app` ve `build/MeetingCapture.app` yeniden imzalandı.
Her ikisinde `codesign --verify --deep --strict` başarılı; Developer ID
otoritesi, ekip, güvenli zaman damgası ve hardened runtime doğrulandı.
Ana uygulama yalnız mikrofon/takvim, yardımcı yalnız mikrofon entitlement'ı
taşıyor. `build/signing-identity.json` yeni SHA-1'e sabitlendi.

Kurulu 1.2.87 sürümünün mevcut ikilileri kullanıldı. `Info.plist`, kaynaklar ve
kaynak deposuna/.venv'ye işaret eden `runtime.json` korundu;
`build/installed-commit` bu nedenle `ab9679f` olarak kaldı. Aktif kayıt ve
işleme işi olmadığı doğrulandı, uygulama kapatılıp imzalı kopyalar kuruldu ve
yeniden açıldığında arayüzde Hazır durumu görüldü. Yardımcının `--self-test`
kontrolü sentetik sesle başarılı; gerçek mikrofon/sistem sesi kaydı yapılmadı.

Önceki iki uygulama, imzalama kaydı ve sürüm işaretinin tam yedekleri ile
doğrulama çıktıları `build/developer-id-migration-20260913/` altında tutuluyor.

## Bekleyen Apple noter sonucu

İmzalı iki uygulama birlikte Apple noter servisine gönderildi:

- Başvuru: `77756197-79e4-415e-aedb-99de763dda03`
- Dosya: `meetingos-developer-id.zip`
- Gönderim: `2026-09-13T19:30:46.315Z`
- Son sorgu: **In Progress**; henüz Accepted veya noter onay bileti yok.

Yerel Developer ID kurulumu tamamlandı. Noter onayı için başvurunun Accepted
olması, iki uygulamaya `stapler staple` uygulanması, ardından `stapler validate`
ve Gatekeeper değerlendirmesinin başarılı olması bekleniyor. Bu belge şu an
noter onayının tamamlandığına dair kanıt değildir.

## Kaynaklar

- [Apple: Developer ID sertifikaları](https://developer.apple.com/help/account/certificates/create-developer-id-certificates)
- [Apple: Sertifika API'sinin Developer ID sınırlaması](https://developer.apple.com/documentation/appstoreconnectapi/certificates)
- [Apple: Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime)
