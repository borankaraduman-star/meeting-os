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

1.2.80 bu zincirin **ilk iki halkasını** kurar: karar kaydı ve dürüst sayım. Kıyas, sınırlı etkinleştirme ve
geri alma 1.2.85 ile geldi — aşağıdaki “Deney ve geri dönüş” bölümü.

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
| `reason` | kararın nedeni, **yalnız uygulama dürüstçe biliyorsa**: `team_conflict` · `inference_error` · `changed_later` (enum; listede olmayan değer yazılmaz) |
| `app_version` | kaydı yazan uygulama sürümü |

**Eylemler:** `record_start`, `record_stop`, `name_confirm`, `name_correct`, `name_reject`, `segment_pin`,
`word_teach`, `word_forget`, `word_dismiss`, `glossary_apply`, `glossary_dismiss`, `review_resolve`,
`task_edit`, `task_due`, `summary_edit` (1.2.81 için ayrılmış, henüz hiçbir şey yazmıyor), `export_ok`,
`policy_promote`, `policy_rollback` (1.2.85; `source='auto'`),
`team_join`, `team_knowledge_ready`, `team_first_value`, `undo`.

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
| `team_knowledge_ready` | `team_knowledge.pull_profiles` — en az bir profil **gördüğü ilk** çekişte, bir kez |
| `team_first_value` | ekibin örneğinin ürettiği otomatik adın kullanıcı tarafından **ilk kez doğrulandığı** an, bir kez |
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

## Kelime döngüsü (1.2.84, #7)

Kelime öğrenmesinin eksik halkası model değil **ölçümdü**: hangi kelimenin ipucuna girdiği, ham STT'nin aynı
hatayı yine yapıp yapmadığı ve bugünün kurallarının eski örneklerde ne yapacağı görünmüyordu. Dört parça:

### 1. Aynı 900 karakter, kanıta göre sıralanıyor

Bulut STT'ye giden yazım ipucu bütçesi değişmedi; **harcanma sırası** değişti. Önceden dosyaların okunma
sırasına göre kesiliyordu, yani modelin her seferinde yanlış yazdığı kelime ile hiç yanlış yazmadığı kelime
aynı önceliğe sahipti. `glossary.rank_hint_terms` saf bir fonksiyon; sıralama şu:

1. **`repeat`** — öğretilmiş, ama **ham** transkript eski yazımı yine yazmış olan kelimeler. İpucu tam olarak
   bunlar için var: kural metni düzeltir, ipucu hatanın olmasını engellemeye çalışır.
2. **`recent`** — bu Mac'te son 30 günde öğretilenler.
3. **`verified`** — yerelde doğrulanmış diğer yazımlar: daha eski öğretmeler ve "bu doğru" denen kelimeler.
4. **`team`** — ekip arkadaşlarının öğrettikleri (`team_knowledge.hint_terms`).
5. **`entries`** — sözlük terimleri, `source_count` ve sonra dosya sırası.
6. **`vocabulary`** — kullanıcının düz listesi.

Katlanmış yazıma göre tekilleştirilir, bütçe dolunca durur. Sonuç **ne girdiğini (`hint_included`) ve kaç
terimin giremediğini (`hint_excluded`)** söyler: `openrouter-finalize` sonucunda ve toplantı metadatasında
terimlerle, toplantı raporunda **yalnız sayıyla** (rapor ekip klasörüne gider; kelime içeriktir). CLI:
`meeting_os glossary hint`.

### 2. Ekip çatışması kazanan seçmez, soru sorar

İki Mac aynı kelimeyi farklı öğrettiyse ve **bu Mac'te kendi kuralı yoksa**, eskiden *en yeni satır*
kazanıyordu — yani bir meslektaşın adının burada nasıl yazılacağına başka bir Mac'in saati karar veriyordu.
Artık hiçbiri uygulanmaz (`team_knowledge.team_rules` → `conflict`), ikisi de Ayarlar'da görünür ve Kontrol'e
tek bir madde gelir: **“Ekipte iki yazım: X / Y — hangisi?”** (`kind: word_conflict`).

- Madde normal Kontrol mekaniğiyle kapanır (`review.resolve_review`); anahtarı **kelimedir**, bölüm değil, bu
  yüzden bir kez cevaplanır. `source_version` iki yazımdan üretilir: ekip fikrini değiştirirse yeniden sorulur.
- Cevap **yerel bir kural öğretir** (`word_teach`, `reason='team_conflict'`) ve yerel kural her zaman sessizce
  kazanır. Kimsenin dosyasına dokunulmaz, kimseye yasak konmaz, çoğunluk oyu yoktur.
- İki Mac **aynı** yazımı öğrettiyse bu bir çatışma değildir: eskisi gibi uygulanır.

### 3. Tekrar eden hatayı ölçmek

`quality.word_repeat_errors(store, since_days)` her öğretilen kelime için, **kuraldan sonra** kaydedilmiş her
toplantıda tek bir soru sorar: ham transkript (`pre_auto_text` / `pre_word_text` / `original_text`) eski yazımı
yine içeriyor mu? İçeriyorsa ikinci soru: kullanıcının okuduğu **son** metinde düzeltilmiş mi?

- Bir (kelime, toplantı) çifti **bir** kontroldür: bir transkriptte kelime on kez geçse de bir sayılır.
- `fixed` / `unfixed` ayrımı önemlidir; “3 kez tekrar etti, hepsi düzeltildi” ile “3 kez tekrar etti, 2 tanesi
  düzeltilmedi” aynı cümle değildir.
- **Kelime bazlı sayılar yalnız burada kalır:** Ayarlar → Sesler ve sözlük → Öğrenilen kelimeler satırında.
  Günlük özet (`daily_summary.word_repeat_errors`) aynı fonksiyondan **havuzlanmış oranı** alır ve hiçbir
  kelime taşımaz.
- Kuraldan **önce** kaydedilmiş toplantı kanıt değildir; kural o transkripte yardım etmesi istenmemiştir.

### 4. Kuralları eski örneklerde yeniden çalıştırmak

`quality.replay_text` **modeli** puanlar ve kurallar hakkında bir şey söylemez, çünkü okuduğu çiftleri o günkü
kural kümesi üretmiştir. `quality.replay_rules(store)` aynı yerel (ham metin, son metin) çiftlerini alır ve
**bugünkü** kural kümesini ham yarısına uygular:

- `matched` — bugünkü kurallar kullanıcının bıraktığı metnin aynısını üretiyor.
- `mismatched` — üretmiyor. Bu tek başına gerileme demek değildir (kullanıcı cümleyi başka nedenle de
  düzeltmiş olabilir), bu yüzden puan değil **liste** verilir.
- `unchanged` — bugünkü kurallar o metne hiç dokunmuyor.
- Kural bazında `applied` (bugün) ve `was_applied` (o gün) ayrı durur; artık var olmayan bir kural `retired`
  diye listelenir. `version` (`correction_memory.rules_version`) hangi kural kümesinin ölçüldüğünü söyler.

Veritabanına hiçbir şey yazmaz, hiçbir segmenti değiştirmez. `meeting_os quality replay --text` çalıştırır.

### Sınırlar (bu maddede korunanlar)

- **Exact-only otomatik uygulama** aynen duruyor; yakın yazımlar hâlâ yalnız Kontrol önerisi.
- Bir kişinin "bu doğru" demesi **yerel** bir doğrulamadır; ekibe yasak olarak gitmez.
- Çoğunluğun yazımı, yerelde açıkça seçilmiş yazımın üstüne konmaz.
- Ham metin ve son metin çiftleri bu Mac'te kalır; rapora, nabza ve ekip klasörüne yalnız sayılar çıkar.

## Ne dışarı çıkar

Nabız (`heartbeat.json`) **yalnız sayı** taşıyan bir `learning` bloğu kazandı:

```json
"learning": { "days": 7, "events": 12, "undo": 1,
              "actions": { "word_teach": 3, "name_confirm": 5, "task_due": 4 },
              "names": { "verified": 4, "falsified": 1, "unreviewed": 9 },
              "team": { "team_join": "2026-09-11T08:00:00+00:00",
                        "team_knowledge_ready": "2026-09-11T08:00:42+00:00",
                        "team_first_value": "2026-09-11T10:14:00+00:00",
                        "join_to_ready_seconds": 42.0, "join_to_first_value_seconds": 8040.0,
                        "profile_effect": { "right": 2, "wrong": 0, "clusters": 31, "meetings": 9, "team_samples": 6 } } }
```

Kelime yok, ad yok, başlık yok, kimlik yok. Ve bu blok, diğer bütün tanılama yükleri gibi
**`meeting_os/telemetry_schema.py`** beyaz listesinden geçerek çıkar (bkz. `docs/EKIP.md`, "Buluta ne çıkar").

`learning_events` tablosunun **kendisi hiçbir zaman yüklenmez.** Bu Mac'te kalır.

## Kişi tanıma kalibrasyonu

Codex incelemesinin #5 ve #6 maddeleri (1.2.83). Üç parça: **kaynak sınıfı**, **ekibin gerçek katkısı**,
**eşik önerisi**. Hiçbiri üretim eşiğini kendiliğinden değiştirmez.

### 1. Kaynak sınıfı (#6)

Her ses örneği, `provenance` alanından okunan tek bir sınıfa düşer (`Store.sample_class`):

| Sınıf | Provenance | Ne demek |
| --- | --- | --- |
| `human_local` | `manual`, `<mid>:<sid>`, `<mid>:speaker:<s>` | **bu** kullanıcı bir ad yazdı |
| `auto_local` | `auto:<mid>:<cluster>` | uygulamanın kendi emin tahmini, profile geri beslendi |
| `team` | `team:<host>:<hash>` | bir takım arkadaşının Mac'i böyle adlandırdı; burada kimse dinlemedi |

`store._scores` her aday için `by_class` (sınıf başına örnek sayısı), `best_class` (en yakın tek örneğin
sınıfı) ve `team_only` (hiç `human_local` örneği yok) döndürür.

**Yalnız ekipten bilinen bir kişi, normal eşiği geçse bile ad olarak yazılmaz — öneri olur.** Ad yazılması
için skorun `eşik + TEAM_EXTRA_MARGIN` (0,03) barajını da geçmesi gerekir (`Store.identify`). Aynı kişinin
burada tek bir yerel örneği olduğu anda bu ek baraj kalkar: baraj kişiye değil, **kimsenin denetlemediği
kanıta** konur. Bir Mac'in hatası böylece bütün ekibin etiketi hâline gelmez.

### 2. Ekibin gerçek katkısı (#6)

"8 profil indi" bir indirme sayısıdır, bir fayda değil. `store.team_profile_effect` **karşı olgusal** ölçer:
aynı zaman sıralı replay iki kez koşar — bir kez bütün örneklerle, bir kez `team:` örnekleri çıkarılarak.

- **+N doğru:** yalnız ekibin örnekleriyle doğru adlandırılan küme sayısı,
- **−M yanlış:** yalnız ekibin örnekleri yüzünden yanlış adlandırılan küme sayısı.

Kurulum kartının ekip satırında ve `learning.summary`'nin `team.profile_effect` alanında, sıfır değilse:
`ekipten gelen profiller: +2 doğru / −1 yanlış`. Ekip örneği olmayan bir veritabanı tek bir `COUNT` ile
cevap verir, replay koşmaz.

### 3. Eşik önerisi (#5)

`quality.calibrate` küçük ve **sabit** bir ızgarayı puanlar: eşik ∈ {0,85 · 0,87 · 0,89}, marj ∈
{0,04 · 0,05 · 0,06}. Üç kural ölçümü kullanılabilir kılar:

1. **Zaman sıralı.** Tek hakem `quality.replay_timeline`: bir toplantı yalnız kendisinden **önce** var olan
   kanıtı kullanabilir. Leave-one-out replay gelecekteki toplantıların örneğini ödünç alabildiği için eşik
   ayarına girmez.
2. **Yalnız insan doğrulamalı küme.** Bir küme ancak bir kişi onu **adlandırmışsa** sayılır
   (`quality._verified_clusters`). Dokunulmamış otomatik ad kendi kendini doğrulamaz.
3. **Daha kötü olmasın.** Amaç doğru otomatik ad sayısını artırmak; kısıt, yanlış otomatik ad sayısının
   bugünkü ayarın ürettiğini **aşmaması** ve **bilinmeyen kişinin adlandırılmaması**. İki ad kazanıp bir ad
   uyduran aday kabul edilmez.

Çıktı `<data_dir>/quality/calibration.json`: her aday için `correct` / `wrong` / `unknown_named` /
`abstained_ok` / `abstained_wrong` / `n`, ve bir `recommendation`. **Üretim eşiği değişmez.**

Kurulum kartının kalite satırı, `n ≥ 20` doğrulanmış küme varsa öneriyi gösterir:

```
kalibrasyon önerisi: eşik 0.85 (+2 doğru, 0 yanlış, n=24)
```

Altındaysa tek satır: `kalibrasyon: veri yetersiz (n=7)`. Ölçüm saatlik boştaki bakım geçişinde, günde en
fazla bir kez yapılır (`quality.calibration_refresh`); kart ve nabız yalnız dosyayı **okur**.

Uygulamak ayrı ve bilinçli bir adımdır:

```bash
meeting_os quality calibrate            # ölçer, yazar, hiçbir şeyi değiştirmez
meeting_os quality calibrate --apply    # öneriyi settings.json'a yazar
```

`--apply`, `identity_threshold` ve `identity_margin` alanlarını ayarlara yazar; `cloud_finalize.identity_bars`
bunları okur ve **doğrulanmış aralık dışındaki** bir değeri yok sayıp sabiti kullanır (eşik 0,80–0,95, marj
0,02–0,15). Veri yetersizse `--apply` reddeder.

### Bir yanlış ad, indirimi durdurur

Kişisel eşik (`Store.personal_bar`) hâlâ her onaylanmış öneri için 0,01 iner ve her çürütülmüş otomatik ad
için 0,02 çıkar. Değişen şu: **`wrong` bir kez oluştuğunda onaylar artık tabanın altına indirmez.** Üç onay
bir hatayı ödeyip barajı yeniden küresel eşiğin altına çekebiliyordu; onaylar profilin kolay konuşmayla
eşleştiğini söyler, hata ise **başkasının sesiyle de** eşleştiğini söyler ve baraj hakkındaki tek argüman
ikincisidir.

## Deney ve geri dönüş (1.2.85)

Kaynağı: Codex #11. Bu sürüme kadar **ölçülen** her iyileşme bir kartta cümle olarak kalıyordu: kalibrasyon
öneri üretip duruyordu, Kontrol kuyruğu yazıldığı gibi sıralanıyordu, bir ayarın ne zaman ve hangi kanıtla
değiştiğini hiçbir yer tutmuyordu. Geri alınamayan bir değişiklik ise kendiliğinden yapılmaması gereken
değişikliktir.

### Politika sürümleri — `quality/policy.json`

Üç alan, bir sürüm numarası ve öncekilerin tamamı:

| Alan | Ne söyler |
| --- | --- |
| `identity` | ses eşleştirme barajları (`threshold`, `margin`) — sürüm bunları **sabitlemiyorsa** `null` |
| `review_order` | `severity` (bugünkü) ya da `recency`: haftalık Kontrol borcu önce neye göre sıralanır |
| `hint_ranking` | `ranked` (bugünkü) ya da `legacy`: 900 karakterlik STT ipucu nasıl doldurulur |
| `version` · `since` · `evidence` | kaçıncı sürüm, ne zaman yürürlüğe girdi, hangi ölçüme dayanıyor (yalnız sayılar) |
| `previous` | önceki sürümlerin yığını (en fazla 20); `rollback` bunun tepesini alır |

```python
policy.current(data_dir)     # yürürlükteki sürüm (dosya yoksa bugünkü sabitler, source='default')
policy.promote(data_dir, {'identity_threshold': 0.85}, evidence, store=store)
policy.rollback(data_dir, store=store)    # bir adım geri
policy.review_order(data_dir); policy.hint_ranking(data_dir)
```

`promote` aralık dışında bir değeri **kırpmaz, reddeder** (`ValueError`): eşik 0,80–0,95, marj 0,02–0,15.
Kuyruk sıralamasıyla ilgili bir yükseltme barajlar hakkında hiçbir şey söylemediği için onları
sabitlemez — kullanıcının uyguladığı kalibrasyon çalışmaya devam eder.

### Öncelik sırası — bir tane, ve yalnız bir tane

`cloud_finalize.identity_bars` barajları şu sırayla okur:

1. **`quality/policy.json`** — ölçülmüş, tarihli, geri alınabilir bir yükseltme. Yalnız `policy.promote` yazar.
2. **`settings.json`** — `identity_threshold` / `identity_margin`, yani `quality calibrate --apply`.
3. **Sabitler** (`IDENTITY_THRESHOLD` 0,87 · `IDENTITY_MARGIN` 0,05).

Her adımda yalnız **doğrulanmış aralıktaki** bir değer okunur; bozuk dosya, elle yazılmış bir sayı ya da
aralık dışı bir değer sessizce bir alt adıma düşer. `quality calibrate --apply` artık ayarlarla birlikte bir
politika sürümü de yükseltir, böylece 1. ve 2. adım kullanıcının bilerek uyguladığı bir baraj konusunda
birbiriyle çelişemez.

### Sessiz ve ucuz deneyler — `quality/experiments.jsonl`

`storage_housekeeping` (saatlik, boşta) `experiments.run_due` çağırır. Kurallar kodda, çağıranın alışkanlığında
değil:

- **Buluta hiçbir çağrı yok.** Üç aday da diskteki satırlar üzerinde aritmetiktir. `quality compare` ayrı bir
  araçtır ve buradan erişilemez.
- **Kayıt ya da iş sürerken asla.** Canlı kayıt nabzı, `processing` durumundaki toplantı, `MEETING_OS_LOW_PRIORITY`
  ya da çağıranın verdiği bayrak — dördü de geçişi durdurur.
- **Cihaz başına günde en fazla bir deney.** Sonuç dosyası defterdir: günü zaten yazılmış bir geçiş hiçbir şey yapmaz.
- **Sonuçlar üretim verisi değildir.** `samples`, `rejections`, `taught_words`, `tasks` hiç yazılmaz; bu modülün
  o tablolara giden bir yolu yoktur. Dosyada toplantı kimliği, kelime ya da kişi adı bulunmaz.
- **Sessizlik onay değildir.** Kullanıcının cevaplamadığı bir Kontrol maddesi havuza hiç girmez; `geçildi`
  yalnız bir sıra tutar, asla onay sayılmaz.

| Aday | Nasıl ölçülür | Önceden ilan edilmiş hedef |
| --- | --- | --- |
| `identity_bars` | `quality.calibrate` (zaman sıralı, yalnız insan doğrulamalı kümeler) | doğru ↑, yanlış ↑ değil, n ≥ 20, aralık içinde |
| `review_order` | son 400 çözülmüş Kontrol maddesi, iki sıralamada da konumlandırılır | `düzeltildi` maddelerinin ortanca konumu ≥1 basamak öne gelsin, n ≥ 20 |
| `hint_ranking` | `quality.replay_rules` (1.2.84 dalında) | ham STT'de tekrar eden hata ↓, yeni hata ↑ değil, n ≥ 20 |

Ölçüm yapılamıyorsa sonuç **“ölçülemedi”** olur — “ölçtük, iyi değil” ile aynı şey değildir.

### Otomatik uygulama varsayılan olarak kapalı

Ayarlar → Sistem → Gelişmiş: **“Ölçülmüş iyileştirmeler kendiliğinden uygulansın (yalnız yerel ayarlar; kayıt
sırasında asla; her değişiklik geri alınabilir)”** — `auto_promote_policies`, varsayılan `False`.

Kapalıyken geçiş yine ölçer ve bulduğunu yazar, ama hiçbir şeyi değiştirmez: Kurulum durumu kartının kalite
satırı öneriyi gösterir ve sonuna **“· otomatik uygulama kapalı”** ekler. Açıkken hedefi tutan ve aralıkta
kalan aday `policy.promote` ile yükselir; bu da bir `policy.rollback` uzaklıktadır.

### Geri alma

```bash
meeting_os quality policy              # yürürlükteki sürüm, kanıtı ve bütün geçmiş sürümler
meeting_os quality policy --rollback   # bir adım geri
meeting_os quality experiments         # son deney sonuçları
```

Geri alma **yeni bir sürüm** üretir: değerler geriye gider, tarih ileriye. “12'sinde hangi baraj yürürlükteydi?”
sorusu bir geri almadan sonra da cevaplanabilir kalır. İlk yükseltme de geri alınabilir — yığının dibinde
sürüm 0, yani uygulamanın geldiği sabitler durur. Her iki yön de `learning_events` içine bir satır yazar
(`policy_promote` / `policy_rollback`, `source='auto'`).

## Saklama

- **Olay kaydı: 90 gün / 20 MB.** Saatlik bakım geçişi (`storage_housekeeping`) önce süresi dolanları, sonra
  bütçe aşılıyorsa en eskileri siler (`learning.prune`).
- **Deney sonuçları: 7 gün / 20 MB** (`experiments.prune`, her geçişte). Bu, uygulamanın tuttuğu en kısa
  ömürlü şeydir: zaten verilmiş ya da verilmemiş bir kararın kanıtıdır ve bir hafta okumaya yeter.
- Kaynak toplantı silindiğinde ona ait metinli öğrenme örneği de gider (mevcut `text_retention` yolu);
  öğrenilmiş kelime ve profil ayrı kalır — bu mevcut ürün sözleşmesidir.
- Olay kaydı ayrı bir veri platformuna dönüşmez: kullanıcı işleminde yalnız küçük yerel yazım, model çağrısı
  yok, ağ beklemesi yok, geçmiş taraması yok.

## Bunu okumak

```bash
meeting_os quality report      # kimlik karnesi: verified / falsified / unreviewed
meeting_os quality replay --timeline   # zaman sıralı kimlik değerlendirmesi
meeting_os quality calibrate   # eşik ızgarası ve öneri (hiçbir şeyi değiştirmez)
meeting_os quality policy      # yürürlükteki politika sürümü ve geçmişi
meeting_os quality experiments # son deney sonuçları (sayılar ve kararlar)
meeting_os reports heartbeat   # learning bloğu dahil nabız
meeting_os quality report     # kimlik karnesi: verified / falsified / unreviewed
meeting_os quality replay --text   # metin + kural replay'i (matched / mismatched / retired)
meeting_os glossary hint      # bugünkü sıralı ipucu: ne girdi, kaç terim giremedi
meeting_os reports heartbeat  # learning bloğu dahil nabız
```

Python'dan: `learning.events(store, since=...)`, `learning.summary(store, days=7)`,
`learning.team_stopwatch(store)`, `store.team_profile_effect(store)`, `quality.calibrate(store, data_dir)`,
`policy.current(data_dir)`, `experiments.records(data_dir)`.
