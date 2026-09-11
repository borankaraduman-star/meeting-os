# Öğrenme döngüsü — kullanıcı kararı, otomasyonun etkisi, ve ikisinin arasındaki çizgi

Bu belge 1.2.80 ile gelen **`learning_events`** kaydını, insan kararı ile otomatik etkinin nasıl ayrıldığını ve
saklama sınırlarını anlatır. Kaynağı: `docs/reviews/2026-09-11-codex-learning-loop.md` (P0 #1 ve #3).

Meeting OS bugün gerçekten öğrenir: ses profilleri, ret vektörleri, kişisel eşikler, kelime kuralları, sözlük.
Eksik olan **modelin öğrenmesi değil, ölçümün dürüstlüğüydü**. Aynı soru her ekranda başka cevap veriyordu,
çünkü kararlar üç ayrı tabloya, dışa aktarmalar ise hiçbir yere yazılıyordu.

## Döngü

```
Kullanıcı eylemi → yerel karar kaydı (learning_events) → kapsam/kanıt denetimi
      → aday kural veya tercih → ayrılmış veride kıyas → sınırlı etkinleştirme
      → sonraki toplantıda ölçüm → (gerileme varsa) geri alma
```

1.2.80 bu zincirin **ilk iki halkasını** kurar: karar kaydı ve dürüst sayım. Aday kural üretimi, kıyas ve
politika sürümleri sonraki sürümlerin işi (1.2.82 ve 1.2.85).

## `learning_events` tablosu

Yerel SQLite veritabanında, diğer geç tablolar gibi ilk kullanımda oluşur (`meeting_os/learning.py`).

| Alan | İçindeki tek şey |
| --- | --- |
| `id` | satır numarası |
| `time` | UTC zaman damgası |
| `action` | aşağıdaki listeden bir eylem adı (enum; listede olmayan ad **yazılmaz**) |
| `object` | **referans**: toplantı kimliği, görev kimliği, katlanmış kelime anahtarı, kişi adı, ekip kısa kimliği. Asla cümle, asla transkript |
| `version` | ilgili analiz ya da düzeltme sürümü (konuşmacı etiketi, bölüm numarası, analiz numarası) |
| `scope` | `segment` · `speaker` · `meeting` · `global` |
| `source` | `human` · `auto` |
| `outcome` | `applied` · `reverted` · `noop` |
| `undo_of` | geri alınan olayın `id`'si ya da boş |
| `app_version` | kaydı yazan uygulama sürümü |

**Eylemler:** `record_start`, `record_stop`, `name_confirm`, `name_correct`, `name_reject`, `segment_pin`,
`word_teach`, `word_forget`, `word_dismiss`, `glossary_apply`, `glossary_dismiss`, `review_resolve`,
`task_edit`, `task_due`, `summary_edit` (1.2.81 için ayrılmış, henüz hiçbir şey yazmıyor), `export_ok`,
`team_join`, `undo`.

### Hangi eylem nereden yazılır

| Eylem | Kaynak |
| --- | --- |
| `record_start` / `record_stop` | kayıt işi (`live.record`); veri klasörü `--db`'den gelir |
| `name_confirm` / `name_correct` / `name_reject` | `label_speaker`, `enroll` — hangisi olduğuna `learning.naming_action` **adlandırma uygulanmadan önce** karar verir |
| `segment_pin` | `label`, `label_segment` ("Yalnız bu bölüm") |
| `word_teach` / `word_forget` / `word_dismiss` | `learn_word`, `forget_word`, `word_dismiss` |
| `glossary_apply` / `glossary_dismiss` | `glossary_apply`, `glossary_apply_all`, `glossary_dismiss` |
| `review_resolve` | `accept_rule` / `reject_rule` — Kontrol'de başka iz bırakmayan tek kuyruk cevabı |
| `task_edit` / `task_due` | `action_update`, `task_set_due` |
| `export_ok` | `export`, `share_export` — **dosya yazılınca**. `share_preview` dışa aktarma değildir |
| `team_join` | `team_join` başarıyla döndüğünde |
| `undo` | `undo_correction`; `undo_of` geri aldığı adlandırma olayını gösterir |

### İki kural

**1. Bir insan kararı bir olaydır, kaç etkisi olursa olsun.** Bir kelimeyi öğretmek **tek** `word_teach`
yazar. O kuralın bu toplantıda düzelttiği yirmi bölüm de, sonraki toplantılarda düzelteceği her bölüm de
onun **etkisidir** ve hiçbiri olay yazmaz. Yirmi otomatik uygulamayı yirmi bağımsız insan onayı saymak, bu
tablonun önlemek için var olduğu hatadır.

**2. Kayıt hissedilmez.** `learning.record_event` asla hata fırlatmaz, ağa çıkmaz, geçmişi taramaz: bir
indeksli arama ve bir ekleme. Bütçe olay başına **≤10 ms** (`tests/test_learning.py` ölçer). Kayıt
başarısız olursa sessizce geçer — kullanıcının işlemi zaten başarılı olmuştur.

**Yeniden deneme çoğaltmaz:** aynı dakikada aynı `(action, object, version, outcome)` tek satırdır. `outcome`
anahtarın parçasıdır, çünkü aynı dakikada "bu doğru" ve ardından "hayır, düzelt" iki karşıt karardır.

## İnsan kararı mı, otomasyonun etkisi mi?

### Otomatik isimler: doğrulandı / yanlışlandı / incelenmedi

`quality.identity_report` artık üç kova sayar:

- **`auto_verified`** — kullanıcı bu kümeyi elle adlandırdı ve yazdığı ad otomatik adla aynı (katlanmış
  karşılaştırma: "Ayse" yazmak "Ayşe"yi onaylar).
- **`auto_falsified`** — kullanıcı adlandırdı ve otomatik adı bozdu.
- **`auto_unreviewed`** — **kimse dokunmadı.** Bu bir başarı değildir.

Önceki hesap, transkriptteki `speaker_name` otomatik adın kendisi olduğu için her dokunulmamış kümeyi
"model haklıydı" diye sayıyordu. `auto_precision` artık yalnız **incelenmiş** kümeler üzerinden ölçülür;
hiç inceleme yoksa `null`'dur — sıfır değil.

### Kelime öğretme ölçüm kapsamı

`quality.reference_set` iki yolu da okur:

- **Düzelt kutusu** → `text_edits` satırı (`via: 'text_edit'`).
- **"Düzelt ve öğret"** → segmentin kendisini yeniden yazar, düzenleme satırı **yazmaz**. Bu yol
  `pre_word_text` / `word_text` çiftinden okunur (`via: 'word_teach'`).

Aynı segment iki yoldan da geçmişse **bir** referans sayılır ve elle yazılan metin kazanır: kullanıcının son
sözü odur.

## Görev geçmişi (P0 #3)

- `memory.set_due_date` artık diğer alanlarla **aynı** `task_edits` satırını yazar (`field='due_date'`,
  önceki/sonraki değer). Takvim tarihi, kullanıcının en sık onayladığı alandı ve geçmişi olmayan tek alandı.
- `update_action` ve `set_due_date` isteğe bağlı bir **`reason`** alır: `inference_error` ("Çıkarım hatası")
  ya da `changed_later` ("Sonradan değişti"). Görevlerim → Düzenle sayfasında iki küçük radyo düğmesi;
  **varsayılan hiçbiri**. Seçili düğmeye tekrar basmak seçimi temizler.
- **Nedeni bilinmeyen değişiklik eğitim etiketi yapılmaz.** "Model yanlış çıkardı" ile "iş sonradan
  devredildi" veride aynı görünür ve zıt şeyler demektir.
- **Görev kimliği:** görev kimliği başlığın ve alıntılarının karmasıdır, yani yeniden analiz aynı sözü başka
  kelimelerle yazdığında **yeni** bir kimlik doğar. `Memory._carry_history` eski kimliğin bütün geçmiş
  satırlarını yeni kimliğe `carried_from` ile kopyalar. Eşleştirme `memory.same_task` — `dedupe_actions`'ın
  kullandığı kural (sahip aynı, normalize edilmiş başlık örtüşmesi), kimlik eşitliği değil.

## Ne dışarı çıkar

Nabız (`heartbeat.json`) **yalnız sayı** taşıyan bir `learning` bloğu kazandı:

```json
"learning": { "days": 7, "events": 12, "undo": 1,
              "actions": { "word_teach": 3, "name_confirm": 5, "task_due": 4 },
              "names": { "verified": 4, "falsified": 1, "unreviewed": 9 } }
```

Kelime yok, ad yok, başlık yok, kimlik yok. Ve bu blok, diğer bütün tanılama yükleri gibi
**`meeting_os/telemetry_schema.py`** beyaz listesinden geçerek çıkar (bkz. `docs/EKIP.md`, "Buluta ne çıkar").

`learning_events` tablosunun **kendisi hiçbir zaman yüklenmez.** Bu Mac'te kalır.

## Saklama

- **90 gün / 20 MB.** Saatlik bakım geçişi (`storage_housekeeping`) önce süresi dolanları, sonra bütçe
  aşılıyorsa en eskileri siler (`learning.prune`).
- Kaynak toplantı silindiğinde ona ait metinli öğrenme örneği de gider (mevcut `text_retention` yolu);
  öğrenilmiş kelime ve profil ayrı kalır — bu mevcut ürün sözleşmesidir.
- Olay kaydı ayrı bir veri platformuna dönüşmez: kullanıcı işleminde yalnız küçük yerel yazım, model çağrısı
  yok, ağ beklemesi yok, geçmiş taraması yok.

## Bunu okumak

```bash
meeting_os quality report     # kimlik karnesi: verified / falsified / unreviewed
meeting_os reports heartbeat  # learning bloğu dahil nabız
```

Python'dan: `learning.events(store, since=...)`, `learning.summary(store, days=7)`.
