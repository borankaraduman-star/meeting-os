# 3–5 gerçek toplantı ile değerlendirme

İzinli yerel kayıtlar kullanın. Enrollment için ayrı bir önceki oturum seçin.
Değerlendirme toplantılarının seslerini veya embedding'lerini enrollment'a
koymayın. Harness aynı `session` ID'sinin iki tarafta bulunmasını reddeder;
ID'leri farklı vererek aynı sesin kullanılmasını otomatik algılayamaz.

1. Toplantı 1: Türkçe + İngilizce code-switch, PM jargon, kişi/proje isimleri.
2. Toplantı 2: aynı kişiler, farklı mikrofon/uzak toplantı koşulu, söz kesme.
3. Toplantı 3: daha önce enroll edilmemiş kişi, gürültü, kısa cevaplar.
4. Tercihen toplantı 4: en az 30 dakika; başlangıç/son ses hizası ve kayıp ölçümü.
5. Tercihen toplantı 5: başka gün, benzer sesli iki kişi, overlap ve sessizlik.

Her toplantıdan 2–5 dakikalık zor ve sıradan bölümler alın. Türkçe bilen bir
kişi sözcükleri ve zamanı referanslasın. Özellikle "değil", tarihler, yüzdeler,
isimler ve kısaltmaları kayıttan kontrol edin. Referans metni ASR çıktısından
kopyalamak hataları görünmez yapabilir. Referans `turns` overlap içeriyorsa iki
konuşmacıyı da yazın. `identity_turns` gerçek isimleri içerir; diarization `turns`
ise anonim speaker ID kullanabilir. İsimlerin kendisi local benchmark verisidir.

`benchmarks/reference.example.json` ve `manifest.example.json` biçimlerini kullanın.
Manifest yolları manifest klasörüne göre çözülür. `configs[].options` CLI argüman
listesidir, shell çalıştırılmaz. Config adında engine/model/quantization ve
embedding/diarization varyantını belirtin. Hız/kalite karşılaştırması için aynı
segment ve sözlüğü kullanın; auto language ve farklı sözlüğü ayrı config yapın.

## Ölçülenler

- Normalized WER: Türkçe I/İ dönüşümü, Unicode NFC, noktalama temizliği.
  Raw WER ve CER ayrıca saklanır. Boş referansa konuşma üretilirse WER null,
  insertions ve silence_hallucination_words pozitif olur; sıfır başarı sayılmaz.
- İsim/jargon entity recall: referansta gerçekten bulunan sözlük ifadelerinin
  hipotezde bütün kelime olarak bulunması. Tekil ifade bazında, occurrence bazında değil.
- DER: optimal speaker mapping, 0 saniye collar, overlap dahil; miss, false alarm
  ve confusion saniyeleri ayrı. Baseline ayrımı overlap kurtaramaz.
- Identity: doğru isim, yanlış isim, false reject ve bilinmeyen kişiye false
  accept. ASR'nin kapsadığı speech üzerinde ölçülür; missing speech DER'dedir.
  Enrollment yoksa bilinen kişi metrikleri null; başarı olarak yorumlanmaz.
- RTF: model yükleme + VAD + ASR + diarization + DB dahil duvar süresi / ses süresi.
  Aynı modelde tekrar koşu ile warm-cache etkisini ayrı raporlayın.
- Bellek: parent peak RSS + en büyük child peak RSS toplam üst sınırı.
  Eşzamanlı tepe veya tam Metal GPU allocation ölçümü değildir. Activity Monitor
  ve uzun koşuda memory pressure/thermal durumunu ayrıca not edin.
- Canlı: her segmentte `live_lag_seconds`, CLI'de backlog. Capture manifestindeki
  `gap` olayları aynı kaynağın beklenen/gerçek zamanını verir. Kanallar arası
  akustik referans/echo ölçümü manuel uzun kayıt testinde yapılmalıdır.

## Kimlik enrollment verisi

Manifest `enrollment` listesi her kayıt için `name`, `model`, `vector`,
`duration`, `session` alır. Vektör ve model ID'si yalnızca ayrı enrollment
oturumundaki `show --json` çıktısından, dinlenmiş temiz segmentten alınır.
`duration >=3` gerekir. Her model ailesi için ayrı vector/model girin.
Aynı sesle hem enroll hem test yapmayın. Eşik seçiminde meeting-01/02 gibi
geliştirme oturumları; final raporda ayrılmış meeting-03/04/05 kullanın.

Başlangıç kabul hedefleri (ölçülmüş sonuç değildir): sessizlikte 0 kelime;
identity false accept <%1; isim/jargon recall >%95; WER <%10; final DER <%15;
canlı sürdürülebilir RTF <1. Küçük veri seti istatistiksel garanti vermez.
Eşikler tutmuyorsa unknown tercih edin; otomatik isimlendirmeyi daha yüksek
eşikle sınırlandırın. V0.1'i günlük kullanıma hazır ilan etmeden uzun kayıt,
Bluetooth değişimi, ekran kilidi, uyku/uyanma ve disk dolmasını manuel deneyin.

## Özet ve görevler için V1 ölçümü

Her toplantıdaki kabul edilmiş görevleri önce kayıttan bağımsız olarak
referanslayın. Modelin kaçırdıklarını da ekleyin. Ardından model çıktısı ile
anlamca eşleşen görevleri insan kontrolüyle eşleyin;
`benchmarks/analysis-reference.example.json` biçimi bunu açıkça kaydeder.
Tahmin numaraları sıfırdan başlar. Desteksiz özet maddelerini de işaretleyin.

```sh
.venv/bin/python -m meeting_os analyze MEETING_ID --output /local/analysis.json
.venv/bin/python scripts/evaluate-analysis.py /local/analysis.json /local/reference.json --output /local/score.json
```

Görev precision/recall/F1, eşleşen görevlerde sahip ve söylenen tarih doğruluğu,
desteksiz özet oranı raporlanır. Aynı referans/tahmin iki kez eşlenemez. Boş
paydalar null'dır, başarı sayılmaz. 3–5 toplantının TP/FP/FN sayıları birleştirilip
micro precision/recall hesaplanabilir; toplantı başına skorları ayrıca saklayın.
Özeti modelin kendisine puanlatmak yerine kaydı bilen bir insan değerlendirsin.
İsim düzeltmeden önce/sonra sonuçları ayrı koşu olarak kaydedin.

## Bulut analiz kıyası

`scripts/benchmark-analysis-cloud.py`, `scripts/benchmark-analysis.py` ile aynı
kurgu fixture'ları ve aynı `check_fixture_analysis` kapılarını kullanır; tek
fark, modelin yerel model yerine OpenRouter adaptörü olmasıdır. Gerçek toplantı
verisi kullanılmaz, kullanılamaz: girdi yalnızca `tests/fixtures/analysis/*.json`.
Her istek ücretlidir, bu yüzden onay açıktır ve koşunun sert bir çağrı bütçesi vardır.

```sh
.venv/bin/python scripts/benchmark-analysis-cloud.py \
  --output /local/analysis-cloud.json --model openai/gpt-4.1-mini \
  --allow-upload --max-calls 40
```

Kapıların dışında şunlar mekanik olarak ölçülür: modelin alıntılarının kaçı
harfi harfine doğruydu (`verbatim`), kaçı `locate_quote` ile gerçek metne
oturtulabildi (`verified`), actions altına sızan yasak terimler, eksik referans
görevler ve eksiklik sebebi, parça birleştirmesinden sağ çıkan tekrarlar,
`required_decision_terms` ile karşılanmayan kararlar ve Türkçe çıktıdaki
İngilizce bölüm adları/etiketleri.

10 Eylül 2026, `openai/gpt-4.1-mini`, beş kurgu fixture. Önce = 39b8095'teki
`intelligence.py`, sonra = bu daldaki hâli; fixture'lar iki koşuda da aynıdır.

| case | checks | verified | verbatim | actions | özet maddesi | eksik görev | eksik karar |
|---|---|---|---|---|---|---|---|
| cancel | 5/5 → 5/5 | 1.00 → 1.00 | 1.00 → 1.00 | 0 → 0 | 3 → 3 | 0 → 0 | 0 → 0 |
| handover (2 parça) | 2/5 → 5/5 | 0.89 → 1.00 | 0.83 → 0.96 | 5 → 4 | 3 → 5 | 0 → 0 | 1 → 0 |
| injection | 5/5 → 5/5 | 1.00 → 1.00 | 1.00 → 1.00 | 1 → 1 | 2 → 2 | 0 → 0 | 0 → 0 |
| reversal | 2/5 → 5/5 | 1.00 → 1.00 | 1.00 → 1.00 | 2 → 3 | 5 → 5 | 1 → 0 | 0 → 0 |
| sprint | 5/5 → 5/5 | 1.00 → 1.00 | 1.00 → 1.00 | 3 → 3 | 5 → 4 | 0 → 0 | 0 → 0 |

Koşu başına 11 bulut çağrısı, ≈ $0.011 (önce) / ≈ $0.015 (sonra).

Ölçülen kusurlar ve karşılıkları: uzun toplantıda aynı görev iki parçada iki kez
raporlanıyordu; ikinci parçada alınan karar iptali hiç görünmüyordu, çünkü model
alıntıyı "…" ile veya araya giren cümleyi atlayarak iki parçadan birleştiriyor ve
doğrulama bütün maddeyi düşürüyordu; başkasının ağzından aktarılan taahhüt yanlış
kişiye yazılıyordu; kendi alıntısının içinde duran tarih kayboluyordu; uzun
toplantının özeti 3 maddeye çöküyordu.

Bu tablo sözlüksel bir gerilemedir, anlam doğruluğu değildir. Beş kurgu fixture
istatistiksel garanti vermez ve gerçek toplantı performansını temsil etmez;
gerçek ölçüm için yukarıdaki insan değerlendirmesi şarttır. `handover` bir koşuda
ekibe yapılan genel bir ricayı görev sanmıştı: aynı fixture'ı en az iki kez koşup
kararsız maddeleri not edin, tek koşuyu sonuç saymayın.
