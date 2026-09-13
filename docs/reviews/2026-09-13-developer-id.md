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
- `xcrun notarytool history --keychain-profile meetingos --output-format json`
  başarılı: `{"history":[],"message":"No submission history."}`.
- Noterleme betiğindeki hata kodlarını gizleyen borular kaldırıldı. Başarı için
  JSON sonucunda tam `Accepted`, imza, staple ve Gatekeeper doğrulaması gerekir.
- Developer ID seçilen yerel derlemeler için güvenli zaman damgası ve hardened
  runtime desteği hazırlandı; eski geliştirme imzasının davranışı korunur.
- Birleşik imzalama takımı: 15 test başarılı; noterleme kısmı 18 çevrimdışı
  senaryoyu içerir. Shell sözdizimi ve `git diff --check` temiz; bağımsız kod
  incelemesinde engel bulunmadı. Testlerde gerçek sertifika veya anahtar zinciri
  kullanılmadı.

## Kalan hesap adımı

Geçerli kod imzalama kimliklerinde yalnız `Apple Development` var. Kurulu
uygulamanın gerçek `TeamIdentifier` değeri `WHA43MLZN6`. Developer ID Application
sertifikası henüz edinilmedi; uygulamanın imzası ve kayıtlı kimlik bu nedenle
henüz değiştirilmedi. Apple Developer sekmesi oturum açmayı bekliyor;
Xcode → Apple Accounts ekranında da kayıtlı hesap bulunmuyor.

Sertifika edinildikten sonra aynı CSR'nin anahtarıyla eşleşmesi doğrulanmalı,
sertifika login anahtar zincirine kurulmalı, eski pin yedeklenerek seçilen
Developer ID SHA-1'e geçilmeli ve hem ana uygulama hem kayıt yardımcısı yeniden
imzalanmalıdır. Sonuç `codesign --verify --deep --strict`, gerçek
`Authority`/`TeamIdentifier` ve noterleme sonucu üzerinden doğrulanmalıdır.
Gerçek imza/noterleme tamamlanmadan bu belge tamamlanmış geçiş kanıtı değildir.

## Kaynaklar

- [Apple: Developer ID sertifikaları](https://developer.apple.com/help/account/certificates/create-developer-id-certificates)
- [Apple: Sertifika API'sinin Developer ID sınırlaması](https://developer.apple.com/documentation/appstoreconnectapi/certificates)
- [Apple: Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime)
