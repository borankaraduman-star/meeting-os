# Meeting OS — bütün sürüm notları

Bu dosya `scripts/changelog-index.py` ile üretilir (GitHub sürüm notları + `docs/releases/*.md`). 72 sürüm, en yeni en üstte. Diğer günlükler:

- [Sürüm günlüğü (canlı sayfa: kurul turları, sprint durumu, bütün sürümler)](https://claude.ai/code/artifact/ed7b851a-164d-4631-9322-e1bd84920425)
- [GitHub sürümleri (her etiketin notu ve kaynak paketi)](https://github.com/borankaraduman-star/meeting-os/releases)
- [docs/CHANGELOG.md (bu dosya: bütün sürüm notları tek yerde)](CHANGELOG.md)
- [docs/AUTONOMY_2026-09-10.md (10 Eylül gece/gündüz özeti: sürüm tablosu, kök nedenler, canlı denenmeyenler, kararlar)](AUTONOMY_2026-09-10.md)
- [docs/AUTONOMY_2026-09-09.md (9 Eylül gece turu)](AUTONOMY_2026-09-09.md)
- [docs/ITERATION_CHECKPOINT.md (zaman damgalı çalışma notları, en yeni en altta)](ITERATION_CHECKPOINT.md)
- [docs/NIGHT_ITERATION.md (8 Eylül gece turu, yerel model dönemi)](NIGHT_ITERATION.md)
- [docs/TURKISH_PRECISION_CHECKPOINT.md · ASR_CHECKPOINT_PLAN.md · DIARIZATION_CHECKPOINT_PLAN.md (8–9 Eylül yerel ASR/diarization deneyleri; bulut yoluna geçildi)](TURKISH_PRECISION_CHECKPOINT.md)
- [Öğleden sonra günlüğü artefaktı (9 Eylül, 1.2.15–1.2.24)](https://claude.ai/code/artifact/bcf01c8b-0ee0-4a10-beb9-0bf08fcde922)
- [Boru hattı artefaktı (9 Eylül: kayıt → transkript → analiz şeması)](https://claude.ai/code/artifact/198c0af2-ed36-4f09-8cd8-5d10a22abb37)
- [Kullanım kılavuzu artefaktı (docs/KULLANIM.md görünümü)](https://claude.ai/code/artifact/add1379b-ccdb-4ae4-9f45-87982d385627)

## Dizin

| Sürüm | Tarih | Başlık |
|---|---|---|
| [v1.2.67](#v1267) | 2026-09-10 23:10 | v1.2.67 — Ekip bulutu: sıfır kurulumlu ortak bilgi tabanı; her düzeltme öğrenir |
| [v1.2.66](#v1266) | 2026-09-10 22:21 | Meeting OS 1.2.66 — "Ekip klasörü" satırı: paylaşım nereye gidiyor, gitmiyorsa neden |
| [v1.2.65](#v1265) | 2026-09-10 22:03 | Meeting OS 1.2.65 — ekipteki hata ve çökmeler tek yerde toplanır |
| [v1.2.64](#v1264) | 2026-09-10 21:51 | Meeting OS 1.2.64 — Kontrol'de onaylanan sözlük düzeltmesi bir daha sorulmaz |
| [v1.2.63](#v1263) | 2026-09-10 21:45 | Meeting OS 1.2.63 — ekip klasörü ortak bilgi tabanı: profiller ve kelimeler herkeste birikir |
| [v1.2.62](#v1262) | 2026-09-10 21:34 | Meeting OS 1.2.62 — ekran paylaşırken göze batmaz |
| [v1.2.61](#v1261) | 2026-09-10 21:19 | Meeting OS 1.2.61 — konuşma payı yine gözünüzün önünde |
| [v1.2.60](#v1260) | 2026-09-10 21:16 | Meeting OS 1.2.60 — ekran kaydı izni neden isteniyor, kartta yazıyor |
| [v1.2.59](#v1259) | 2026-09-10 21:10 | Meeting OS 1.2.59 — ortalı boş durumlar, her sayfada ✕, Geri düğmesi |
| [v1.2.58](#v1258) | 2026-09-10 20:50 | Meeting OS 1.2.58 — tıkla-düzelt ve Özet'e ikinci görüş düzeltmeleri |
| [v1.2.57](#v1257) | 2026-09-10 20:47 | Meeting OS 1.2.57 — soldaki listede çöp kutusu; 1–2 saniyelik seslere isim istenmez |
| [v1.2.56](#v1256) | 2026-09-10 20:38 | Meeting OS 1.2.56 — kelimeye tıkla düzelt, temiz Özet, soldan sil; kelime öğrenme güvenli |
| [v1.2.55](#v1255) | 2026-09-10 19:57 | Meeting OS 1.2.55 — temizlik: doğru belgeler, tam köprü, tek kural |
| [v1.2.54](#v1254) | 2026-09-10 19:26 | Meeting OS 1.2.54 — 2 saatlik toplantı: kayıp yok, disk dürüst, arayüz tembel |
| [v1.2.53](#v1253) | 2026-09-10 19:12 | Meeting OS 1.2.53 — kelimeyi bir kez düzelt, uygulama öğrensin |
| [v1.2.52](#v1252) | 2026-09-10 18:45 | Meeting OS 1.2.52 — kıyas seti mikrofon sahibi yolunu da sınıyor |
| [v1.2.51](#v1251) | 2026-09-10 18:32 | Meeting OS 1.2.51 — maske adınızı yine gizler, kopya birleştirme vadeleri ayırır, yeniden analiz onaylı vadeyi silmez |
| [v1.2.50](#v1250) | 2026-09-10 18:16 | Meeting OS 1.2.50 — kopya görevler, dürüst sayılar, ses silme uyarısı |
| [v1.2.49](#v1249) | 2026-09-10 17:56 | Meeting OS 1.2.49 — bölüm seçici gerçek paragrafı görür |
| [v1.2.48](#v1248) | 2026-09-10 17:52 | Meeting OS 1.2.48 — görevler geri alınabilir, boş analiz görev silmez |
| [v1.2.47](#v1247) | 2026-09-10 17:34 | Meeting OS 1.2.47 — ikinci hafta: kendi sözleriniz artık sizin, Hafıza dürüst |
| [v1.2.46](#v1246) | 2026-09-10 19:40 | Meeting OS 1.2.46 — iki Mac aynı iCloud klasöründe: biri toplantıdayken diğeri güncellenebilir |
| [v1.2.45](#v1245) | 2026-09-10 18:40 | Meeting OS 1.2.45 — güncelleme yolu: yarıda kalınca dürüst, tekrar denemede eksiksiz |
| [v1.2.44](#v1244) | 2026-09-10 17:15 | Meeting OS 1.2.44 — ad düzeltmesi kurulu Mac'lerde de çalışır |
| [v1.2.43](#v1243) | 2026-09-10 16:20 | Meeting OS 1.2.43 — ilk gerçek toplantı: ad, maliyet, bekleme süresi |
| [v1.2.42](#v1242) | 2026-09-10 15:20 | Meeting OS 1.2.42 — kurulumda/güncellemede parola penceresi kalmadı; “Yalnız bu bölüm” ikinci görüşle sağlamlaştı |
| [v1.2.41](#v1241) | 2026-09-10 14:40 | Meeting OS 1.2.41 — dinlemeyi durdur; “Yalnız bu bölüm” düzeltmesi |
| [v1.2.40](#v1240) | 2026-09-10 14:05 | Meeting OS 1.2.40 — Anahtar Zinciri pencereleri bitti; ⌘M işaretleri düzeldi |
| [v1.2.39](#v1239) | 2026-09-10 12:04 | Meeting OS 1.2.39 — Keychain'e yalnız uygulama dokunur; yankı süzgeci kendi sesinizi silmiyor |
| [v1.2.38](#v1238) | 2026-09-10 11:57 | Meeting OS 1.2.38 — Keychain penceresi: süreç başına en fazla bir kez |
| [v1.2.37](#v1237) | 2026-09-10 11:45 | Meeting OS 1.2.37 — Keychain artık bir kez sorar; bütünleşme düzeltmeleri |
| [v1.2.36](#v1236) | 2026-09-10 11:00 | Meeting OS 1.2.36 — güncellemeler yalnız yayınlanmış etiketlerden |
| [v1.2.35](#v1235) | 2026-09-10 10:57 | Meeting OS 1.2.35 — zehirli sözlük savunması |
| [v1.2.34](#v1234) | 2026-09-10 10:50 | Meeting OS 1.2.34 — gizlilik düzeltmelerine ikinci görüş |
| [v1.2.33](#v1233) | 2026-09-10 10:36 | Meeting OS 1.2.33 — gizlilik denetimi, belgeler arayüzle bire bir |
| [v1.2.32](#v1232) | 2026-09-10 04:29 | Meeting OS 1.2.32 — brifing düzeltmesi |
| [v1.2.31](#v1231) | 2026-09-10 04:25 | Meeting OS 1.2.31 — analiz katmanında ikinci görüş |
| [v1.2.30](#v1230) | 2026-09-10 03:23 | Meeting OS 1.2.30 — ikinci görüş düzeltmeleri, boşta CPU, analiz kalitesi |
| [v1.2.29](#v1229) | 2026-09-10 02:12 | Meeting OS 1.2.29 — kurul turu 4: 14 güvenilirlik düzeltmesi, sadelik, ekip belgeleri |
| [v1.2.28](#v1228) | 2026-09-10 01:33 | Meeting OS 1.2.28 — yalın Ayarlar ve kenar çubuğu, kişi kartı, kişi bazlı eşik |
| [v1.2.27](#v1227) | 2026-09-10 01:08 | Meeting OS 1.2.27 — yarı yolda bırakmama, ekip kurulumu, öz-test |
| [v1.2.26](#v1226) | 2026-09-10 00:53 | Meeting OS 1.2.26 — İsimler kartı, tek eylemli Düzelt, ⌘Z, öğrenme döngüsü |
| [v1.2.25](#v1225) | 2026-09-10 00:32 | Meeting OS 1.2.25 — kurul turu 3: güvenilirlik, gizlilik, kalite tekrarı |
| [v1.2.24](#v1224) | 2026-09-09 18:58 | Meeting OS 1.2.24 — arka uç sadeleştirme ve hız |
| [v1.2.23](#v1223) | 2026-09-09 18:27 | Meeting OS 1.2.23 — sadeleştirme turu ve brifing |
| [v1.2.22](#v1222) | 2026-09-09 18:14 | Meeting OS 1.2.22 — soru radarı, karne, vade önerisi |
| [v1.2.21](#v1221) | 2026-09-09 18:00 | Meeting OS 1.2.21 — sadeleştirme ve daha hafif yoklama |
| [v1.2.20](#v1220) | 2026-09-09 17:54 | Meeting OS 1.2.20 — tema ve vurgu rengi |
| [v1.2.19](#v1219) | 2026-09-09 17:43 | Meeting OS 1.2.19 — belge gibi okuma görünümü |
| [v1.2.18](#v1218) | 2026-09-09 17:40 | Meeting OS 1.2.18 — kayıt uyku/uyanmada kopmaz |
| [v1.2.17](#v1217) | 2026-09-09 17:37 | Meeting OS 1.2.17 — ses dosyaları 3–4× küçüldü |
| [v1.2.16](#v1216) | 2026-09-09 17:29 | Meeting OS 1.2.16 — kurul turu: sağlamlık, PM haftası, arayüz |
| [v1.2.15](#v1215) | 2026-09-09 17:07 | Meeting OS 1.2.15 — kenar çubuğu grupları ve klavye kısayolları |
| [v1.2.14](#v1214) | 2026-09-09 15:10 | Meeting OS 1.2.14 — toplantıyı asla yavaşlatma |
| [v1.2.13](#v1213) | 2026-09-09 14:55 | Meeting OS 1.2.13 — kurulum kartında teşhis raporu durumu |
| [v1.2.12](#v1212) | 2026-09-09 14:52 | Meeting OS 1.2.12 — izinleri yerinde düzelt, ⌘, |
| [v1.2.11](#v1211) | 2026-09-09 14:42 | Meeting OS 1.2.11 — kurulum durumu kartı |
| [v1.2.10](#v1210) | 2026-09-09 14:38 | Meeting OS 1.2.10 — Görevlerim sayaçları |
| [v1.2.9](#v129) | 2026-09-09 14:34 | Meeting OS 1.2.9 — görevler Apple Hatırlatıcılar’a |
| [v1.2.8](#v128) | 2026-09-09 14:23 | Meeting OS 1.2.8 — Hafıza araması Türkçe eklere dayanıklı |
| [v1.2.7](#v127) | 2026-09-09 14:21 | Meeting OS 1.2.7 — bulut maliyeti kartı, panelde toplantı adı |
| [v1.2.6](#v126) | 2026-09-09 14:10 | Meeting OS 1.2.6 — Zoom’da elle dokunmadan kayıt, Kontrol’de takvim katılımcıları |
| [v1.2.5](#v125) | 2026-09-09 14:03 | Meeting OS 1.2.5 — takvim bağlamı |
| [v1.2.4](#v124) | 2026-09-09 13:51 | Meeting OS 1.2.4 — konuşma payı, kenar çubuğu araması ve süreleri |
| [v1.2.3](#v123) | 2026-09-09 13:43 | Meeting OS 1.2.3 — yüzen kayıt paneli, toplu sözlük düzeltmesi |
| [v1.2.0](#v120) | 2026-09-09 13:29 | Meeting OS 1.2.0 — Kontrol, sözlük, güncelleyici, menü çubuğu |
| [v1.1.0](#v110) | 2026-09-09 10:06 | Meeting OS 1.1.0 — OpenRouter transkript ve kişi tanıma |
| [v1.0.5](#v105) | 2026-09-08 09:14 | Meeting OS 1.0.5 — düşük bellekli transkripsiyon |
| [v1.0.4](#v104) | 2026-09-08 09:14 | Meeting OS 1.0.4 — kurulum ve durdurma düzeltmeleri |
| [v1.0.3](#v103) | 2026-09-08 09:14 | Meeting OS 1.0.3 — Bellek koruması |
| [v1.0.2](#v102) | 2026-09-08 09:14 | Meeting OS 1.0.2 — İlk kurulum düzeltmesi |
| [v1.0.1](#v101) | 2026-09-08 09:14 | Meeting OS 1.0.1 — Mac kurulum paketi |

## Notlar

<a id="v1267"></a>
### v1.2.67 — Ekip bulutu: sıfır kurulumlu ortak bilgi tabanı; her düzeltme öğrenir

2026-09-10 23:10 · yerel not · GitHub sürüm sayfası yok

Boran: "bunların hepsini sen yapmalısın; ekip arkadaşlarımın uygulama açılırken bir şey yapmasını isteyemem, sistem full hazır olmalı."

- **Ekip bulutu.** Profiller, öğretilen kelimeler, sözlük, nabız ve tanılama raporları artık iCloud'a ya da seçilen bir klasöre değil, Boran'ın kendi sunucusundaki küçük bir eşitleme servisine gider (`https://hermes-vps.tail2d8c7e.ts.net/meetingos`, TLS Tailscale Funnel, systemd, günlük yedek). Ekip kimliği OpenRouter anahtarından türetilir: aynı anahtarla kurulan her Mac aynı ekiptir, **kimse hiçbir şey seçmez**. Farklı anahtarla kurulan bir Mac için `MEETING_OS_TEAM=<token> sh scripts/install.sh` ya da `python -m meeting_os team join <token>`; token'ı `python -m meeting_os team invite` verir. Seçilmiş bir "Ekip klasörü" varsa o kazanmaya devam eder; iCloud yedek olarak kalır.
- Uygulama yerel bir aynayla (`Application Support/MeetingOS/team/`) çalışır: sunucu ulaşılamazsa hiçbir şey kaybolmaz, bağlanınca eşitlenir. Her Mac yalnız kendi dosyalarını yükler, diğerlerininkini indirir; yarış yok. Ağ çağrıları hızlı köprüde değil arka planda (adlandırma/öğretme) ya da saatlik bakımda ve açılışta (yavaş köprü); bağlantı 5 sn, tur 20 sn. Kurulum kartında "Ekip klasörü" satırı: "ekip bulutu · N Mac · son eşitleme HH:MM" ya da "bulut şu an erişilemiyor; yerel bilgi korunuyor".
- Gizlilik klasörle aynı: ad + ses vektörü, kelimeler, sözlük, raporlar (`share_text` kapalıysa metin yok), redakte hata günlüğü. Ses, transkript, toplantı başlığı yok. `docs/TEAM_CLOUD.md`, `server/README.md`.
- **Her düzeltme öğrenir.** "Yalnız bu bölüm" artık yalnız doğru kişiye örnek vermekle kalmıyor: yanlış kişi için o ses "bu o değil" diye kaydediliyor (bir daha ona eşleşmez) ve yanlış kişinin küme profili o parça olmadan yeniden hesaplanıyor (profili yabancı sesten arınıyor). ⌘Z ikisini de geri alır. Düz satıra "Adlandır" da temiz ≥6 sn bölümden ses öğreniyor; "Dinledim" kutusu gerekmiyor.
- **İsimler sese göre sıralı.** Adlandırma penceresindeki isim çipleri artık alfabetik değil: pencere açılınca ses karşılaştırılır, en benzeyen isim başa gelir; altında not.
- Testler: Python 865 (yeni: sunucu 17, bulut istemcisi 17, düzeltme öğrenimi 3, düz adlandırma 1, isim sırası 1), Swift 228. Sunucu canlı denendi: yetkisiz 401, başkasının dosyası 403, yaz/oku/sil 200, Funnel yolu `/v1/…` olarak iletiyor.
- Canlı doğrulanmadı: iki Mac'in aynı ekipte buluşması (diğer Mac güncellenince), kurulum kartı satırı.

<a id="v1266"></a>
### Meeting OS 1.2.66 — "Ekip klasörü" satırı: paylaşım nereye gidiyor, gitmiyorsa neden

2026-09-10 22:21 · yerel not · GitHub sürüm sayfası yok

Diğer Mac'te iCloud Drive klasörü olmadığı için ortak bilgi tabanı sessizce yazılmıyordu (nabız da gitmiyordu).
- Ayarlar → Sistem → Kurulum durumu'na "Ekip klasörü" satırı: seçili ekip klasörü (yeşil), seçilmemişse "iCloud Drive kullanılıyor (yalnız kendi Mac'leriniz arasında; ekip için Ekip klasörü seçin)", ikisi de yoksa kırmızı "profiller, kelimeler ve raporlar paylaşılmıyor".
- Köprü `setup_status` → `team_root`, `team_root_kind` (team | icloud | none).

<a id="v1265"></a>
### Meeting OS 1.2.65 — ekipteki hata ve çökmeler tek yerde toplanır

2026-09-10 22:03 · yerel not · GitHub sürüm sayfası yok

Boran: "3–5 kişi kullanınca yaşanan hata/çökme gibi şeyleri de toplayalım ki görüp fixleyebilelim."
- Her Mac'te maskelenmiş bir hata günlüğü (`errors.jsonl`): arayüzde gösterilen hatalar, iş/bulut/kayıt hataları, başarısız güncellemeler ve macOS çökme raporlarının özeti (süreç, sürüm, istisna türü, bizim koddaki üst 8 çerçeve). Transkript metni, ses, konuşmacı adı asla girmez; ev dizini yolları maskelenir; aynı hata 10 dakikada bir kez.
- Saatlik nabızda `error_journal` (son 24 saat sayımları, son 5 satır, çökme sayısı); `reports summarize` her Mac için hata satırı; çökme → hata uyarısı, günde ≥5 hata → uyarı.
- Ayarlar → Sistem → "Hatalar" kartı: son 5 kayıt, "Tanılama raporunu dışa aktar" (hata günlüğü ve çökme özetleri dahil), "Hata günlüğünü temizle". CLI: `errors list|clear`.
- EKIP.md gizlilik bölümünde günlüğün içeriği ve bir sorunun nasıl bildirileceği.

<a id="v1264"></a>
### Meeting OS 1.2.64 — Kontrol'de onaylanan sözlük düzeltmesi bir daha sorulmaz

2026-09-10 21:51 · yerel not · GitHub sürüm sayfası yok

Boran: "AB Testi → A/B Test diye birkaç kere düzelttim, hâlâ soruyor."
- Kontrol'deki "Sözlük: X muhtemelen Y" maddesini onaylamak artık **öğretir**: bu toplantıdaki bütün geçişler düzelir, kural öğrenilen kelimelere girer (ekip klasörüne de yazılır) ve sonraki toplantılarda yazıya çevirme bitince kendiliğinden uygulanır; Kontrol aynı kelimeyi bir daha sormaz.
- "Bu doğru" da bütün toplantılar için geçerli (aynı kelime başka toplantıda önerilmez).
- "Tümünü uygula" da aynı şekilde öğretir.

<a id="v1263"></a>
### Meeting OS 1.2.63 — ekip klasörü ortak bilgi tabanı: profiller ve kelimeler herkeste birikir

2026-09-10 21:45 · yerel not · GitHub sürüm sayfası yok

Boran: "3–5 kişi kullanınca isim ve kelime düzeltmeleri herkeste birikmeli; kimse cold start yaşamamalı; kullananlardan beslenen bir platform."
- **Ortak bilgi tabanı = ekip klasörü** (Ayarlar → Sistem → Ekip klasörü; yoksa iCloud Drive/MeetingOS-Shared): `team-words.jsonl` (öğretilen kelimeler) ve `profiles/<Mac>.jsonl` (kişi adı + ses vektörü). Ses kaydı, transkript, toplantı adı hiç yazılmaz.
- **Herkes yazar, herkes alır:** her adlandırma/kelime öğretme sonrası hemen, açılışta ve saatte bir eşitleme. İlk açılışta Mac'teki bütün mevcut profiller ve kelimeler geriye dönük yüklenir; yeni kurulan Mac ilk toplantısında tanıdıkları tanır.
- **Kurallar:** çakışmada yerel düzeltme kazanır, aksi hâlde en yeni; ekipten gelen bir kelimeyi "Kapat", bir profili kişi kartından silip engelleyebilirsiniz; reddettiğiniz kişi ekipten geri gelmez. Ekip kelimeleri de yalnız birebir yazımda otomatik uygulanır.
- Ayarlar → Sesler ve sözlük: "Öğretilen kelimeleri ekiple paylaş" ve "Ses profillerimi ekiple paylaş" (ikisi de açık); "ekipten N profil, M kelime" sayacı; öğrenilen kelimeler listesinde kaynak Mac rozeti.
- Nabız/özet: her Mac'in katkısı (`team_profiles/team_words/shared_*`).
- EKIP.md "Ekip bilgisi" bölümü: neyin çıktığı, nasıl kapatıldığı.

<a id="v1262"></a>
### Meeting OS 1.2.62 — ekran paylaşırken göze batmaz

2026-09-10 21:34 · yerel not · GitHub sürüm sayfası yok

Boran: "ekran paylaşan biri kayıt alıyorsa diğerleri menü çubuğundaki ikonu ya da paneli görmemeli."
- **Göze batma** (Ayarlar → Genel, varsayılan açık): kayıt sırasında menü çubuğu simgesi boştaki ile birebir aynı (kırmızı nokta, süre, "kaydediyor" yok; menü açılınca Bitir/An/Karar yine orada).
- Zoom ekran paylaşımı algılanınca (paylaşım çubuğu penceresi) yüzen panel tamamen gizlenir, paylaşım bitince geri gelir; ⌃⌥R / ⌃⌥M çalışmaya devam eder.
- Ana pencere ve paneller ekran yakalamaya girmez (`sharingType = .none`): paylaşılan ekranda transkript görünmez.
- Paylaşım sürerken bildirim gösterilmez (kuyruğa alınır).
- Canlı doğrulanmadı: Zoom'un paylaşım çubuğu pencere adı (eşleşme listesi geniş tutuldu); Zoom'da ana pencerenin gerçekten boş görünmesi.

<a id="v1261"></a>
### Meeting OS 1.2.61 — konuşma payı yine gözünüzün önünde

2026-09-10 21:19 · yerel not · GitHub sürüm sayfası yok

- Özet'te "Konuşma payı" (kim ne kadar konuştu) çubukları yeniden varsayılan olarak açık; katlarsanız tercihiniz hatırlanır (toplantı değişince kapanmaz).

<a id="v1260"></a>
### Meeting OS 1.2.60 — ekran kaydı izni neden isteniyor, kartta yazıyor

2026-09-10 21:16 · yerel not · GitHub sürüm sayfası yok

- Ayarlar → Sistem → Kurulum durumu → "Ekran kaydı (toplantı sesi)" satırı artık nedenini söylüyor: karşı tarafın sesi (Zoom'dan hoparlöre giden ses) macOS'ta yalnız bu izinle alınabilir; ekran görüntüsü alınmaz ve saklanmaz. İzin verilmişken de aynı açıklama görünür.

<a id="v1259"></a>
### Meeting OS 1.2.59 — ortalı boş durumlar, her sayfada ✕, Geri düğmesi

2026-09-10 21:10 · yerel not · GitHub sürüm sayfası yok

Boran'ın üç isteği:
- **Boş sekmeler / uyarılar ortalı:** bütün boş durumlar (Transkript, Özet, Görevlerim, Kontrol, Hafıza, karne, Ara) tek bileşenle, pencere boyutundan bağımsız ortada; içerik sütunları (≈800 pt) pencerede ortalanır (Özet artık sola yapışık değil); şeritler dar pencerede kırpılmaz, sarar.
- **Her sayfada kapatma:** Ayarlar, Paylaş, OpenRouter, Düzelt, temiz örnek, taslak/görev düzenleme ve kelime baloncuğunda sağ üstte ✕; Esc ve ⌘W sayfayı kapatır (pencereyi değil). Ayarlar'ın ✕'i kaydırmadan bağımsız her zaman görünür, sayfa ekrandan taşmaz.
- **Geri:** "Bölüme git", kanıt alıntısı, Hafıza/karar/soru sonucu, Kontrol → Görevlerim gibi programlı atlamalardan sonra sekme şeridinde "← Geri" (⌘[; Git menüsünde de). Kenar çubuğu ve sekme tıklamaları geri yığınına girmez.

<a id="v1258"></a>
### Meeting OS 1.2.58 — tıkla-düzelt ve Özet'e ikinci görüş düzeltmeleri

2026-09-10 20:50 · yerel not · GitHub sürüm sayfası yok

- ⌘⌫ artık bir metin alanı/pencere açıkken "toplantıyı sil" penceresi açmaz (metin düzenleme kısayolu olarak kalır).
- "Trendyoll'a" gibi ekli kelimeye "Düzelt ve öğret": kural kökten öğrenilir (Trendyoll → Trendyol), ek korunur; eskiden kural ölü doğuyor ve "öğrenildi" deniyordu.
- "istanbul → İstanbul" gibi yalnız büyük/küçük harf düzeltmesi artık öğretilebilir ve uygulanır.
- "Yalnız burada" tıklanan kelime bu arada değiştiyse (başka bir düzeltme geldiyse) yanlış kelimeyi değiştirmez; "kelimeye yeniden tıklayın" der.
- Kelime üzerinde el imleci sistem yoluyla (imleç takılı kalmıyor); Özet maddeleri yine kopyalanabilir; baloncuk ekranda görünen yazımı (büyük harfli) kullanır.

<a id="v1257"></a>
### Meeting OS 1.2.57 — soldaki listede çöp kutusu; 1–2 saniyelik seslere isim istenmez

2026-09-10 20:47 · yerel not · GitHub sürüm sayfası yok

- Kenar çubuğunda her toplantı satırının sağında, üzerine gelince ya da seçiliyken görünen **çöp kutusu** düğmesi (sağ tık menüsü ve ⌫/⌘⌫ de duruyor). Boran: "toplantıyı sil butonu hâlâ yok solda".
- Toplam 4 saniyenin altındaki konuşmacı kümeleri (öksürük, kapı, kesik kelime) için İsimler kartı ve Kontrol artık isim istemez; transkriptte etiketleriyle kalırlar. Boran: "1–2 saniyelik noise'lara isim verilemez".
- Sürüm notlarındaki saatler gerçek git zaman damgalarına göre düzeltildi (1.2.47–1.2.56 hepsi 10 Eylül 17:34–20:38).

<a id="v1256"></a>
### Meeting OS 1.2.56 — kelimeye tıkla düzelt, temiz Özet, soldan sil; kelime öğrenme güvenli

2026-09-10 20:38 · yerel not · GitHub sürüm sayfası yok

Boran'ın üç isteği + ikinci görüşün kritik bulgusu:
- **Kelimeye tıklayarak düzeltme:** transkriptte herhangi bir kelimeye tıklayın → küçük baloncuk: "Yalnız burada" (sadece bu geçiş) ya da "Düzelt ve öğret". Düzelt penceresine girmeye gerek yok; oradaki satır da duruyor.
- **Özet sayfası:** her madde tek satır (kontrol/geri alındı çipleriyle); kanıtlar varsayılan gizli, maddeye tıklayınca açılır; bölüm başlığında "Kanıtları göster/gizle"; tepede tek satır istatistik; konuşma payı katlanır; kartlar sadeleşti.
- **Kenar çubuğundan silme:** sağ tık satırın her yerinde "Toplantıyı sil…" (artık iş sürerken de gri değil); seçili toplantıda ⌫ ve ⌘⌫; iş sürüyorsa neden silinmediği yazılır.
- **Kelime öğrenme güvenliği (kritik):** 1.2.53'ün bulanık eşlemesi gerçek transkriptlerde başka kelimeleri de değiştiriyordu ("Aynen" → "Ayşen"). Artık otomatik düzeltme yalnız birebir yazımda; yakın yazımlar yalnız Kontrol'e öneri olarak gelir, onaylanınca düzelir. "Unut" elle düzenlenmiş bölümü bozmaz; aynı kelimeyi iki kez öğretmek metni büyütmez; "Bu doğru" bütün toplantılar için geçerli; öğretilen kelime sözlük terimiyse de çalışır.
- Görev sahibi kanıt kapısı aksanları korur ("Şen" ≠ "sen"); disk dolunca deneme hakkı geri gitmez (48 saat sonra normal hata); devam eden yüklemede kalan süre bu koşuya göre; disk geri sayımı doğru (1,2 GB → ≈39 dk) ve uyarı 250 MB'de bir yenilenir; geçici birleştirme dosyasına 1 saat tolerans.

Kıyas 7/7 (bir koşuda `mic_owner` vade metni "cuma günü"/"cuma gününe kadar" farkıyla 4/5, tekrarında 5/5 — model varyansı), replay 14/0/2, Python 781, Swift 200.

<a id="v1255"></a>
### Meeting OS 1.2.55 — temizlik: doğru belgeler, tam köprü, tek kural

2026-09-10 19:57 · yerel not · GitHub sürüm sayfası yok

Tur 17 (sadelik/tutarlılık denetimi) → uygulandı.
- README/OPENROUTER/V1_USAGE'deki 8 yanlış cümle düzeltildi (disk eşikleri, Zoom 5 dk, bulut yanıt, düğme/sekme adları, kimlik eşikleri, bulut akışı).
- Kurulum kartı dal ayrışmasını ve git kontrol hatasını artık gerçekten gösteriyor ("kontrol edilemedi"); kayıt günlüğü okunamadığında kayıt "sağlıklı" sayılmıyor; kimlik eşikleri Swift'te kopya değil, köprüden.
- Görev sahibi kanıt kapısı diğer yerlerle aynı ad katlamasını kullanıyor (Gokhan/Gökhan artık sahipsiz kalmıyor); dışa aktarım reddedilen/emekli görevleri geri getirmiyor ve Türkçe durum yazıyor; konuşmacı etiketleri her yerde mikrofon sahibini doğru gösteriyor.
- Testler: hiçbir test gerçek kayıt cihazını ya da veri klasörünü kullanmıyor; `MEETING_OS_TEST_IGNORE_PRESSURE=1` ile tam paket meşgul Mac'te de yeşil (769 test).
- Ölü kod: çağrılmayan 3 köprü eylemi, 4 Swift sembolü, 10 gereksiz import, bir ölü ortam değişkeni kaldırıldı; 14 yetim belge `docs/archive/`; ad katlaması, durum etiketleri, ayar kaydetme sarmalayıcısı tek yerde; analiz kullanım kaydı ContextVar.
- `verify-capture.py` `MEETING_OS_CAPTURE_BIN` ile imzasız yardımcıyı da sınar.

<a id="v1254"></a>
### Meeting OS 1.2.54 — 2 saatlik toplantı: kayıp yok, disk dürüst, arayüz tembel

2026-09-10 19:26 · yerel not · GitHub sürüm sayfası yok

Tur 16 ölçek denetimi (2 saat / 1200 bölüm, ölçüldü: 4 P0, 4 P1, 5 P2) → uygulandı.

**Ses kaybı (P0)**
- Yarıda kesilen birleştirme dosyası artık bütün sayılmıyor: `.tmp`'ye yazılır, bitince adı değişir; var olan dosya günlükteki süreyle karşılaştırılır, kısa ise yeniden kurulur; bir kaynak eksikse parçalar asla silinmez.
- Disk: birleştirme için bütün kaynakların yeri önceden ayrılır; kayıt yardımcısı durma eşiğini toplantı uzunluğuna göre yükseltir (2 saatte ≈1,2 GB), 3 GB/3× eşikte uyarır; disk dolunca "Disk dolu: ≈N MB gerekli" der ve bulut deneme hakkı harcamaz.
- 3 GB uyarısı ilk kez görünüyor: kayıt panelinde ve durum satırında "Disk azalıyor · N GB boş · kayıt M dk sonra durabilir"; 600 MB altında kayıt başlamaz, 1,5 GB altında uyarır.

**Hız ve dürüstlük (P1/P2)**
- Kalan süre parça sayısı yerine yüklenen saniyeye göre (hoparlörlü toplantıda 8× hata giderildi); kaynaklar dönüşümlü sıraya alındı; boşta yeniden deneme 2 işçi (Zoom açıksa 1); kodlama yüklemeyle örtüşüyor; düşük öncelikte 120 dk tahmin sınırı.
- Transkript listesi tembel (1200 satır ilk karede ölçülmez); arama 150 ms gecikmeli ve süzülmüş satırlar önbellekli; Zoom pencere taraması ana aktörden alındı; saatlik bakım 10 sn köprü bekçisinden ayrı yavaş şeride alındı (`.flac.tmp` artığı süpürülür).
- Analiz maliyeti dürüst: 40 dk ≈ 3 cent, 2 saat ≈ $0,08.

<a id="v1253"></a>
### Meeting OS 1.2.53 — kelimeyi bir kez düzelt, uygulama öğrensin

2026-09-10 19:12 · yerel not · GitHub sürüm sayfası yok

Boran'ın isteği: "kelimelerde de düzeltme yapabilmeliyim; sonrasında o kelimeyi öğrenmeli ve yakınsa o şekilde algılamalı; Kontrol'e gelmeyen yanlış kelime algıları var; eğitilebilir olmalı."

- **Düzelt penceresinde "Kelime düzelt":** kelimeyi seçin, doğrusunu yazın, "Düzelt ve öğret". Bu toplantıdaki bütün geçişler düzelir (büyük/küçük harf korunur), kural hemen öğrenilir, doğru kelime yazıya çevirme sözlüğüne (ASR ipucu) eklenir.
- **Yakın yazımlar:** (1.2.56'da değişti) kendiliğinden düzeltilmez, Kontrol'e "muhtemelen" önerisi olarak gelir; onaylayınca düzelir ve öğrenilir. Kendiliğinden düzelen yalnız öğretilen yazımın kendisidir (Türkçe ek ve kesme işareti korunur: "Trendyoll'a" → "Trendyol'a"; "Trendyola" gibi ekli doğru yazımlara dokunulmaz).
- **Kontrol:** "Kelime: X muhtemelen Y" maddeleri (öğretilen kelimelere ve sözlük terimlerine yakın yazımlar) — "Düzelt ve öğret" / "Bu doğru".
- **Ayarlar → Sesler ve sözlük → Öğrenilen kelimeler:** liste ve "Unut" (metinler geri döner, sözlük satırı kalkar). CLI: `words teach|forget|list`.
- Eskisi gibi: aynı düzeltme iki toplantıda tekrarlanınca da kural öğrenilir; "Metni kaydet" Gelişmiş altında duruyor.

<a id="v1252"></a>
### Meeting OS 1.2.52 — kıyas seti mikrofon sahibi yolunu da sınıyor

2026-09-10 18:45 · yerel not · GitHub sürüm sayfası yok

- Kıyas setine `mic_owner` vakası (kurgusal 4 kişilik toplantı; sahibin mikrofon satırları "Ben" etiketiyle, bir yankı satırı, bir karar): sahibin iki sözü sahibe, meslektaşınki meslektaşa, yankı sözü "kontrol edin" ile. Bulutta 7/7, çevrimdışı 11 sözleşme testi. Uygulama kodu değişmedi.
- `docs/BENCHMARK.md` güncellendi.

Diğer Mac için Terminal'den güncelleme tarifi (eski sürüm düğmeyi gizliyorsa): `docs/TWO_MAC_WORKFLOW.md` → "Düğme görünmüyorsa".

<a id="v1251"></a>
### Meeting OS 1.2.51 — maske adınızı yine gizler, kopya birleştirme vadeleri ayırır, yeniden analiz onaylı vadeyi silmez

2026-09-10 18:32 · yerel not · GitHub sürüm sayfası yok

1.2.50'ye ikinci görüş (3 P0, 4 P1):
- **Maske gerilemesi (P0):** 1.2.50 sahibin adını yalnız mikrofon satırı varsa maskeliyordu; mikrofonsuz toplantılarda (bu Mac'te 3 tanesi) "Boran'a soralım" açıkta kalıyordu. Artık sahibin adı her zaman maskelenir; yalnız ortak kelime olan adlar (Can, Deniz…) için katılım şartı var.
- **Kopya birleştirme (P0):** yalnız rakamı farklı görevler ("10 Ekim" / "15 Ekim", "5 gün" / "7 gün") tek göreve iniyordu. Rakamlar artık ayırt edici; 4 kelimeden kısa başlıklar yalnız birebir eşleşir; birleşince kanıtlar, vade ve sahip birleştirilir ve "merged_from" izi kalır.
- **Yeniden analiz (P0, eski):** aynı analiz yeniden kaydedilince onaylanan vade tarihi ve "aynı görev" bağlantıları siliniyordu; artık korunur.
- Ses silme uyarısı gerçek geri sayımı söyler ("bugün" / "yarın" / "N gün içinde"); diskte sesi olmayan toplantıları saymaz; Son durum satırını her saat değil, geri sayım adımı başına bir kez alır.
- Kararlar başlığı görünen listeyi sayar (arama/limit ile uyumlu); "(kısmi)" yalnız fiyatlı çağrı varsa; "Aynı görev" iki yönde uygulanamaz.
- Kıyas betiğinden sabit kişisel ad kaldırıldı; mikrofon sahibi yolu için fikstür henüz yok (kıyas bu yolu sınamaz).

<a id="v1250"></a>
### Meeting OS 1.2.50 — kopya görevler, dürüst sayılar, ses silme uyarısı

2026-09-10 18:16 · yerel not · GitHub sürüm sayfası yok

Tur 14 (ikinci görüşlerden kalan küçük maddeler):
- Aynı toplantı içindeki kopya görevler: analizde birleştirilir; kalanlar "Bu toplantıda benzer görev" ile bağlanır ve "Aynı görev, eskisini kapat" çalışır.
- "İsimleri maskele": sahibin adı yalnız gerçekten konuştuysa ve ortak Türkçe kelime olan adlar (Can, Su, Deniz…) yalnız büyük harfli kullanımda maskelenir; "Can sıkıntısı" bozulmaz.
- Ayarlar maliyet kartı: bazı analizlerin kullanımı kayıtlı değilse "(kısmi)".
- Kararlar başlığı "N karar · M geri alındı" (karneyle aynı sayım); bayat sayısı yalnız görünen satırlar için.
- Geçmişe düşen vade önerisi "(geçmiş)" ile işaretli.
- Gün sonu özetinde sorular mikrofon sahibini doğru tanır.
- Ses saklama: en eski kaydın sesi silinmeden 3 gün önce Son durum satırında uyarı ("Sesi koru" ile saklanır); KULLANIM'da tam olarak neyin silindiği yazıldı (yalnız ses; transkript, özet, görevler, profiller kalır).
- Kıyas betiği artık mikrofon sahibi yolunu da sınar (6/6, 12 çağrı ≈1,6 cent).

<a id="v1249"></a>
### Meeting OS 1.2.49 — bölüm seçici gerçek paragrafı görür

2026-09-10 17:56 · yerel not · GitHub sürüm sayfası yok

Canlı doğrulama (bu Mac, 1.2.48): ▶ çalarken ■ oluyor ve ikinci tıkta duruyor; Düzelt penceresinde "Yalnız bu bölüm"; Özet ve Kontrol sekmeleri düzgün. Bulunan eksik: 3 bölümlü paragrafta "hangi bölüm?" seçicisi çıkmıyordu, çünkü seçici bitişik satırlara bakıyor, okuma görünümünde gizli yankı satırları ve kısa "hı hı" araları paragrafı bölüyordu.
- Bölüm seçici artık okuma görünümünün kendi paragraf gruplamasını kullanır (gizli yankı satırları ve kısa aralar paragrafı bölmez); "3 bölüm" yazan paragrafta üç seçenek listelenir.

<a id="v1248"></a>
### Meeting OS 1.2.48 — görevler geri alınabilir, boş analiz görev silmez

2026-09-10 17:52 · yerel not · GitHub sürüm sayfası yok

1.2.47'ye ikinci görüş (2 P0, 6 P1):
- **Boş dönen yeniden analiz açık görevleri gizliyordu (P0):** "Özeti yenile" sonrası model hiç görev çıkarmazsa eski görevlerin hepsi görünmez oluyordu. Artık eski görevler yalnız yeni analiz en az bir görev ürettiğinde emekli edilir; "devam ediyor"/"tamamlandı" işaretli görevler her zaman kalır.
- **⌘Z görev sahiplerini geri taşımıyordu (P0):** adlandırma geri alınınca görevler olmayan bir isimde kalıyor, yeniden adlandırma da kurtaramıyordu. Geri alma (küme ve tek bölüm) sahipleri de geri taşır.
- Ayarlar'da ad değişince yalnız yeniden etiketlenen toplantıların görevleri taşınır (aynı ilk adı taşıyan bir meslektaşın görevine dokunulmaz). Kişi kartından yeniden adlandırma da görevleri taşır.
- "Tamamlandı" işaretlemek görevi "elle düzenlendi" saymaz; yalnız başlık/sahip/vade değişikliği sayar.
- Mikrofon satırından çıkan birinci tekil söz (olası yankı) sahibe atanır ama "kontrol edin" işaretiyle.
- Karnede "N toplantı analiz edilmedi" satırı gerçekten çıkıyor (alan köprüde eksikti). Eski "Boran"/"Ben" mikrofon etiketleri ad zaten varken de süpürülür.
- EKIP: analiz istemine mikrofon satırlarında kendi adınızın gittiği yazıldı.

<a id="v1247"></a>
### Meeting OS 1.2.47 — ikinci hafta: kendi sözleriniz artık sizin, Hafıza dürüst

2026-09-10 17:34 · yerel not · GitHub sürüm sayfası yok

Tur 13 denetimi (Hafıza, gün sonu özeti, brifing, karne — gerçek veriyle: 3 P0, 8 P1, 9 P2) → uygulandı.

**Görev sahipliği (P0)**
- Bulut yolunda sahip ataması mikrofon etiketini hiç okumuyordu: kendi verdiğiniz sözler asla "Bana ait" olmuyor, gün sonu özeti "sana düşen görev yok" diyordu. Artık mikrofon satırındaki adınız sahiptir (ad yoksa Ayarlar'daki ad); model de mikrofon kişisini görür.
- Brifing adları alt-dize ile eşliyordu (Ali → Salih, Can → Cansu): tam ad/kelime eşleşmesi.
- Ad değişince (Ayarlar'da ya da konuşmacı yeniden adlandırınca) görev sahipleri de taşınır; kendi göreviniz "Beklediklerim"e düşmez.

**Hafıza ve raporlar (P1)**
- Karne: analiz edilmemiş toplantı "analiz yok" der (sıfır değil); "N toplantı analiz edilmedi" satırı; analiz ücreti satırı; boş aralıkta sakin boş durum.
- Geri alınan kararlar Kararlar'da "geri alındı" olarak görünür, özet/brifing/paylaşım/karnede canlı sayılmaz.
- Bayat analiz Kararlar/Sorular/Beklediklerim'de turuncu "Kaynak değişti" rozetiyle; başlıkta "N toplantının analizi bayat".
- "İsimleri maskele" sizin adınızı da maskeler; gün sonu görev alıntıları da maskeli.
- Vade önerisi toplantının kendi gününe göre (analiz saatinin UTC gününe değil).
- Yeniden analiz eski görevi açık bırakmıyor (yenilendi olarak emekli; sayımlarda yok).
- "Senden beklenen cevaplar" → "Cevapsız sorular" (dürüst); "Muhtemelen cevaplandı" bir ipucu gibi görünür.
- Eski analizlerin bilinmeyen maliyeti "$0.00" yerine "—".

**P2:** arama eşitlik kırma (daha çok isabet, kısa bölüm önce), konuşmacı süzgeci aksan katlaması, karne konuşanlarda mikrofon sahibi, silinmiş toplantının örneği "toplantı silindi", Kontrol ve karne aynı 7 takvim günü.

Kıyas seti 6/6, replay 14/0/2. Kıyas betiğinin sarmalayıcısı yeni argümanı geçirmiyordu; düzeltildi.

<a id="v1246"></a>
### Meeting OS 1.2.46 — iki Mac aynı iCloud klasöründe: biri toplantıdayken diğeri güncellenebilir

2026-09-10 19:40 · yerel not · GitHub sürüm sayfası yok

1.2.45'e ikinci görüş (1 P0, 5 P1):
- **Diğer Mac'in kaydı bu Mac'in güncellemesini engelliyordu (P0):** kayıt nabzı paylaşılan iCloud klasörüne de yazıldığı için `update.sh` başka Mac'in toplantısını "kayıt sürüyor" sayıp reddediyor, uygulamayı kapatıp açıyor ve sahte "güncelleme başarısız" uyarısı yayıyordu. Artık yalnız bu Mac'in kaydına bakılır.
- Kilit artık saate değil sürecin yaşayıp yaşamadığına bakar (uzun derleme kilidi kaybetmez); ikinci koşu durum dosyasına dokunmaz.
- Kayıt, yerel değişiklik ve kapanmayan uygulama "başarısız" değil "yapılmadı" (refused) sayılır: bildirim ve ekip uyarısı çıkmaz.
- Uygulama ile betik etiket yokken aynı şeyi söyler (uygulama artık olmayan bir güncellemeyi teklif etmez); etiket deseni `vX.Y.Z` ile sınırlı (rc/iki parçalı etiketler seçilmez).
- ⌃⌥R ayarlar ilk seferde yüklenemediyse bir saat boyunca "ayarlar yükleniyor" demez; her yoklamada yeniden yükler.
- Ekip uyarıları: sessiz (bayat nabızlı) Mac için tekrar etmez; sürüm uyuşmazlığı başarısız güncelleme yoksa uyarı düzeyinde.
- "Dal ileri sarılamadı" mesajı boş kalmıyor; betiğin çıkış kodu derleme hatasında korunuyor; kurulum kartındaki imza komutu geçersiz `/tmp` yolu üretmiyor.

<a id="v1245"></a>
### Meeting OS 1.2.45 — güncelleme yolu: yarıda kalınca dürüst, tekrar denemede eksiksiz

2026-09-10 18:40 · yerel not · GitHub sürüm sayfası yok

Tur 12 denetimi (güncelleme / geri alma / ekip klasörü: 4 P0, 10 P1, 9 P2) → uygulandı.

**Güncelleme (P0)**
- `update.sh` artık depoyu değiştirmeden ÖNCE imza iznini ve ileri sarılabilirliği denetler; yarıda kalan güncelleme depoyu yeni/uygulamayı eski bırakıp "güncel" diyemez.
- Son başarıyla kurulan commit `build/installed-commit` olarak izlenir; tekrar denemede pip ve kayıt yardımcısı atlanmaz.
- Ekip klasörü nabzı yüklü uygulama sürümünü, depo sürümünü, commit'i, son güncelleme durumunu ve imza işaretini taşır; `reports summarize` sürüm uyuşmazlığı, başarısız güncelleme ve eksik izin için uyarı verir.
- Dal ayrışması (force-push) artık uygulamada, kurulum kartında ve köprüde açıkça "Dal ayrışmış · yeni sürüm kurulamıyor · Boran'a bildirin"; güncelle düğmesi gizlenir. Etiketler `--force` ile çekilir, en YÜKSEK sürüm etiketi seçilir (en yakın değil).

**Güncelleme (P1)**
- Kilit (ikinci koşu "Güncelleme zaten sürüyor"), kayıt sürerken red ("Kayıt sürüyor; güncelleme yapılmadı"), atomik durum dosyası, günlük döndürme, derleme çıktısı koşu başına ayrı dosya, "Derleme başarısız; kurulu sürüm değişmedi" doğru mesajı, çıkışta önce depo yolundaki uygulama açılır.
- Yedekler artık oluşturulur oluşturulmaz silinmiyor (zaman damgasına göre iki yedek kalır).
- İmza izni işareti mesajında depo yolu var; Öz-test ve `doctor` "hata" düzeyinde söyler; kurulum kartında "İmzalama izni" satırı. Keychain'de anahtar olan ama dosyası olmayan Mac artık hata değil uyarı.
- Ad 1.2.44 geçişinde sessizce boşalmıyor: uygulama açılışta bir kez sorar; ⌃⌥R ayarlar yüklenmeden ad yok sanmaz; ayarlar penceresi açıkken çıkışta yazılan ad kaybolmaz. 30 dk'dan eski "çalışıyor" güncelleme durumu "yarıda kalmış olabilir" diye söylenir; başarısız güncelleme bildirim de gönderir.

**Belgeler:** güncelleme sırası, yarıda kalan güncelleme, force-push yasağı, "etiket sürümdür, release paketi değil" (zip ve SHA güncellemede kullanılmaz), geri dönüş desteklenmiyor (ölçüldü), nabız içeriği.

Kurulu Mac'lerde ilk güncelleme bir kez `sh ~/meeting-os/scripts/fix-signing-prompts.sh` isteyebilir (1.2.41 ve öncesinde çalıştırılmış olsa da dosya yazılmamıştı).

<a id="v1244"></a>
### Meeting OS 1.2.44 — ad düzeltmesi kurulu Mac'lerde de çalışır

2026-09-10 17:15 · yerel not · GitHub sürüm sayfası yok

1.2.43'e ikinci görüş (1 P0, 4 P1):
- **Kurulu Mac'lerde ad düzeltmesi devreye girmiyordu (P0):** 1.2.42 ayar dosyasına kimsenin yazmadığı "Boran" adını kaydediyordu; 1.2.43 bunu gerçek ad sanıyordu. Artık yalnız kullanıcının yazdığı ad (onaylı) sayılır; eski "Boran" kaydı adsız kabul edilir, kayıt öncesi ad sorulur ve eski toplantılar yeniden etiketlenir. Boran'ın kendi Mac'lerinde adı bir kez yeniden yazması yeter.
- Boş ad alanı kayıtlı adı silmiyor (Ayarlar, ad yüklenmeden açılınca adı siliyordu); ayarlar köprüden yüklenmeden kaydedilmez.
- "Ben raporu paylaşacağım" cümlesinden model "Ben" adında bir sahip üretiyordu; birinci tekil/çoğul zamirler sahip olamaz.
- Toplantı değiştirilince bekleyen özet yenilemesi yanlış toplantıya "Özeti yenile" rozeti koyuyordu; düzeltildi, rozet artık kayıtlı "bayat" bilgisinden türetilir.
- Zoom otomatik kaydı ad yokken sessizce başlamıyordu; şimdi Zoom oturumu başına bir kez bildirim gösterir.
- Yeniden etiketlenen toplantı sayısı tekrarsız; kullanım bilgisi gelmeyen analiz çağrısı için sıfır satır yazılmaz.

<a id="v1243"></a>
### Meeting OS 1.2.43 — ilk gerçek toplantı: ad, maliyet, bekleme süresi

2026-09-10 16:20 · yerel not · GitHub sürüm sayfası yok

Tur 10 denetimi (“ekip arkadaşının ilk gerçek toplantısından sonraki 10 dakika”): 2 P0, 9 P1, 6 P2 → uygulandı.

**Adınız (P0)**
- Karşılama ekranı artık “Boran” ile dolu gelmiyor; ad yazılmadan kayıt başlamıyor (kısayol dahil) ve alan işaretleniyor. Ad sonradan değişirse önceki toplantılardaki mikrofon sesiniz de yeniden etiketlenir (“önceki N toplantı”), özetleri bayat düşer.
- Ad yokken mikrofon satırları “Ben (siz)” görünür. “Bana ait” filtresi Python ile aynı ad katlamasını kullanır (Ayse = Ayşe, Ilker = İlker).

**Analiz maliyeti (P0)**
- Adlandırmalar 20 sn içinde tek bir yeniden analizde birleşir; iş sürerken gelen adlandırma bittikten sonra bir kez koşar. “Yalnız bu bölüm” analizi yeniden koşturmaz; Özet sekmesinde “İsim değişti · Özeti yenile” rozeti çıkar.
- Her analiz çağrısının kullanımı kaydedilir (OpenRouter `usage`; yoksa tahmin ve “tahmini” etiketi). Ayarlar → Sistem maliyet kartında “Analiz · N çağrı”, karnede ve raporlarda analiz maliyeti.

**İlk 10 dakika (P1)**
- Durum satırında kalan süre tahmini (“≈8 dk kaldı”); yazıya çevirme sürerken Mac boşta uykuya girmez; kayıt düğmesi iş sürerken gri kalmaz (kayıt ayrı yuvada); ⌘Z öneri onayı ve bölüm düzeltmesinden sonra da çalışır ve yeniden analiz boyunca kapanmaz.
- İlk toplantıda İsimler kartı bir cümleyle durumu söyler (profil yok; adları bir kez yazın). Sistem sesi boş olan toplantı artık “Konuşma bulunmadı” demez; başlıkta mikrofon sahibi de sayılır.
- Görevlerde “Kaynak ses belirsiz” yalnız gerçekten belirsizse; atılan alıntı/madde sayısı rapor ve köprüde. Paylaşılan klasöre giden dosyalarda ev dizini yolu maskelenir. Kısa örnekle kaydedilen profil süresini söyler (“12 sn”, 6 sn altı uyarı).
- Belgeler: dışarı kendiliğinden çıkanların tam listesi, 45 dk toplantı için 10–20 dk dürüst süre, ad kurulum adımı, maliyet rakamları tutarlı, ⌘. kısayol listesinde, raporlarda başlık/isim yalnız transkript paylaşımı açıkken.

Güncelleme: `sh scripts/update.sh` ya da uygulamadan; kurulu Mac'lerde ilk seferinde bir kez `sh ~/meeting-os/scripts/fix-signing-prompts.sh` istenebilir.

<a id="v1242"></a>
### Meeting OS 1.2.42 — kurulumda/güncellemede parola penceresi kalmadı; “Yalnız bu bölüm” ikinci görüşle sağlamlaştı

2026-09-10 15:20 · yerel not · GitHub sürüm sayfası yok

**Kurulum ve güncelleme (tur 9 denetimi: 4 P0, 7 P1, 3 P2)**
- İmzalama anahtarına kalıcı izin adımı artık **her** kurulumda çalışır (sertifika Xcode'dan ya da önceki bir denemeden gelse de); sessizce atlanmaz, başarısızsa kurulumun sonunda kutulu uyarı.
- Başarılı izin `signing-partition.ok` işareti bırakır; Öz-test ve `doctor` eksikse uyarır; `update.sh` işaret yoksa derlemeye girmeden durur ve ne yapılacağını yazar (uygulama kapalıyken arka planda parola penceresi açılmaz). **Kurulu Mac'lerde ilk güncelleme bir kez** `sh ~/meeting-os/scripts/fix-signing-prompts.sh` ister.
- Kurulum anahtarı Keychain'in yanında uygulamanın 0600 dosyasına da yazar: yeni kurulumda uygulama Keychain'e hiç gitmez, Kurulum durumu kartı kırmızı yanmaz.
- Ayarlar ekranı Keychain'i okumaz (yalnız dosya); anahtar okuma kilitli (iki eşzamanlı köprü çağrısı iki pencere açamaz); reddedilen erişim tek satırla söylenir, tekrar sormaz.
- `git fetch` 120 sn bekçi ve parola sormaz; başarısız imzalama derleme artığı bırakmaz; belgeler (EKIP, KULLANIM, OPENROUTER, README) yaşam döngüsündeki gerçek pencerelerle bire bir.

**“Yalnız bu bölüm” (ikinci görüş: 1 P0, 2 P1)**
- Sabitlenen bölüm kümenin defterinden düşüldü: sonraki küme adlandırması onu “önceki isim” saymaz (⌘Z bütün konuşmacıyı o kişiye boyamıyordu → düzeltildi), o kişiye ret yazmaz, otomatik tanıma kümenin geri kalanı için çalışmaya devam eder.
- ⌘Z bölüm düzeltmesini de geri alır (etiket, örnek, gizlenen örnek). Karne bölüm düzeltmesini modelin hatası saymaz. Kişi kartından alınan temiz örnekler bölümü sabitlemez.
- Çalma bitince ▶ hemen geri döner; ⌘. bir sayfa açıkken “vazgeç” olarak kalır; bölüm seçici ⌘F filtresinden etkilenmez.

<a id="v1241"></a>
### Meeting OS 1.2.41 — dinlemeyi durdur; “Yalnız bu bölüm” düzeltmesi

2026-09-10 14:40 · yerel not · GitHub sürüm sayfası yok

Boran'ın iki isteği:
- **Dinlemeyi durdurma.** ▶ düğmesi çalarken ■ olur ve aynı düğme durdurur; **⌘.** (Git menüsü → Dinlemeyi durdur) her yerden durdurur; kayıt başlarken çalan ses kesilir. Transkript, İsimler kartı, Kontrol, Düzelt penceresi ve kişi kartındaki bütün dinleme düğmeleri.
- **Tek bölüm yanlış kişiye gittiyse.** Düzelt penceresinde yeni **Yalnız bu bölüm** düğmesi: sadece o bölüm yeni adı alır, konuşmacının geri kalanı ve mevcut profili olduğu gibi kalır, kimse “yanlış” sayılmaz (ret kaydı yazılmaz). Bölüm en az 6 sn temiz konuşmaysa doğru kişinin ses profili ondan öğrenir; kısa/karışıksa yalnız etiket yazılır. Paragraf birden çok bölümden oluşuyorsa hangi bölüm olduğu üstteki menüden seçilir. Sonraki küme adlandırmaları ve ⌘Z bu bölümü atlar.

Ayrıca: `docs/CHANGELOG.md` — 45 sürümün notu tek dosyada; bütün günlük ve artefaktların dizini en üstte (`scripts/changelog-index.py` üretir).

<a id="v1240"></a>
### Meeting OS 1.2.40 — Anahtar Zinciri pencereleri bitti; ⌘M işaretleri düzeldi

2026-09-10 14:05 · yerel not · GitHub sürüm sayfası yok

**Anahtar Zinciri (bugünkü pencere fırtınasının kalan iki kaynağı)**
- codesign: kurulumun oluşturduğu imzalama anahtarı bölüm listesi taşımadığı için her derleme/güncellemede parola soruyordu ve "Her Zaman İzin Ver" tutmuyordu. Kurulum artık bu izni bir kez veriyor; kurulu Mac'lerde **güncellemeden sonra bir kez** Terminal'de çalıştırın (Mac parolanızı bir kez sorar): `sh ~/meeting-os/scripts/fix-signing-prompts.sh`
- Swift birim testleri Keychain'i okumuyor (xctest pencereleri).
- Pencereler "Reddet"e rağmen kapanmıyorsa kuyruğu tutan SecurityAgent sürecini kapatın: `pkill -9 SecurityAgent`.

**Kayıt**
- ⌘M işaretleri kayıt sırasında hiç yazılmıyordu; düzeltildi. İşaretler artık uyku ve yeniden başlatma boşluklarından bağımsız, transkriptle aynı saatte.
- Kayıt yardımcısında bekçi durumu kilitle korunuyor; ses yazma kuyruğuna saniyede 12 bloklayan çağrı kalktı.
- `scripts/verify-capture.py` parçaların 16-bit olduğunu ve kırpılmış örnek sayısını raporluyor (son gerçek kayıt: 0 kırpılmış).

Güncelleme: `cd <depo> && sh scripts/update.sh` ya da uygulamadaki "Güncelle ve yeniden başlat"; ardından yukarıdaki fix-signing-prompts adımı.

<a id="v1239"></a>
### Meeting OS 1.2.39 — Keychain'e yalnız uygulama dokunur; yankı süzgeci kendi sesinizi silmiyor

2026-09-10 12:04 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.39)

**Keychain (Boran'ın "terminalden çıkmaya devam ediyor" bildirimi)**
- Python tarafı (işler, testler, betikler) artık Anahtar Zinciri'ne hiç dokunmuyor: anahtar ya ortam değişkeninden ya da uygulamanın bir kez yazdığı 0600 dosyadan okunur. Anahtar yoksa "uygulamayı bir kez açın" der. Terminal kaynaklı Keychain pencereleri bitti.

**Ses yolu denetimi (kayıt yardımcısı + birleştirme)**
- Yankı süzgeci kulaklıkla konuşurken ortak sessizlik yüzünden mikrofon pencerelerinin %18–30'unu "yankı" sayıp siliyordu (30 s'lik delikler). Eşik 0,5 → 0,8, gecikme ±1 s → ±400 ms; gerçek hoparlör yankısı yine %100 yakalanıyor.
- Ölü bir akışta durdurma başarısız olunca son parça (12 s'ye kadar) yazılmıyordu; artık her durumda yazılır.
- Mikrofon da sistem sesi gibi uzun parçalarla gönderilir (30 s'lik 119 kesik yerine 12 parça): kelimeler ortadan bölünmüyor, ASR bağlam görüyor, istek sayısı azalıyor.

Kalan (sonraki sürüm): ⌘M işaretleri duvar saatinde, transkript ses saatinde (uyku sonrası kayma); 16-bit parçalarda olası kırpma doğrulaması.

Güncelleme: `cd <depo> && sh scripts/update.sh` ya da uygulamadaki "Güncelle ve yeniden başlat".

<a id="v1238"></a>
### Meeting OS 1.2.38 — Keychain penceresi: süreç başına en fazla bir kez

2026-09-10 11:57 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.38)

Boran'ın bildirdiği "Her Zaman İzin Ver diyorum, birer birer sürekli çıkıyor": eski sürümler anahtarı her 2 saniyelik yoklamada Anahtar Zinciri'nden okuyordu; güncelleme imzayı değiştirince her okuma yeni bir pencere açıyordu.

- 1.2.37: anahtar bir kez okunup uygulamanın 0600 dosyasına alınır.
- 1.2.38: dosya yazılamasa bile anahtar süreç başına en fazla bir kez Anahtar Zinciri'nden okunur; pencere kuyruğu oluşamaz.

Etkilenen Mac'te: Meeting OS'i kapatın (⌘Q), `cd ~/meeting-os && sh scripts/update.sh`, uygulama açılınca bir kez "Her Zaman İzin Ver".

<a id="v1237"></a>
### Meeting OS 1.2.37 — Keychain artık bir kez sorar; bütünleşme düzeltmeleri

2026-09-10 11:45 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.37)

**Keychain sorusu** — Boran'ın bildirdiği "Her Zaman İzin Ver dedim, yine soruyor": her güncelleme uygulamanın kod imzasını değiştirdiği için macOS her yeni yapıda yeniden soruyordu. Artık anahtar Anahtar Zinciri'nden **bir kez** okunur ve uygulamanın kendi klasöründeki yalnız size açık bir dosyaya (`openrouter.key`, 0600) alınır; sonraki açılışlar, güncellemeler ve bütün işler dosyayı okur. Bu sürüme geçince en fazla bir kez daha sorar.

**Bütünleşme incelemesi (15 bulgu)**
- Teşhis raporları toplantı başlığı ve konuşmacı adlarını yalnız "metni de ekle" açıkken içerir (Ayarlar'daki açıklama artık doğru).
- Hafıza sorusu ve içe aktarılan dosya yolu komut satırından kalktı.
- Kişi tanıma durum makinesi: bir kümeyi yeniden eski kişiye adlandırmak o kişinin reddini kaldırır (kişi kalıcı tanınmaz hâle gelmiyor); geri alma yalnız kendi eklediği örneği siler; S1/S10 önek çakışması; her yeniden adlandırma aynı model hatasını yeniden saymaz; geri alma etiketi boşaltmaz.
- Boşalma sırasında ⌃⌥R "Kayıt başladı" demez; "Önceki kayıt kapanıyor · birkaç saniye sonra tekrar deneyin".
- Uzun toplantılarda yeniden başlatma/uyku sayaçları tüm günlükten okunur; öldürülen finalize sınırsız yeniden denemez.
- Ayar/nabız/rapor dosyaları atomik ve 0600 yazılır (ekip klasörü okunabilir kalır); `answer-*.json` silinir; toplu adlandırma ⌘Z ile toplu geri alınır; Zoom taraması tek geçiş ve boşta kadans; güncelleme boşalma penceresini bekler.

Testler: Swift 128, Python hedefli modüller yeşil; kimlik tekrarı 14/0/2 sabit.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1236"></a>
### Meeting OS 1.2.36 — güncellemeler yalnız yayınlanmış etiketlerden

2026-09-10 11:00 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.36)

- Uygulamadaki güncelleme kontrolü ve `update.sh`, artık `origin/v0.1` üzerindeki en yeni `vX.Y.Z` etiketini hedef alır. Etiketten sonra atılan ara commit'ler (belge, yarım iş) ekip Mac'lerine hiç gitmez; her güncelleme bu sayfadaki bir sürüme karşılık gelir.
- Geliştirme Mac'inde her commit'i izlemek için `MEETING_OS_UPDATE_UNTAGGED=1`.
- Bu, kamuya açık daldan imzasız kod çekme riskini azaltır ama kapatmaz; imzalı commit doğrulaması ya da özel depo kararı hâlâ Boran'da.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1235"></a>
### Meeting OS 1.2.35 — zehirli sözlük savunması

2026-09-10 10:57 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.35)

Ekip klasöründen gelen bir sözlük girdisi analiz modelini yönlendirebiliyordu (kurgusal vaka: açılıma gömülü talimat gerçek görevi düşürüp "müşteri listesini dışarı gönder" görevi ekletti). Artık:

- Sözlük açılımları yalnız isim tamlaması: ilk cümle, 80 karakter; talimat kalıbı içeren girdi boş geçilir.
- Analiz promptu sözlüğü de güvenilmez veri sayar; içindeki istekler maddeye dönüşmez.
- Bir madde, içerik kelimelerinden hiçbiri kendi alıntısında geçmiyorsa görevse atılır, özet/karar ise "kontrol edin" işareti alır (uydurma ya da dışarıdan gelen maddeler kanıtın arkasına saklanamaz).
- Model sahibi boş bırakırsa, "Ben … yapacağım" diyen adlı konuşmacı sahip olur; yanlış bir ad verirse eskisi gibi çekimser kalır.

Bulut kıyası: 6 vaka 5/5 (zehirli sözlük dahil), sızıntı 0; 12 çağrı ≈ 1,6 cent.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1234"></a>
### Meeting OS 1.2.34 — gizlilik düzeltmelerine ikinci görüş

2026-09-10 10:50 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.34)

Bağımsız inceleme 1.2.33'ün gizlilik düzeltmelerinde 9 boşluk buldu; hepsi giderildi.

- OpenRouter'a giden **her** ses parçası (mikrofon dahil, ayrımsız modeller dahil) sağlayıcıdan veri saklamamasını ister; 1.2.33 bunu yalnız ayrımlı isteklerde yapıyordu. Kırık kalan test düzeltildi.
- Silinen toplantının yeniden-deneme çalışma alanı, deponun sertleştirilmiş kaldırıcısıyla (inode/uid/0700/beyaz liste) ve veritabanı işlemi **bittikten sonra** siliniyor; kaldırılamayanlar gizlenmiyor, raporlanıyor.
- Rapor hata süzgeci noktalı istisna adlarını (`sqlite3.OperationalError` gibi) yine yakalıyor; raporun kendi hataları da görünüyor.
- Rapor silme her kökü ayrı deniyor (iCloud'da takılı bir dosya ekip klasöründeki kopyayı bırakmıyor).
- Hatırlatıcı silme tam satır eşleşmesi ve yalnız varsayılan listede ("Sync" silinince "Sync retro" gitmez).
- Ekip klasöründeki rapor klasörü ekipçe okunabilir kalır (0700 yalnız kişisel klasörde).
- Yeniden deneme (resume) eski işin başlığını taşımaz.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1233"></a>
### Meeting OS 1.2.33 — gizlilik denetimi, belgeler arayüzle bire bir

2026-09-10 10:36 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.33)

**Gizlilik/güvenlik denetimi (15 bulgu, 6 P0)**
- `last-job.log` artık yalnız sahibi okuyabilir ve toplantı metni içermez (uygulamanın başlattığı analiz/soru işleri makbuz basar). Ekip rehberi bu dosyayı "gönderin" diyordu.
- Rapor hata süzgeci satır başına bağlı: "Error" kelimesi geçen bir transkript satırı ekip klasörüne kopyalanmaz.
- Yerel modda canlı önizleme metni günlüğe yazılmaz.
- Toplantı silinince çökmüş yeniden-deneme kopyaları, önceki rapor klasörlerindeki raporlar ve Hatırlatıcılar'daki tamamlanmamış aktarımlar da silinir; veritabanı silinen sayfaları sıfırlar.
- Ayar/rapor/sözlük dosyaları ve klasörler yalnız sahibine açık; OpenRouter'dan veri saklamaması isteniyor (`data_collection: deny`); sözlük analiz için güvenilmez veri; güncelleyiciye API anahtarı geçmiyor; toplantı başlığı komut satırından kalktı (her kullanıcı görebiliyordu).

**Belgeler**
- README, KULLANIM, EKIP ve iki-Mac belgesi arayüzle bire bir (30 düzeltme): bölüm adları, ⋯ menüsü, Gelişmiş, "Adlandır ve öğren", 5 dk Zoom toleransı, CLI komutları, eksik kontroller (Yalnız bu toplantıda, İşlemi sürdür/iptal, geri alınan karar, Haftalık bakım).
- Gizlilik cümleleri gerçeğe uygun: neyin kendiliğinden dışarı çıktığı, silmenin neyi kapsadığı, Hatırlatıcılar istisnası.

Yapılmayan (karar gerekiyor): `update.sh` kamuya açık daldan imzasız kod çekiyor — imzalı commit doğrulaması ya da depoyu özel yapmak Boran'ın kararı.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1232"></a>
### Meeting OS 1.2.32 — brifing düzeltmesi

2026-09-10 04:29 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.32)

- 1.2.31'de "Brifing" dışa aktarımı bir ad-gölgeleme hatasıyla çöküyordu (tam paket yakaladı); düzeltildi.
- İlk açılışta yoklama ile iş aynı anda veritabanını göç ettirirse çökmesin diye son sütun göçü de korumalı.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1231"></a>
### Meeting OS 1.2.31 — analiz katmanında ikinci görüş

2026-09-10 04:25 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.31)

Bağımsız inceleme 1.2.30'un analiz değişikliklerinde sessiz kayıp riskleri buldu; hepsi giderildi, kıyas 5/5 (11 çağrı, ≈1,4 cent).

- Toplantı içinde geri alınan karar artık **silinmiyor**: Özet'te üstü çizili ve "Toplantı içinde geri alındı" notuyla kalıyor, Karar günlüğüne girmiyor. "İptal edilmeyecek" gibi olumsuzlamalar onay sayılıyor; aynı ürün alanındaki farklı kararlar birbirini iptal etmiyor.
- Alıntı kurtarma dolgu cümlesini kanıt sayamıyor (en az 3 içerik kelimesi + iddiayla ortak kelime); kurtarılan madde "kontrol edin" işaretiyle geliyor.
- Bir kişinin iki tarihsiz görevi artık tek göreve birleştirilmiyor.
- Aynı ada iki farklı yazımla iki kişi konuşuyorsa sahip tahmin edilmiyor.
- Devredilen görev yeni sahibiyle listede kalıyor.
- Sahip karşılaştırmaları (Bana ait, Beklediklerim, gün özeti, brifing) İ/I/ı yazımlarını aynı kişi sayıyor; brifing sabit "Boran" yerine ad ayarını kullanıyor.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1230"></a>
### Meeting OS 1.2.30 — ikinci görüş düzeltmeleri, boşta CPU, analiz kalitesi

2026-09-10 03:23 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.30)

**Güvenilirlik (ikinci görüş incelemesi, 11 bulgu)**
- Boş biten kayıt (hiç parça yok) artık boşta yeniden deneme kuyruğuna girmiyor; durdurulmuş boş kayıt "iptal" sayılır, "Kayıt tamamlanamadı" demez.
- SQLite `busy_timeout` ve korumalı şema göçü: yoklama ile iş aynı anda açılınca çökmez.
- Öneri onayı yalnız tam yazımda; "Ali"/"Alı" birbirinin eşiğini düşürmez. Geri alma yalnız son adlandırmayı çözer. Yeniden adlandırma gizli örnekleri taşımaz.
- "Adlandır ve öğren" kısa/kirli bölümde profil alamazsa ismi yine yazar ve söyler.
- Sözlük hiçbir durumda depo dosyasına yazılmaz (güncelleme kilidi tekrar edemez).

**Yük**
- Boşta CPU gerilemesi giderildi: her 6 saniyede ~180 ms yerleşim → ~10 ms (tepe %18 → %1).
- Kayıt sırasında saniyelik sayaç ve iş ilerlemesi ana pencereyi yeniden yerleştirmiyor.
- Her kayıt (Zoom şart değil) önceki toplantının yükleme/özet işini arka plan önceliğine alır, tek parça yükler.

**Analiz kalitesi (kurgusal fixture'larla ölçüldü)**
- Model iki ayrı alıntıyı birleştirince doğrulama bütün maddeyi atıyordu (iptal edilen karar kayboluyordu) → gerçek parça kurtarılır.
- Parçalar arası tekrar giderme, iptal edilen karar üstün, sahip adı normalizasyonu, uzun toplantıda daha geniş özet. İki zor vaka 2/5 → 5/5.
- Sahip filtresi İ/I/ı yazımlarını aynı kişi sayar.

Tam Python paketi (554 test) ve Swift (121 test) yeşil. Arayüz ekran doğrulaması kilit açılınca yapılacak.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1229"></a>
### Meeting OS 1.2.29 — kurul turu 4: 14 güvenilirlik düzeltmesi, sadelik, ekip belgeleri

2026-09-10 02:12 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.29)

Tur 3'ün 40 commit'i üç bağımsız denetçi ajan tarafından incelendi; bulguların tamamı bu sürümde, her biri testli.

**Kayıt asla kaybolmaz (14 düzeltme)**
- Bellek baskısında yalnız arka plan işi durur; canlı kayıt asla (eski tek-yuva kodundan kalan hata).
- Hiç parça üretmeden takılan yardımcı artık `--start-offset 0` ile yeniden başlatılabiliyor.
- Kurtarılabilir hatalarda (yardımcı geç kapandı, 5 yeniden başlatma) makbuz yazılır, toplantı özetlenir; "Kayıt tamamlanamadı" yerine sakin bir satır.
- Kayıt boşalırken nabız/bakım/boşta kuyruğu beklemede; iptal edilen iş boşta kuyruğunda yeniden başlamaz.
- "Ayse" ↔ "Ayşe" yazım farkı gerçek kişiyi reddetmez; silinen örnekler ⌘Z ile geri gelir; otomatik düzeltmeyi geri almak elle düzeltmeyi silmez.
- Çıkışta yeni iş başlamaz; `.partial.wav` süpürülür; "i" → "İ"; kişi eşiği tabanı; sözlük içe aktarma iCloud dosyasını ezmez; kurulum betiği sertifikayı iki kez içe aktarmaz.

**Sadelik (19 değişiklik)**
- Dürüst durum satırı ("Hazır · ⌃⌥R ile kayıt başlat"), siz kipi, "Güncelleme ara" / "Sorun var".
- OpenRouter anahtarı artık Ayarlar → Sistem'de; Sistem'de nadir kontroller "Gelişmiş" altında.
- Görev kartı, Kontrol sayfası ve "Konuşanı adlandır" sayfası daha az düğmeyle.

**Ekip**
- Sözlük kutusu artık depo dosyasına yazmıyor (güncelleme kilidi hatası bitti).
- EKIP.md: üç parola penceresi, iptal kurtarma, "Asla paylaşmayın", izinler ilk kayıttan önce, gizlilik cümleleri gerçeğe uygun (analiz tüm transkripti gönderir, raporda başlık ve isimler var).

Ekran kilitli olduğu için bu sürümün arayüzü henüz ekranda doğrulanmadı; birim testleri ve derleme yeşil.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1228"></a>
### Meeting OS 1.2.28 — yalın Ayarlar ve kenar çubuğu, kişi kartı, kişi bazlı eşik

2026-09-10 01:33 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.28)

**Yalınlık (Sprint C)**
- Ayarlar üç bölüm: Genel · Sesler ve sözlük · Sistem. Her kontrol yerinde, daha az sekme.
- Kenar çubuğu: Yeni kayıt, tek satır sürüm, toplantılar, durum, Ayarlar + ⋯ (ses dosyası aç, tanılama raporu). Yazıya çevirme modeli seçimi Ayarlar → Sistem'e taşındı.
- Görevlerim filtresi seçtiğiniz gibi kalır (varsayılan "Bana ait"); boşsa tek cümle ve "Bu toplantı" bağlantısı.
- Sözcükler: "Kontrol kuyruğu" → "Kontrol"; sağlayıcı adları yalnız Ayarlar'da.

**Öğrenme döngüsü (Sprint B)**
- Q9: bir kişiyi adlandırdığınız anda aynı toplantının diğer isimsiz sesleri yeniden puanlanır ("· 2 kişi daha önerildi").
- Q8: kişi kartı (Ayarlar → Sesler ve sözlük): örnekler, süre, en zayıf örnek, son toplantı; "Temiz örnek ekle…" ile en uzun temiz konuşmadan profil güçlendirme.
- Q5: kişi bazlı eşik — onayladığınız her öneri o kişinin eşiğini düşürür (en az 0,84), yanlış otomatik isim yükseltir; küresel eşik değişmedi. Kimlik tekrarı 14/0/2 sabit.

**Gözlemlenebilirlik**
- Nabız günde bir öz-testi de koşar; `reports summarize` uyarı listesiyle başlar (nabız yok, disk az, öz-test başarısız, bulutta bekleyen, kayıt takıldı).
- Canlı doğrulandı: yardımcı süreç öldürülünce kayıt aynı klasörde devam etti (24 → 36 → 48 sn), gerçek 401 doğru sınıflandı.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1227"></a>
### Meeting OS 1.2.27 — yarı yolda bırakmama, ekip kurulumu, öz-test

2026-09-10 01:08 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.27)

**Yarı yolda bırakmama (Sprint A)**
- T7: OpenRouter geçici hata verirse parça bazında 2/8/20 sn yeniden dener; anahtar geçersiz (401) ya da kredi bitti (402) ise dürüst tek satır gösterir ve boşta yeniden denemez. Reddedilen toplantı Mac boştayken (kayıt/Zoom/iş yokken) arka plan önceliğiyle kendiliğinden yeniden alınır (10 dk → 30 dk → 2 sa → 6 sa → günlük). Ses asla silinmez. Ayar: "Bulut hatasında boşta yeniden dene".
- T3/T6: kayıt yardımcısı ölür ya da takılırsa aynı klasöre kaldığı saniyeden devam eder (saatte en çok 5 kez); uyku/uyanmada akış proaktif yeniden kurulur; panelde "Kayıt devam ediyor · N sn boşluk". Kayıt sürerken dakikada bir nabız dosyası.

**Ekip (Sprint D)**
- Ayarlar → Genel → "Sizin adınız": mikrofon etiketi, "Bana ait" filtresi ve özetler artık sabit "Boran" değil.
- Tek komutla kurulum: `git clone -b v0.1 … ~/meeting-os && sh ~/meeting-os/scripts/install.sh` (araçlar, Python ortamı, ad, anahtar, sertifika, denetim). Ekip rehberi: `docs/EKIP.md` (gizlilik: ses/transkript Mac'te kalır, ses profilleri hiç çıkmaz).
- Ekip klasörü ayarı: sözlük ekipçe ortak, raporlar ekip klasörüne.

**Gözlemlenebilirlik**
- Ayarlar → Kurulum durumu → **Öz-test**: kayıt yardımcısı, ffmpeg, ses modeli, veritabanı, disk, anahtar, sözlük, rapor klasörü birkaç saniyede. CLI: `python -m meeting_os probe`.
- Kontrol → **Haftalık bakım**: zayıf ses örnekleri, öğrenilen metin kuralları, disk, bulutta bekleyen toplantılar.

Canlı denenmeyen: gerçek 401/429 yolu, yardımcı ölümü/uyku (gerçek akış gerekir), install.sh uçtan uca.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1226"></a>
### Meeting OS 1.2.26 — İsimler kartı, tek eylemli Düzelt, ⌘Z, öğrenme döngüsü

2026-09-10 00:53 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.26)

**Yalınlık (Sprint C)**
- Transkriptin üstünde "İsimler · N kişi bekliyor" kartı: satır başına dinle, öneriyi onayla, isim yaz ⏎ ya da takvim/profilden seç; birden çok öneri varsa "Hepsini onayla".
- Düzelt sayfası tek alan + tek eylem ("Adlandır ve öğren"); metin düzeltme, temiz örnek ve "Neden bu isim?" Gelişmiş altında.
- İsimler bitince bayat özet kendiliğinden yenilenir (kayıt/Zoom sırasında asla).
- ⌘Z / "Geri al": son adlandırma etiketleriyle, öğrenilen örneğiyle birlikte geri alınır.

**Öğrenme döngüsü (Sprint B)**
- Q4: yanlış otomatik isim düzeltilince o kümenin eski kişiye beslediği örnek silinir; ses o kişi için "reddedildi" olarak hatırlanır ve bir daha ona eşleşmez.
- Q6/Q7: iki farklı toplantıda aynı şekilde düzeltilen kelime kural olur, sonraki transkriptlerde kendiliğinden uygulanır (işaretli, geri alınabilir); sözlük terimiyle eşleşenler yanlış-duyma önerisi.
- Q10: haftalık öğrenme ilerlemesi (kendiliğinden tanıma oranı, 1000 kelimede düzeltme) Kontrol karnesinde.

Kimlik tekrarı değişmedi: 16 küme, 14 doğru, 0 yanlış, 2 atlanmış.

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1225"></a>
### Meeting OS 1.2.25 — kurul turu 3: güvenilirlik, gizlilik, kalite tekrarı

2026-09-10 00:32 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.25)

Kurul turu 3 · Sprint A (güvenilirlik + gizlilik) ve kalite Q1–Q3.

**Kayıt hiçbir şeyi beklemez**
- Kayıt kendi süreç yuvasında: süren bir özetleme işi ⌃⌥R'yi engellemez; biten toplantı kuyruğa girer, iş bitince sırayla işlenir.
- Kısayol debounce: ilk 3 sn yok sayılır; 15 sn'nin altında durdurmak için ikinci basış gerekir (yanlışlıkla durdurma yok).
- Yetim kayıt süreci kendini durdurur; güncelleyici her durumda uygulamayı yeniden açar; yedekler budanır.

**Toplantıda göze batmaz**
- Yüzen panel ekran paylaşımından dışlanır.
- Bildirimler pasif; kayıt/Zoom sırasında kuyrukta bekler; tek "Toplantı hazır".
- Kayıt sırasında ses oynatma kapalı; API anahtarı işlere uygulamadan geçer (toplantı ortasında Keychain penceresi yok).
- Zoom algılama tüm Spaces + paylaşım araç çubuğu + mikrofon-kullanımda koruması, 5 dk tolerans.

**Kalite**
- `quality replay`: toplantı-dışarıda-bırak kimlik tekrarı ve dolgusuz metin tekrarı (gerçek veri: 16 küme, 14 doğru, 0 yanlış, 2 atlanmış).
- Kimlik puanlama bağlı konuşmacı üzerinden (sağlayıcı alt kümeleri değil).

**Sadelik**
- Bitmiş toplantıya zorla geçiş yok ("Toplantı hazır · Aç" şeridi), tek işaret sözlüğü (An · Karar · Görev · Sonra).

Güncelleme: `cd ~/meeting-os && sh scripts/update.sh` (Zoom kapalıyken).

<a id="v1224"></a>
### Meeting OS 1.2.24 — arka uç sadeleştirme ve hız

2026-09-09 18:58 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.24)

Python tarafı: toplantılar arası benzerlik hesabı 3× hızlı (Beklediklerim, Kararlar, Sorular), ortak yardımcı modül, önbellekli hafıza, rapordaki FLAC boyutu hatası düzeldi, daha hızlı köprü başlangıcı, yeni veritabanı indeksleri. Uygulama boşta %0 CPU. Diğer Mac'te toplantı yokken: “Güncelle ve yeniden başlat”.

<a id="v1223"></a>
### Meeting OS 1.2.23 — sadeleştirme turu ve brifing

2026-09-09 18:27 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.23)

Görevlerim: satır başına üç kontrol + menü, tek Dışa aktar menüsü (Brifing, gündem, gün/hafta özeti). Toplantı öncesi brifing: sıradaki takvim toplantısının katılımcıları için sözler, sorular, kararlar. Hafıza’da tek arama alanı; karne Kontrol’e taşındı. Alt şerit kalktı, terimler ve kısayol metinleri tutarlı, ⌘1–⌘5 menüden. Performans: yoklama yalnız değişeni yayınlar, paragraf görünümü yeniden çizilmez, Zoom/mikrofon taraması boşta 6 sn. Diğer Mac'te toplantı yokken: “Güncelle ve yeniden başlat”.

<a id="v1222"></a>
### Meeting OS 1.2.22 — soru radarı, karne, vade önerisi

2026-09-09 18:14 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.22)

Hafıza sekmesinde Sorular (toplantılar arası cevapsız sorular, tekrar edenler üstte, ‘muhtemelen cevaplandı’ ipucu) ve Karne (son 7 gün: saat, karar, görev, soru, ücret; toplantı başına konuşma payı). Görevlerim’de vade önerisi: transkriptteki ‘yarın / haftaya salı / ay sonu’ ifadeleri tarihe çevrilir, onaylayınca Hatırlatıcılar’a 09:00 alarmıyla gider. Boş kütüphanede karşılama ekranı; menü çubuğunda ‘Son toplantıyı aç’. Diğer Mac'te toplantı yokken: “Güncelle ve yeniden başlat”.

<a id="v1221"></a>
### Meeting OS 1.2.21 — sadeleştirme ve daha hafif yoklama

2026-09-09 18:00 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.21)

Ayarlar beş bölüme ayrıldı; kenar çubuğunda yazıya çevirme seçenekleri tek satıra katlandı; başlıktaki teknik satır ve transkriptteki fazla bilgi satırı kaldırıldı. Durum yoklaması yalnız değişen veriyi taşır (her 2 saniyede bir tüm transkriptin yeniden gönderilmesi bitti). Diğer Mac'te toplantı yokken: “Güncelle ve yeniden başlat”.

<a id="v1220"></a>
### Meeting OS 1.2.20 — tema ve vurgu rengi

2026-09-09 17:54 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.20)

Ayarlar (⌘,) → Görünüm: Sistem / Açık / Koyu tema ve altı vurgu rengi (yeşil, mavi, lacivert, turuncu, gül, grafit). Yüzen kayıt paneli de temayı izler. Diğer Mac'te toplantı yokken: “Güncelle ve yeniden başlat”.

<a id="v1219"></a>
### Meeting OS 1.2.19 — belge gibi okuma görünümü

2026-09-09 17:43 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.19)

Transkriptin okuma görünümü belge gibi: kart kabuğu yok, zaman solda, aynı konuşmacının paragrafları başlıksız sürer, konuşmacı değişiminde ayraç, dar metin sütunu; ekrana çok daha fazla paragraf sığar. Diğer Mac'te toplantı yokken: “Güncelle ve yeniden başlat”.

<a id="v1218"></a>
### Meeting OS 1.2.18 — kayıt uyku/uyanmada kopmaz

2026-09-09 17:40 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.18)

Kayıt yardımcısı ses akışı durursa ya da 20 sn ses gelmezse akışı kendiliğinden yeniden kurar (uyku/uyanma, ekran değişimi); disk azalınca kaydı öldürmek yerine uyarır (3 GB uyarı, 400 MB durdurma). Güncelleme kayıt yardımcısını yeniden derler. Diğer Mac'te toplantı yokken: “Güncelle ve yeniden başlat”.

<a id="v1217"></a>
### Meeting OS 1.2.17 — ses dosyaları 3–4× küçüldü

2026-09-09 17:37 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.17)

Tamamlanan kayıtların sesi kayıpsız 16-bit FLAC’e çevrilir (41 dk: 313 MB → ≈82 MB; çalma ve ses profili aynen çalışır), kayıt parçaları 16-bit yazılır, eski toplantıların sesi ayarlanan gün sonra kendiliğinden silinir (varsayılan 30 gün; yazı kalır). Ayarlar → Depolama → “Sesleri sıkıştır” mevcut kayıtları da çevirir. Güncelleme kayıt yardımcısını da yeniden derler. Diğer Mac'te toplantı yokken: “Güncelle ve yeniden başlat”.

<a id="v1216"></a>
### Meeting OS 1.2.16 — kurul turu: sağlamlık, PM haftası, arayüz

2026-09-09 17:29 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.16)

Sağlamlık: köprü çağrıları kendi kuyruğunda, toplantı sırasında başlayan iş Zoom açılınca kendini arka plana alır, okuma görünümü önbellekli, saatlik kalp atışı raporu, hafif durum yoklaması. PM: Hafıza’da Karar defteri ve Beklediklerim, Görevlerim’de Hafta özeti, Kontrol’de 7 günlük kontrol borcu. Arayüz: başlıkta özet şeridi ve sekme rozetleri, konuşmacı adını başlıktan menüyle değiştirme, kanıta kaydırıp vurgulama, yüzen panelde mikrofon/sistem sinyali, kenar çubuğunda sürüm satırı ve “Kontrol et”. Diğer Mac'te toplantı yokken: “Güncelle ve yeniden başlat”.

<a id="v1215"></a>
### Meeting OS 1.2.15 — kenar çubuğu grupları ve klavye kısayolları

2026-09-09 17:07 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.15)

Kenar çubuğu: Bugün / Dün / Bu hafta / Daha eski grupları, “Bugün 14:05” gibi okunur saat, arama her zaman görünür ve konuşmacı adıyla da bulur. Klavye: ⌘1–⌘5 sekmeler, ⌘F konuşmada ara, ⌘⇧F hafızada ara, Esc aramayı temizler. Diğer Mac'te toplantı yokken: “Güncelle ve yeniden başlat”.

<a id="v1214"></a>
### Meeting OS 1.2.14 — toplantıyı asla yavaşlatma

2026-09-09 15:10 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.14)

Arka plan işleri (yükleme, kişi tanıma, analiz) düşük öncelikte; Zoom toplantı penceresi açıkken en düşük öncelik, nice 10 ve tek yükleyici. Zoom açıkken güncelleme başlamaz (düğme “Güncelleme toplantı bitince”), güncelleme derlemesi nice 19. Boşta yoklama 6 sn. Her işin CPU/bellek/süre bilgisi iCloud raporuna yazılır. Diğer Mac'te: toplantı bittikten sonra “Güncelle ve yeniden başlat”.

<a id="v1213"></a>
### Meeting OS 1.2.13 — kurulum kartında teşhis raporu durumu

2026-09-09 14:55 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.13)

Kurulum durumu kartı teşhis raporu paylaşımının açık/yazılabilir olduğunu ve kaç rapor yazıldığını gösterir; diğer Mac'ten rapor gelmiyorsa nedeni burada. Diğer Mac'te: “Güncelle ve yeniden başlat”.

<a id="v1212"></a>
### Meeting OS 1.2.12 — izinleri yerinde düzelt, ⌘,

2026-09-09 14:52 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.12)

Kurulum durumu kartında eksik izin için “İzin iste” (hiç sorulmamışsa) ya da “Ayarları aç” (reddedilmişse ilgili Sistem Ayarları bölmesi). ⌘, ayarları açar. Diğer Mac'te: “Güncelle ve yeniden başlat”.

<a id="v1211"></a>
### Meeting OS 1.2.11 — kurulum durumu kartı

2026-09-09 14:42 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.11)

Ayarlar’ın başında Kurulum durumu: mikrofon/ekran/takvim/hatırlatıcı/bildirim izinleri, OpenRouter anahtarı, sözlük, sürüm. İkinci Mac’te eksik izinleri tek bakışta gösterir. Diğer Mac'te: “Güncelle ve yeniden başlat”.

<a id="v1210"></a>
### Meeting OS 1.2.10 — Görevlerim sayaçları

2026-09-09 14:38 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.10)

Görevlerim filtrelerinde açık görev sayıları; Boran’a atanmış görev yokken sekme toplantının görevleriyle açılır. 13:35’ten beri: yüzen kayıt paneli, toplu sözlük düzeltmesi, konuşma payı, kenar çubuğu arama/süre, takvim bağlamı, Zoom elle dokunmadan kayıt (isteğe bağlı), bulut maliyeti kartı, Türkçe eklere dayanıklı hafıza araması, Hatırlatıcılar’a görev gönderme. Diğer Mac'te: “Güncelle ve yeniden başlat”.

<a id="v129"></a>
### Meeting OS 1.2.9 — görevler Apple Hatırlatıcılar’a

2026-09-09 14:34 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.9)

Görevlerim’de “Hatırlatıcılar’a ekle”: görev varsayılan listeye eklenir, notunda kaynak toplantı/sahip/zaman ifadesi. İlk kullanımda Hatırlatıcılar izni istenir. Diğer Mac'te: “Güncelle ve yeniden başlat”.

<a id="v128"></a>
### Meeting OS 1.2.8 — Hafıza araması Türkçe eklere dayanıklı

2026-09-09 14:23 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.8)

Hafıza sekmesindeki arama ve “Kayıtlardan yanıtla” Türkçe ekleri tolere eder (modülleri → modülü), işlev sözcüklerini atar; gerçek soruda kaçan kanıt artık bulunuyor. Diğer Mac'te: “Güncelle ve yeniden başlat”.

<a id="v127"></a>
### Meeting OS 1.2.7 — bulut maliyeti kartı, panelde toplantı adı

2026-09-09 14:21 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.7)

Ayarlar’da bu ay/toplam gerçek OpenRouter transkript harcaması; yüzen kayıt panelinde toplantı adı; Zoom elle dokunmadan kayıt yalnız gerçek toplantı penceresini sayar. Diğer Mac'te: “Güncelle ve yeniden başlat”.

<a id="v126"></a>
### Meeting OS 1.2.6 — Zoom’da elle dokunmadan kayıt, Kontrol’de takvim katılımcıları

2026-09-09 14:10 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.6)

İsteğe bağlı: Zoom toplantı penceresi 10 sn açık kalınca kayıt kendiliğinden başlar, pencere kapanınca 1 dk sonra biter (elle başlatılanlara dokunmaz; Ayarlar → Kayıt sırasında). Kontrol sekmesinde isimsiz konuşmacılar takvim katılımcılarından tek tıkla adlandırılır; menü çubuğunda o anki takvim etkinliği görünür. Diğer Mac'te: “Güncelle ve yeniden başlat”.

<a id="v125"></a>
### Meeting OS 1.2.5 — takvim bağlamı

2026-09-09 14:03 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.5)

Kayıt başlarken takvimdeki toplantının adı başlık olur, katılımcıları konuşmacı adlandırmada tek tıkla seçilir (Ayarlar → Kayıt sırasında; takvim yalnız okunur, varsayılan kapalı). Ayarlar sayfası ekrana göre uzar ve kaydırma çubuğu görünür. Diğer Mac'te: “Güncelle ve yeniden başlat”.

<a id="v124"></a>
### Meeting OS 1.2.4 — konuşma payı, kenar çubuğu araması ve süreleri

2026-09-09 13:51 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.4)

Özet sekmesinde kişi başına konuşma payı çubukları; kenar çubuğunda toplantı arama ve her kaydın süresi/kişi sayısı (boş kayıtlar “Konuşma bulunmadı”); kanıt alıntılarında dolgu sesleri gizli. Diğer Mac'te: “Güncelle ve yeniden başlat”.

<a id="v123"></a>
### Meeting OS 1.2.3 — yüzen kayıt paneli, toplu sözlük düzeltmesi

2026-09-09 13:43 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.3)

1.2.1–1.2.3 ara sürümleri: başlıktan yeniden adlandırma, transkript/analiz bitince bildirim, otomatik başlık, kayıt sırasında her pencerenin üstünde duran yüzen kayıt paneli, Kontrol sekmesinde “Doğrulananları uygula” ve “Yoksay”, silinen toplantının iCloud raporu da silinir. Diğer Mac'te: kenar çubuğundaki “Güncelle ve yeniden başlat” yeterlidir.

<a id="v120"></a>
### Meeting OS 1.2.0 — Kontrol, sözlük, güncelleyici, menü çubuğu

2026-09-09 13:29 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.2.0)

Bulut transkript (MAI-Transcribe 2) ve analiz (gpt-4.1-mini), kişi tanıma ve profil bakımı, Kontrol sekmesi, proje sözlüğü (iCloud), tek tık güncelleyici, iki Mac raporları, menü çubuğu ve ⌃⌥R/⌃⌥M, Zoom bildirimi, belge/gün sonu özeti/paylaşım maskesi, depolama temizliği.

<a id="v110"></a>
### Meeting OS 1.1.0 — OpenRouter transkript ve kişi tanıma

2026-09-09 10:06 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.1.0)

MAI-Transcribe 2 ile Türkçe transkript ve konuşmacı ayrımı, yerel ses profilleriyle toplantılar arası tanıma, gpt-4.1-mini özet/görev, Kontrol sekmesi, ⌘R/⌘M, yankı atlama, ekran uykusu koruması.

<a id="v105"></a>
### Meeting OS 1.0.5 — düşük bellekli transkripsiyon

2026-09-08 09:14 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.0.5)

16 GB Mac için CPU tabanlı quantize turbo varsayılanı; model süreçlerinde bellek/süre denetimi; canlı kayıt işçilerinin izolasyonu ve ana süreç ölürse alt süreçlerin kapanması. Kapak kapalı mikrofon uyarısı.

Bu Mac üzerinde entegre import15.45s, canlı40s kayıt, ikinci kayıt finalize19.52s ve sentetik ses profilini yeniden tanıma testleri geçti. Türkçe-English kısa örnek7.96s içinde işlendi.87 Python ve9 Swift testi geçti. Claude Code incelemesi yapıldı.

Özet modeli mevcut masaüstü yükünde bellek baskısına takılıyor; küçük alternatif kalite testini geçmedi.16GB cihazlarda otomatik özet ertelenir, elle başlatma korunur ve denetlenir. Doğal çok konuşmacılı toplantı kalitesi henüz doğrulanmadı.

Kaynak kod ve ilk kurulum paketi; modeller ve bağımlılıklar ilk kurulumda indirilir. Notarize bağımsız uygulama değildir. Giriş ve ücretli API gerekmez.

<a id="v104"></a>
### Meeting OS 1.0.4 — kurulum ve durdurma düzeltmeleri

2026-09-08 09:14 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.0.4)

Kurulum artık isteğe bağlı büyük Whisper modelini otomatik indirmez. Hugging Face Xet/CAS varsayılan olarak kapalı, HTTP zaman aşımı 120 saniye. Kayıt yardımcısı durdurmaya yanıt vermezse 15 saniye sonra sonlandırılır; tamamlanmış ses parçaları korunur. Native model çağrısının iptali için bu süre garantisi geçerli değildir.

76 Python testi (75 genel + ek indirme ayarı testi), 9 Swift testi ve native derleme geçti; Claude Code incelemesi tamamlandı.

Bu paket kaynak kod ve kurulum başlatıcısıdır; notarize edilmiş bağımsız uygulama değildir. İlk kurulum internetten yerel modelleri ve bağımlılıkları indirir. Giriş veya ücretli API gerekmez. Doğal 3–5 toplantı ve ikinci Mac kurulumu henüz doğrulanmadı.

<a id="v103"></a>
### Meeting OS 1.0.3 — Bellek koruması

2026-09-08 09:14 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.0.3)

Bellek koruması — 1.0.3

16 GB Mac üzerinde büyük Whisper testi ciddi bellek baskısıyla masaüstü oturumunun çökmesine katkıda bulundu. Bu sürüm import/finalize için turbo varsayılanını kullanır; büyük model 32 GB altında yüklenmeden reddedilir. MLX önbelleği sınırlandı; uygulama kendi işlem belleğini ve OS bellek uyarılarını izler. Kayıt dosyaları silinmez.

İşlem aşaması/bölüm sayısı/geçen süre görünür. Kayıt durdurulduğunda kuyruktaki canlı çözümleme tekrarları atlanır; bütün kalıcı ses nihai işlemede kullanılır.

ZIP'i indirip açın ve yeni klasördeki Meeting OS.command dosyasını çalıştırın. Apple Silicon/macOS15+ gerekir. Kaynak/kurulum paketidir; eski kurulumun üstüne dosyaları gelişigüzel kopyalamayın. Bu Mac'teki kurulum yerinde güncellendi.

70 Python ve 9 Swift testi; ardından 4 odaklı kaynak koruma testi geçti. Büyük modelin yüklenmeden reddedilmesi doğrulandı. Çökme sonrası ağır model testi tekrarlanmadı. M2 üzerinde yeni ölçüm yok; turbo tam büyük modelle aynı doğruluk garantisi vermez. Ayrıntılı olay raporu ZIP içindeki docs/CRASH_RECOVERY_1.0.3.md dosyasındadır.

<a id="v102"></a>
### Meeting OS 1.0.2 — İlk kurulum düzeltmesi

2026-09-08 09:14 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.0.2)

Yeni Mac için düzeltilmiş ilk kurulum (1.0.2).

1. Assets bölümündeki MeetingOS-source-v1.0.2.zip dosyasını indirin; giriş gerekmez.
2. ZIP’i açın, MeetingOS klasörünü iCloud dışında yerel bir klasöre taşıyın.
3. Bu yeni klasördeki **Meeting OS.command** dosyasını çift tıklayın.
4. İlk kurulum gerekli araçları ve modelleri indirir. Homebrew/Mac parola veya Apple geliştirici araçları penceresi çıkarsa adımları tamamlayın; araç kurulumu bittikten sonra aynı dosyayı yeniden açın.

Apple Silicon Mac ve macOS15+ gerekir. İnternet bağlantısını ve Terminal penceresini açık tutun. Bu Apple tarafından noterlenmiş bağımsız uygulama değildir; macOS dosyayı engellerse Sistem Ayarları → Gizlilik ve Güvenlik içindeki bildirimi inceleyin.

Eski 1.0.1 paketindeki başlatıcı yalnızca kurulu uygulamayı açıyordu; yeni Mac için eksikti. Bu sürüm ilk kurulumu başlatır, hata halinde pencereyi açık tutar. Üç başlatıcı testi geçti; temiz ikinci Mac’te tüm bağımlılık/model kurulumu henüz doğrulanmadı. Kaynak paketinde kişisel toplantı verileri yoktur.

<a id="v101"></a>
### Meeting OS 1.0.1 — Mac kurulum paketi

2026-09-08 09:14 · [GitHub](https://github.com/borankaraduman-star/meeting-os/releases/tag/v1.0.1)

Meeting OS 1.0.1 — diğer Mac için kaynak ve kurulum paketi.

**İndir:** Aşağıdaki Assets bölümünden `MeetingOS-source-v1.0.1.zip` dosyasını alın.
İndirmek için GitHub hesabı veya giriş gerekmez.

**Gereksinimler:** Apple Silicon (M1/M2/M3/M4 vb.), macOS 15+, Xcode Command Line Tools, Python 3.12 ve ffmpeg. Intel Mac desteklenmiyor.

1. ZIP’i açın; MeetingOS klasörünü iCloud dışında yerel bir klasöre taşıyın.
2. Terminal’de bu klasöre geçip `sh scripts/setup.sh` çalıştırın. Önkoşullar eksikse önce kurun; Homebrew kullanıyorsanız Python/ffmpeg için `brew install python@3.12 ffmpeg`. Xcode araçları için `xcode-select --install`.
3. Kurulum tamamlanınca `open "build/Meeting OS.app"` çalıştırın.
4. İlk kayıtta macOS mikrofon ve ekran/sistem sesi izinlerini onaylayın.

Bu kaynak/kurulum paketidir; sürükle-bırak kurulabilen bağımsız uygulama değildir.
Modeller ilk kurulumda internetten ayrıca indirilir. Toplantı veritabanı ve kişisel
ses profilleri bu pakette yoktur. Ücretli API gerekmez.

62 Python ve 7 Swift testi geçti. Gerçek 3–5 toplantıyla kalite ve uzun kayıt
dayanıklılığı henüz doğrulanmadı; GUI izinleri yeni Mac’te ayrıca tamamlanmalıdır.

SHA-256: `91d506f4795d7dab2536cf0006c7206b5a19432607896145c4cba23a4f772cf9`
