# Ekip bulutu (team cloud): sıfır kurulumlu ortak bilgi tabanı

Tarih: 2026-09-10 22:40. Boran: "bunların hepsini sen yapmalısın; ekip arkadaşlarımın uygulama açılırken bir şey
yapmasını isteyemem, sistem full hazır olmalı."

## Neden

1.2.63'teki ekip bilgi tabanı bir **klasöre** dayanıyordu: `team_dir` (kullanıcı seçer) ya da iCloud Drive
`MeetingOS-Shared`. iCloud Apple-ID'ye özel (ekip arkadaşına asla ulaşmaz) ve diğer Mac'te kapalıydı; ekip klasörü
seçmek ise her kullanıcıdan bir işlem ister. İkisi de "kur ve unut" değil. Bu belge klasörün yerine geçen
sunucuyu ve istemciyi tanımlar. **Eski klasör yolu kaldırılmıyor:** `team_dir` seçilmişse o kazanır (aynı ağdaki
bir NAS'ı tercih eden ekip için), iCloud da bulut yoksa yedek olarak kalır.

## İlkeler

- **Sıfır kurulum.** Ekip kimliği OpenRouter anahtarından türetilir (`sha256("meetingos-team-v1:" + anahtar)`).
  Aynı anahtarı kullanan Mac'ler aynı ekiptir; kimse bir şey seçmez, yapıştırmaz. Farklı anahtarla kurulan bir Mac
  için `team.token` dosyası (`MEETING_OS_TEAM=<token> sh scripts/install.sh` ya da `meeting_os team join <token>`)
  aynı ekibe alır. Token asla depoya yazılmaz (depo herkese açık).
- **Yerel ayna.** Sunucu, mevcut klasör düzeninin aynasıdır: istemci `~/Library/Application Support/MeetingOS/team/`
  klasörünü "ekip klasörü" olarak kullanır (`reports.team_dir` bulut yapılandırılmışsa bu klasörü döndürür) ve
  `team_cloud.sync` bu klasörü sunucuyla eşitler. `team_knowledge`, `glossary`, `reports` DEĞİŞMEZ: hepsi klasöre
  yazıp klasörden okumaya devam eder. Sunucu düşerse uygulama yerel aynadan çalışır; hiçbir öğrenim kaybolmaz.
- **Sunucu aptaldır.** Ekip başına, host başına dosya saklar. Birleştirme istemcide: her Mac yalnız KENDİ
  dosyalarını yükler, diğerlerininkini indirir. İki Mac'in aynı dosyayı yazması mümkün değildir; yarış yoktur.
- **Asla toplantıyı yavaşlatma.** Ağ çağrıları hızlı köprüde (10 sn bekçi) yapılmaz: adlandırma/öğretme
  kancaları `sync_async` (arka plan iş parçacığı, tek seferde bir eşitleme) çağırır; saatlik `storage_housekeeping`
  ve açılıştaki `team_sync` (yavaş köprü) bloklayan `sync` çağırır. Bağlantı 5 sn, toplam bütçe 20 sn. Hata asla
  yükselmez; `team-cloud-state.json`'a yazılır, kurulum kartı gösterir.
- **Gizlilik, klasörle aynı.** Yüklenen şey klasöre yazılanın aynısı: ad + ses vektörü, öğretilen kelimeler, sözlük,
  tanılama raporları (`share_text` kapalıysa metin yok), redakte edilmiş hata günlüğü. Ses, transkript, toplantı
  başlığı yok. Sunucu Boran'ın VPS'inde, TLS Tailscale Funnel'dan.

## Sunucu

`server/sync_server.py` — yalnız stdlib (Python 3.12), `ThreadingHTTPServer`, 127.0.0.1:8790, depo
`/var/lib/meetingos-sync/<team_id>/…`. `team_id = sha256(token).hexdigest()[:32]`; ham token diske yazılmaz,
loglanmaz.

Kimlik: `Authorization: Bearer <token>` (token: 32–128 hex). Host: `X-Meeting-OS-Host` (`^[A-Za-z0-9._-]{1,64}$`).
Yol öneki: hem `/v1/…` hem `/meetingos/v1/…` kabul edilir (Funnel `--set-path /meetingos` öneki soyabilir de
bırakabilir de).

İzinli yollar (regex, başka hiçbir şey yok):

    ^(words|glossary|profiles|errors)/<host>\.jsonl$
    ^reports/<host>/[A-Za-z0-9._-]{1,120}\.json$

`PUT`/`DELETE` yalnız `<host>` == `X-Meeting-OS-Host` olan yollara (403 yoksa). `GET` ekipteki her dosyaya.

| Uç | Yanıt |
|---|---|
| `GET /v1/ping` | `{"ok":true,"version":"1","time":"<utc iso>"}` — kimlik istemez |
| `GET /v1/index` | `{"files":{"<path>":{"sha256":"…","size":n,"updated":"<utc iso>"}}, "hosts":[…]}` |
| `GET /v1/file/<path>` | ham içerik, `ETag: "<sha256>"`; `If-None-Match` eşleşirse 304 |
| `PUT /v1/file/<path>` | gövde ham içerik; `{"sha256":"…","size":n}`; atomik yazım (tmp + rename) |
| `DELETE /v1/file/<path>` | `{"deleted":true}` (yoksa da true) |

Sınırlar: dosya 4 MB (413), ekip toplamı 500 MB (413), gövde `Content-Length` zorunlu. Hatalar JSON
`{"error":"…"}`. Yanlış/eksik token 401, yasak yol 403, olmayan dosya 404. Erişim günlüğü: zaman, ekip kısa id
(ilk 6), host, yöntem, yol, durum — token yok.

Dağıtım: `server/meetingos-sync.service` (systemd, `Restart=always`, `User=meetingos`, `ProtectSystem=strict`,
`ReadWritePaths=/var/lib/meetingos-sync`), `server/deploy.sh` (scp + `systemctl restart` + ping denetimi),
`server/backup.sh` (günlük tar → `/var/backups/meetingos-sync/`, 14 gün). Funnel:
`tailscale funnel --bg --set-path /meetingos http://127.0.0.1:8790` → `https://hermes-vps.tail2d8c7e.ts.net/meetingos`.

Testler `tests/test_sync_server.py`: sunucuyu rastgele portta iş parçacığında açar; kimlik, yol beyaz listesi,
host sahipliği, atomik yazım, 304, boyut sınırı, önek toleransı.

## İstemci

`meeting_os/team_cloud.py`:

- `DEFAULT_URL = 'https://hermes-vps.tail2d8c7e.ts.net/meetingos'`; ayar `team_url` ('' = varsayılan).
- `token(data_dir)`: `data_dir/team.token` (0600) varsa o; yoksa `data_dir/openrouter.key`'den türetilir; ikisi de
  yoksa None. (`openrouter.key` dosyası `data_dir` altındadır, bu yüzden testler gerçek anahtarı asla görmez.)
- `mirror_dir(data_dir) = data_dir/'team'` (0700).
- `configured(settings, data_dir)`: token var ve `team_dir` seçilmemiş.
- `reports.load_settings` sonucu `_mirror` anahtarını taşır (bulut yapılandırılmışsa ayna yolu; `save_settings`
  yazmadan önce düşürür); `reports.team_dir(settings)` = `team_dir` ya da `_mirror`. Böylece `report_root`,
  `glossary.team_path`, `team_knowledge.shared_root` kendiliğinden aynayı kullanır.
- Ayna düzeni (klasörle bire bir): `team-words.jsonl`, `glossary.jsonl` (**yalnız diğer host'ların** terimleri),
  `profiles/<host>.jsonl`, `reports/<host>/…`.
- `sync(data_dir, settings=None, budget=20.0)` → sözlük (`pushed`, `pulled`, `hosts`, `error`), asla yükseltmez:
  1. **İlk çalıştırmada tohum:** ayna boşsa ve iCloud `MeetingOS-Shared/profiles/<host>.jsonl` varsa kopyala;
     `team-words.jsonl`'den kendi satırlarını al; `MeetingOS-Reports/<host>/heartbeat.json` kopyala.
  2. **Yükle (yalnız kendi dosyalarım):** `profiles/<host>.jsonl` (ayna), `words/<host>.jsonl` (aynadaki
     `team-words.jsonl`'in `host==ben` satırları), `glossary/<host>.jsonl` (yerel `data_dir/glossary.jsonl` +
     gerçek veri klasöründe iCloud paylaşımlı sözlük, `merge_into` mantığıyla birleşik), `reports/<host>/*.json`,
     `errors/<host>.jsonl` (`errors.jsonl` kopyası; `share_reports` kapalıysa raporlar ve hatalar yüklenmez).
     `team-cloud-state.json` `pushed[path]=sha256`; değişmeyen dosya yüklenmez.
  3. **İndir (yalnız diğerleri):** `index`'ten `host != ben` dosyaları; `pulled[path]=sha256` ile aynı olanlar
     atlanır. `profiles/<other>.jsonl` → ayna; `words/<other>.jsonl` → aynadaki `team-words.jsonl` = kendi
     satırlarım + bütün diğerlerinin satırları (yeniden yazılır); `glossary/<other>.jsonl` → ayna `glossary.jsonl` =
     diğerlerinin birleşimi; `reports/<other>/*.json` → ayna. Sunucuda artık olmayan bir başkasının dosyası
     aynadan silinir (bir ekip arkadaşının `forget`/silmesi böyle ulaşır).
  4. Durum: `last_ok`, `last_error` (sınıf adı + kısa mesaj), `hosts` (index'teki host listesi), `team_id_short`.
- `sync_async(data_dir)`: daemon iş parçacığı, modül kilidiyle tek seferde bir; hızlı köprü kancaları bunu çağırır.
- `team_knowledge.sync`: publish_words + publish_profiles (aynaya yaz) → `team_cloud.sync` (yapılandırılmışsa) →
  pull_words + pull_profiles (aynadan oku). `desktop.share_profiles` (adlandırma sonrası) publish'ten sonra
  `sync_async`.
- `setup_status`: `team_root_kind` → `'cloud'` (yeni), `team_cloud: {url, host, team_id_short, last_ok, last_error,
  hosts}`; Swift `teamRootCheck`: cloud + last_error → `.optional` "bulut şu an erişilemiyor (…)" (varsa
  "· son başarılı eşitleme HH:MM", yoksa "; yerel bilgi korunuyor, bağlanınca eşitlenir") — **hata, eski bir
  `last_ok`'i bastırır**; cloud + yalnız last_ok → `.ok` "ekip bulutu · N Mac · son eşitleme HH:MM"; cloud henüz
  hiç denenmemiş → `.optional` "ekip bulutu · ilk eşitleme bekleniyor".
- Nabız (`build_heartbeat`): `team_cloud: {last_ok, last_error, hosts}`.

### Davet (1.2.68): terminalsiz katılma

Ekibe katılmanın tek yolu kurulum satırıydı; "kullanacak insanlar terminal yazamaz" (Boran, 10 Eyl 2026). Aynı
yük artık iki zarfla taşınıyor — bir **bağlantı** ve bir **dosya** — ve ikisi de aynı `accept_invite`'a düşüyor.

- Yük: `{"v":1,"team":<token>,"url":<varsayılan değilse team_url>,"key":<istenirse openrouter.key>}`.
- `invite_payload(data_dir, include_key=False)` / `invite_url(...)` → `meetingos://join?team=…[&url=…][&key=…]`
  (yüzde kodlu) / `invite_file_text(...)` → `Meeting OS Daveti.meetingos-invite` içeriği (JSON). Token yoksa
  `invite_payload` `{'error': …}`, ötekiler `''`.
- `parse_invite(text)`: bağlantı **ya da** JSON **ya da** çıplak token. Doğrulama: token 32–128 onaltılık; adres
  `https` (yalnız `127.0.0.1`/`localhost` için `http`, test sunucusu); anahtar `[A-Za-z0-9._:-]{8,400}` — anahtar
  bozuksa **düşürülür**, davet yine de geçerlidir.
- `accept_invite(data_dir, text)`: `join` (0600 `team.token`) → anahtar **yalnız** davette varsa **ve** Mac'te
  `openrouter.key` **yoksa** yazılır (`O_EXCL`; var olan anahtar asla ezilmez) → `team_url` `save_settings` ile →
  `sync`. Dönüş `{joined, team_id_short, key_written, synced}`; hiçbir girdide yükselmez, hata Türkçe tek cümle.
- Köprü (veritabanı açmadan, `error_report` gibi): `team_invite {include_key}` → `{url, text, team_id_short,
  with_key}`, `team_join {invite}` → `accept_invite`, `team_status` → `status`.
- Uygulama: Info.plist'te `CFBundleURLTypes` (`meetingos`) + `CFBundleDocumentTypes`/`UTExportedTypeDeclarations`
  (`local.boran.meeting-os.invite`, `public.json`); `AppDelegate.application(_:open:)` → `Model.handleIncoming`
  → `team_join` → `TeamJoinSheet`. Swift tarafındaki saf yardımcılar `TeamInvite` (yük **ayrıştırılmaz**, yalnız
  URL tanıma + etkin hedef satırı + sonuç cümlesi).
- Ayarlar → Sesler ve sözlük → **Ekip**: ilk satır etkin hedef (`TeamInvite.target`), davet kopyala/kaydet/yapıştır,
  "Şimdi eşitle"; üç paylaşım anahtarı artık `team_dir` yerine **etkin hedefe** bakar (Codex P0 #1); ekip klasörü
  "Gelişmiş" altında.
- CLI `python -m meeting_os team status|sync|invite [--with-key]|join <bağlantı | dosya yolu | belirteç>`;
  `invite` bağlantıyı, dosya içeriğini ve eski kurulum satırını birlikte basar.
- `scripts/install.sh`: `MEETING_OS_TEAM` doluysa `team.token` yazar (0600); 6/6 çıktısında ekip durumunu söyler.
- Belgeler: EKIP.md (ekip bilgisi buluta gider, kurulum gerekmez; kim görür), TWO_MAC_WORKFLOW.md (iCloud artık
  şart değil), KULLANIM.md.

## Doğrulama

- Python: `tests/test_team_cloud.py` (yerel test sunucusuyla uçtan uca: iki sahte host, kelime/profil/rapor
  yükle-indir, `forget` yayılımı, ağ yokken sessiz hata, ayna kökü çözümü, token türetimi, `save_settings` `_mirror`
  düşürür) + `InviteTests` (bağlantı/dosya gidiş-dönüşü, anahtarın asla ezilmemesi, bozuk davetin cümleye dönmesi,
  çıplak token, köprünün üç eylemi) + mevcut `test_team_knowledge`/`test_desktop`/`test_glossary`/`test_reports` yeşil.
- Swift: `TeamInviteTests` (join bağlantısı ile transkriptin `meetingos://word` bağlantısını ayırma, davet dosyası
  uzantısı, etkin hedef satırı, katılma sonucu cümlesi) + `SetupStatusTests` (hata eski `last_ok`'i bastırır).
- Canlı: bu Mac 1.2.67 ile açılınca `team_sync` → sunucuda `profiles/Boran-MacBook-Air.jsonl` + `reports/…/heartbeat.json`;
  diğer Mac güncellenince aynı ekipte görünür (`index.hosts` 2), profilleri buraya iner.
