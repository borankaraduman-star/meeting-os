# Kayıt durumu, canlı önizleme ve kullanıcı notları — sözleşme ve kabul eşlemesi

Dayanak: `/Users/boran/dev/meetingos-granola/ONERILER.md` (üç özgün öneri, `0e2ab1b` snapshot'ı). Granola kodu
ürüne **kopyalanmadı**, yeni Granola araştırması yapılmadı. Bu belge, paralel çalışan sekiz parçanın uyduğu tek
sözleşmeyi (A/B/C), ONERILER.md'deki sentetik kabul satırlarının hangi testte karşılandığını ve dosya sahipliğini
kaydeder. Gerçek koddaki bir adla uyuşmayan yerde parçalar en küçük uyarlamayı yapar ve raporunda `Uyarlama:`
satırıyla bildirir; bu belge sözleşmeyi, rapor uyarlamayı anlatır.

İlkeler değişmez: **kayıt asla kaybolmaz** (20 sn watchdog, 3'lük restart bütçesi, disk eşikleri, chunk kapanışı,
gap, ayrı mic/system dosyaları, journal/kurtarma/checkpoint ve 1.2.88 yankı kurtarması aynen), **toplantı asla
yavaşlamaz** (capture callback'i STT/ağ beklemez), **metin buluta yalnız beyaz listeyle çıkar** (notlar listeye
eklenmez), ses/metin günlüğe yazılmaz.

## A. Kayıt oturumu — gerçek ses kanıtına bağlı durum

**Sorun.** `App.swift` alt süreç başlamadan `recording=true` yapıyordu; yardımcının `started` olayı yalnız “akış
kuruldu” demektir, ilk mikrofon/sistem buffer'ının geldiğini ispatlamaz. `CaptureSignalPresentation.swift` kanal
başına unknown/silent/signal/stale ayrımını zaten yapıyordu; yeni sözleşme bunları tek oturum modelinde birleştirir.

- **Oturum kimliği.** `meeting_os/live.py` `record` her kayıt için bir session UUID üretir, her yardımcı
  başlatmada `--session <uuid> --launch <n>` geçer; relaunch'ta `n` artar. Argüman yoksa yardımcı kendi UUID'sini
  üretir (launch 0). Argümanı tanımayan eski yardımcı = **schema 1**.
- **Yardımcı satırları** (`capture/Sources/MeetingCapture/main.swift`): her JSON satırı `session`, `launch` taşır;
  `started` ek olarak `schema:2, epoch:0`; `restarted` `epoch` taşır. Yeni olaylar:
  - `{event:'permission', kind:'microphone'|'screen_audio', state:'requested'|'granted'|'denied'}`
  - `{event:'first_buffer', source:'mic'|'system', epoch, seq, host_time, silent:bool}` — kaynak+epoch başına
    bir kez, ilk geçerli PCM'de (peak 0 → `silent:true`).
  - `{event:'channel_flow', source, state:'signal'|'silent'|'stalled', epoch, seq}` — yalnız geçişte;
    silent = ≥2 sn peak 0, stalled = o kaynaktan >5 sn buffer yok.
  - Ses kuyruğunda ağır iş yok: kilitli küçük durum yapısı, `emit` kuyruk dışında.
- **Python durumu.** `meeting_os/desktop.py` `capture_state` mevcut anahtarları korur, ekler: `schema`, `session`,
  `session_state: 'awaiting_permission'|'awaiting_stream'|'receiving'|'stopped'|'failed'`,
  `channels: {mic|system: {state:'awaiting_first_buffer'|'silent'|'signal'|'stalled'|'unverified', epoch,
  age_seconds}}`. Yalnız **en son session/launch** satırları sayılır; eski oturumun geç satırı yok sayılır.
  Schema 1 journal → kanallar `unverified`, eski anahtarlar aynı. `live.py` stdout `capturing` satırı `session`
  taşır.
- **Uygulama.** `preparing` ve `finishing` uygulamada türetilir (`CaptureSessionState.swift`, saf). Faz sırası
  `preparing → awaiting_permission → awaiting_stream → receiving → finishing → stopped/failed`. Farklı session ya
  da önceki kayıt klasörüne ait yanıt yok sayılır. **İzin beklerken başlangıç zaman aşımı işlemez**; akış
  kurulduktan 5 sn sonra ilk buffer yoksa **uyarı** (hata değil; ürün hedefi, ölçüm değil). `preparing`'de Stop →
  hayalet kayıt/süre yok, bekleyen olay sonraki oturuma taşınmaz. Kanal etiketleri: “İlk ses bekleniyor”,
  “Ses geliyor · sessiz”, “Sinyal var”, “Akış kesildi”, “Doğrulanamadı”. Genel yeşil yalnız en az bir kanal
  sinyal/sessiz buffer alırken. `CaptureSignalPresentation.swift` geriye uyumludur (schema 1 payload aynı metin).
  `StopEscalation`, receipt ve `finishRecordedMeeting` değişmez.

## B. Canlı önizleme — varsayılan kapalı, açık seçimle

**Sorun.** Bulut modunda metin kayıt sonunu bekler (`CloudTranscription.recordArguments` bulutta `--cloud`,
yerelde `--live`; bulut STT kayıt sonrası `cloud_finalize.finalize_capture`). Öneri: kalıcı 12 sn'lik WAV yolunu
ve kurtarma sözleşmesini bozmadan, kapanmış parçalardan **taslak** üreten ayrı, düşük öncelikli işçi.

- **Modül.** `meeting_os/preview_transcription.py`. Tembel DDL:
  `transcript_previews(meeting, session, source, span, epoch INTEGER, revision INTEGER,
  status 'partial'|'final'|'failed'|'unknown', text, audio_start REAL, audio_end REAL, updated,
  PRIMARY KEY(meeting, source, span))`, `span = <source>-<index:06d>`. Final `segments` ve kullanıcı
  düzeltmeleri ayrı kalır.
- **Stale-response kuralı.** `apply_preview(store, meeting, resp) -> 'applied'|'stale_epoch'|'stale_revision'|
  'other_session'`: küçük epoch reddedilir; aynı epoch'ta `revision <= kayıtlı` reddedilir; final partial'a dönmez.
- **Kuyruk ve cursor.** `PreviewWorker.offer(chunk_event)` **asla bloklamaz** (`put_nowait`), bellek kuyruğu ≤3;
  taşan iş kalıcı `<capture_dir>/preview-cursor.json` (atomik tempfile+fsync+replace) ve `capture-native.jsonl`
  chunk satırlarından sonra okunur. Span idempotency anahtarıdır; cevabı kaydedilmemiş dış çağrı `unknown` olur
  (ücret tekrarı tamamen önlenemez, bilinmeyen olarak görünür). Kaynak zamanı `audio_start/audio_end` kuyruk
  boyunca taşınır. Reconnect'te epoch artar.
- **Durdurma ve bütçe.** `stop(grace=PREVIEW_STOP_GRACE_SECONDS=5)` + cancel; süre aşılırsa kaynak ses ve notlar
  korunur, nihai yol normal sürer. `PreviewPolicy(upload_allowed, max_chunks, max_audio_seconds, max_age_seconds,
  max_cost_usd)`; aşımda önizleme `paused`, **kayıt sürer**.
- **Gizlilik.** `upload_allowed=False` → adaptör hiç kurulmaz, **sıfır ağ çağrısı**. Mikrofon kapısı dışındaki mic
  parçası gönderilmez ama atılmaz/silinmez (1.2.88'de düzeltilen bütün-parça yankı kaybı geri gelmez); system
  parçasının mic'ten geç gelmesi mic sesini düşürmez.
- **Adaptör.** `transcribe_chunk(path, source, audio_start, duration, *, cancel) -> {text, final:bool, cost_usd}`.
  OpenRouter adaptörü mevcut toplu tek-parça çağrısını (`meeting_os/openrouter.py`) kullanır; **streaming
  varsayılmaz**. Aktif kayıtta `finalize_capture` çağrılmaz; yerel `--live` ve kayıt sonrası finalize aynen.
- **Bağlantı.** CLI `record --cloud-preview --allow-preview-upload [--preview-model M]` (izin bayrağı yoksa no-op +
  Türkçe not). Köprü eylemi `transcript_previews {meeting}` → `{session, state:'off'|'running'|'paused'|'stopped',
  reason, lag_seconds, rows:[{span, source, epoch, revision, status, text, audio_start, audio_end}]}`; metin yalnız
  yanıtta, günlükte değil. Swift `UserDefaults` `cloudLivePreview` varsayılan **false**; yalnız
  `mode == 'openrouter' && livePreview` iken `recordArguments` `--cloud-preview --allow-preview-upload` ekler.
  `PreviewDrafts.swift` (saf) final segmentlerin kapsadığı aralıkta taslağı gizler, revizyon/epoch geri gitmez;
  `TranscriptView.swift`/`TranscriptBlocks.swift` taslak satırlarını “Taslak” stiliyle gösterir, düzeltme ve
  adlandırma taslakta kapalı. Yoklama mevcut ritme bağlı; yeni sonsuz döngü yok.

## C. Kullanıcı notları — transkriptten ayrı

**Sorun.** `store.correct_text` segment düzeltme geçmişini (`original_text`, `text_edits`) zaten tutuyor; ayrı bir
toplantı not belgesi yoktu. Not, transkript segmenti olarak yazılmaz; `correct_text` akışı değişmez.

- **Modül.** `meeting_os/notes.py`. Tembel DDL:
  `meeting_notes(id PK, meeting, pending_key, revision INTEGER, text, anchors TEXT json, updated)`,
  `note_revisions(note, revision, text, anchors, author 'user'|'ai_accepted', created, PK(note, revision))`.
- **CAS.** `save_note(store, *, meeting=None, pending_key=None, base_revision, text, anchors, author='user')` tek
  `BEGIN IMMEDIATE` transaction'ında karşılaştırır → `{ok:true, revision, note}` ya da
  `{conflict:true, revision, text, anchors}`; uyuşmazlıkta **ezmez**. Her revizyon `note_revisions`'ta kalır.
  `ai_accepted` yalnız açık `save_note` ile oluşur; AI metni editöre kendiliğinden girmez.
- **Kaynak bağlantısı.** Anchor `{id, source, start, end, segment?, segment_revision?}` — kalıcı kaynak ses zamanı;
  geçici preview satırına ya da DB row offset'ine bağlanmaz. `get_note` her anchor için
  `status:'ok'|'source_unavailable'` döner; kaynak silinince not kalır, sahte alıntı üretilmez.
- **Kayıttan önce yazılan not.** `pending_key` = kayıt klasörü UUID'si; `claim_pending(store, pending_key,
  meeting)` atomik sahiplenir.
- **Köprü.** `note_get{meeting|pending_key}`, `note_save{meeting|pending_key, base_revision, text, anchors}`,
  `note_history{meeting}`, `note_claim{pending_key, meeting}`; Türkçe hata cümlesi, ham istisna yok.
- **Kapsam.** Finalizer/retry/analiz notlara yazmaz. Notlar **hiçbir bulut yüküne** girmez (OpenRouter analizi,
  `team_cloud`, diagnostics/telemetry; `telemetry_schema.ALLOWED`'a eklenmez). Export `include_notes` varsayılan
  **false**, yanıtta açıkça belirtilir. `delete_meeting` notları da siler.
- **Masaüstü.** `NoteDocument.swift` (saf): clean/dirty/saving/conflict, 500 ms debounce (enjekte saat), odak
  kaybı/kayıt stop/çıkışta flush, `base_revision` CAS; conflict'te kullanıcı metni korunur — “Benim sürümümü
  kaydet / Diğerini al / Karşılaştır”; gösterge “Kaydediliyor…/Kaydedilmedi”. `MeetingNotesView.swift`:
  `TextEditor`, “Bu ana bağla”, anchor listesi + “Kaynak kullanılamıyor”, yazarlık etiketi. `Layout.swift`
  DetailView'da notlar bölmesi (kayıt sürerken de).

## Sentetik kabul eşlemesi (ONERILER.md → test)

Hepsi sahte yardımcı / sahte journal / sahte adaptör ve `tempfile` ile; gerçek ses, gerçek STT, gerçek toplantı
verisi yok. Test adları parça görevlerinde sabitlendi; gerçek metot adları parça raporlarındadır.

### 1. Kayıt durumu

| ONERILER.md satırı | Python | Swift |
|---|---|---|
| Process başladı, `started` var, PCM yok | `tests/test_capture_session_state.py`: `awaiting_stream`, iki kanal `awaiting_first_buffer` | `CaptureSessionStateTests`: PCM yok → “akış bekliyor”, ses doğrulandı iddiası yok |
| İzin 20 sn bekliyor, sonra ret | aynı modül: `permission requested` → `denied`, hiç `receiving` yok, `failed` + Türkçe mesaj | `CaptureSessionStateTests`: beklerken zaman aşımı yok, ret → failed |
| Mic sıfır PCM, system sinüs | `first_buffer silent:true` + system `signal` → mic `silent` (stalled değil) | `CaptureSessionStateTests`: “Ses geliyor · sessiz” / “Sinyal var” |
| Yeni oturumdan sonra eski oturumun geç buffer'ı | eski session/launch satırı yeni durumu etkilemez | `CaptureSessionStateTests`: farklı session/klasör yanıtı yok sayılır |
| Cihaz değişiminde kesinti, restart sonrası buffer | `stalled → restarted + first_buffer → signal`, gap saniyesi korunur | `CaptureSessionStateTests`: kesinti + restart |
| Başlatma reddi / hazırlıkta Stop | `tests/test_live_features_integration.py`: yardımcı ilk satırdan önce stop → canceled, sızıntı yok | `CaptureSessionStateTests`: preparing'de stop → hayalet kayıt/süre yok |
| Ek: mic var, system yok, STT yanıtsız | — | `CaptureSessionStateTests`: üç aşama ayrı, tek genel yeşil yok |
| Ek (native): ters sıralı mic/system callback'leri | `tests/test_capture_session_state.py`: zaman çizgisi bozulmaz | — |
| Ek (native): bir backend başlangıç hatası | aynı modül: bir kanalın hatası diğerini başarısız göstermez | — |
| Eski yardımcı uyumu | schema 1 → `unverified`, eski anahtarlar aynı; `tests/test_live.py`: `--session/--launch` geçilir, relaunch'ta launch artar | `CaptureSignalPresentationTests`: schema 1 metni aynı |

### 2. Canlı önizleme

| ONERILER.md satırı | Python (`tests/test_preview_transcription.py`) | Swift |
|---|---|---|
| 10 kapanmış parça, adaptör 60 sn bekliyor | `offer` bloklanmaz, bellekte ≤3, cursor kalanı saklar, lag görünür | — |
| Aynı chunk iki kez; yanıttan önce/sonra kesinti | tek satır; kaydedilmemiş çağrı `unknown` | — |
| System mic'ten 5 sn geç | mic parçası atılmaz, kapsamlar ayrı | — |
| İzin kapalı / gate dışı parça | sahte adaptör çağrı sayısı 0; parça diskte kalır | `CloudTranscriptionTests`: varsayılan argümanlar değişmedi, bayraklar yalnız openrouter+preview'da |
| Ağ kopması / bütçe / iptal | kayıt sürer, parçalar korunur, sonra finalize normal | `PreviewDraftsTests`: boş/paused açıklaması |
| Taslak “proje A”, final “proje B” + nota bağlama | `tests/test_live_features_integration.py`: preview span zamanına bağlı anchor finalize sonrası aynı, taslak final tarafından kapsanır | `PreviewDraftsTests`: final taslağı gizler |
| Ek: rev1 partial → rev2 final → rev1 | tek final satır, geri dönmez | `PreviewDraftsTests`: eski revizyon yok sayılır |
| Ek: epoch 2 sonra epoch 1 geç final | `stale_epoch`, uygulanmaz | `PreviewDraftsTests`: epoch geri gitmez |
| Ek: stop sırasında yavaş sağlayıcı | stop ≤ grace; finalize kaynak sesi işler | — |
| Varsayılan kayıt | `record()` `--cloud-preview` olmadan sıfır adaptör kurulumu; entegrasyon testinde de çağrı 0 | — |

### 3. Kullanıcı notları

| ONERILER.md satırı | Python (`tests/test_notes.py`) | Swift (`NoteDocumentTests`) |
|---|---|---|
| “Karar: deneme cuma” + finalizer metni değiştirir | not byte eşdeğer; transkript değişimi ayrı | — |
| Revision 3'ten iki pencere | biri 4, diğeri `conflict` (ezmez) | conflict'te kullanıcı metni korunur; eski revizyon yanıtı yeni durumu ezmez |
| Autosave transaction'ında kesinti | `execute`'a istisna → ya eski ya yeni tam revizyon | debounce birleştirme ve flush (debounce içindeki kaydedilmemiş metin sınırı) |
| Preview kaynağı final segmentlerle yeniden bölünür | anchor ses aralığı korunur | — |
| Segment/ses retention ile silinir | not kalır, `source_unavailable` | — |
| Notta özel metin, yalnız transkript analizi | OpenRouter analiz, `team_cloud`, diagnostics/telemetry yüklerinde not yok; `include_notes` export seçimi açık | — |
| Kayıttan önce yazılan not | `pending_key` → `claim_pending` sonrası toplantıya bağlı | pending → claim |
| Ek: transkript revizyonları sürerken not rev 5 | `tests/test_live_features_integration.py`: transkript olayı nota yazmaz | — |

**Gerileme koruması** (sırayla koşulur): `tests/test_live.py`, `tests/test_capture_state.py`,
`tests/test_capture_metrics.py`, `tests/test_echo_recovery.py`, `tests/test_recovery.py`,
`tests/test_retry_capture.py`, `tests/test_cloud_finalize.py`, `tests/test_openrouter.py`, `tests/test_mic_gate.py`,
`tests/test_desktop.py`, `tests/test_corrections.py`, `tests/test_team_cloud.py`, `tests/test_telemetry_schema.py`,
`tests/test_intelligence.py`; `cd desktop && swift build && swift test`; `cd capture && swift build`
(`scripts/build-capture.sh` değil — imza içerir).

## Dosya sahipliği (s1 parçaları)

| Parça | Dosyalar |
|---|---|
| yardimci-olaylari (A) | `capture/Sources/MeetingCapture/main.swift` |
| kayit-durumu-python (A) | `meeting_os/live.py` (yalnız başlatma/attach/reader, `capturing` satırı), `meeting_os/desktop.py` (`capture_state`), gerekirse `meeting_os/capture_metrics.py`; yeni `tests/test_capture_session_state.py`, `tests/test_live.py` eki |
| kayit-durumu-arayuz (A) | yeni `desktop/Sources/MeetingOS/CaptureSessionState.swift`; `CaptureSignalPresentation.swift`, `RecorderPanel.swift`, `App.swift` (yalnız start/stop/yoklama); yeni `CaptureSessionStateTests`, `CaptureSignalPresentationTests` eki |
| onizleme-arka-uc (B) | yeni `meeting_os/preview_transcription.py`; `meeting_os/live.py` (yalnız ana döngü chunk olayı), `meeting_os/cli.py` (`record` bayrakları, choices korunur), `meeting_os/desktop.py` (`transcript_previews`), gerekirse `meeting_os/openrouter.py`; yeni `tests/test_preview_transcription.py` |
| onizleme-arayuz (B) | `CloudTranscription.swift`, `SettingsSections.swift`/`SettingsSheet.swift`, `RecorderPanel.swift` göstergesi, yeni `PreviewDrafts.swift`, `TranscriptView.swift`, `TranscriptBlocks.swift`, `App.swift` (record argümanı + yoklama); `CloudTranscriptionTests`, yeni `PreviewDraftsTests` |
| notlar-arka-uc (C) | yeni `meeting_os/notes.py`; `meeting_os/desktop.py` (`note_*` eylemleri, export `include_notes`, `delete_meeting`); yeni `tests/test_notes.py` |
| notlar-arayuz (C) | yeni `NoteDocument.swift`, `MeetingNotesView.swift`; `Layout.swift`, `App.swift` (note köprüsü); yeni `NoteDocumentTests` |
| belgeler | bu belge, `docs/KULLANIM.md`, `docs/EKIP.md` “Buluta ne çıkar”, `docs/ITERATION_CHECKPOINT.md` sonu |

Çakışma sıcak noktaları (s2 entegrasyonunda birleşim ile çözülür): `App.swift` start/stop/yoklama,
`meeting_os/desktop.py` dispatch + `capture_state`, `meeting_os/live.py` attach/ana döngü, `meeting_os/cli.py`
choices, `RecorderPanel.swift`. Entegrasyon `tests/test_live_features_integration.py`'yi ekler.

## Ölçülmeyenler

Gerçek ScreenCaptureKit `first_buffer` zamanlaması, gerçek OpenRouter önizleme gecikmesi ve maliyeti (ONERILER'in
“12 sn pencere + 3 sn” hedefi), canlı Zoom ile iki pencereli not çatışması **ölçülmedi**. 5 sn ilk-buffer uyarısı
ve bütçe varsayılanları ürün hedefidir, ölçüm değildir. Kaynakta hazır olmak kurulu uygulamanın güncellenmesi
değildir.

## Entegrasyon uyarlamaları (s2)

Parçalar birbiriyle uyumlu ama yukarıdaki metinden farklı adlar kullandı; kod esas alındı, sözleşme şöyle okunur:

- **Önizleme adları.** Span kimliği `<source>:<start:.3f>` (`span_id`), indeks değil. İmleç kalıcı dosyada değil,
  `preview_sessions.cursor` satırında (aynı transaction'da cevapla birlikte). `transcript_previews {meeting}` yanıtı
  `previews` (satırlar) + `status` (işçinin satırı) taşır; s2 sözleşmenin üst düzey `state` (`'off'` = işçi hiç
  kurulmadı), `reason`, `lag_seconds` anahtarlarını da ekledi. Swift `PreviewDrafts.merge` `previews`/`status` okur.
- **Oturum kimliği toplantıda.** `live.record` session'ı toplantı metadata'sına `capture_session` olarak yazar;
  `desktop.capture_state` başka session damgalı her satırı (yeni bir `started` dahil) baştan eler — eski oturumun geç
  `started` satırı oturumu devralamaz. Satır damgasız (schema 1) yardımcı aynen okunur.
- **Önizleme yalnız bu oturumun güncel parçalarını alır.** `PreviewWorker(session=…)`; başka session'ın parçası ve
  yeni launch'ın parçasından sonra gelen eski launch parçası taslak almaz. Kural `offer()` ve `events.jsonl` geri
  okumasında aynıdır (sıra numarası = günlük indeksi). Kayıt tarafı değişmedi: her parça diskte, kuyrukta,
  watchdog'da ve relaunch ofsetinde sayılır; nihai geçiş hepsini okur. Fabrika imzası `factory(dir, meeting, session=None)`.
- **Hazırlıkta stop.** Stop, önizleme fabrikasından önce geldiyse işçi hiç kurulmaz (thread/adaptör yok); kayıt
  `canceled`. Uygulamada süreç hiç başlamadan durdurulan kaydın klasör UUID'si bir sonraki kayda geri verilir
  (`Model.reclaimNoteKey`), hazırlıkta yazılan not düzenleyicide kalır; süreç başladıysa iptal edilen toplantı
  listede kalır ve not ona `note_claim` ile bağlanır.
- **Durum yükü.** `capture_state` schema 2'de ek olarak `permission` (`{microphone|screen_audio: state}`) ve
  `stream_age_seconds` verir; Swift `CaptureSessionState` ret izni ve 5 sn uyarısını bunlardan, genel başarısızlığı
  köprünün Türkçe `message` cümlesinden gösterir.
- Entegrasyon testi: `tests/test_live_features_integration.py` (8 test; sahte yardımcı `test_live.FAKE_HELPER`,
  sahte adaptör, sahte OpenRouter istemcisi, tempfile).
