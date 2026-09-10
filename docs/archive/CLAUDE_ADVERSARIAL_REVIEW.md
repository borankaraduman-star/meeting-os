Aşağıda dosya/fonksiyon bazında somut bulgular ve en küçük düzeltme önerileri var. Övgü veya genel gözlem yok.

**1. `speakers.py — Diarizer.turns` (cluster mode): son pencere her zaman "unknown" olarak damgalanıyor**
Her konuşma bölgesinin son 2.5s penceresi genellikle 1 saniyeden kısa kalıyor. `Embedder.embed()` `len(audio) < RATE` ise `None` döndürüyor, `Clusterer.assign(None)` de doğrudan `'unknown'` döndürüyor — kümeleme indeksiyle ilişkisiz. Sonuç: hemen her konuşma bölgesinin sonunda gerçek konuşmacı yerine sahte bir `unknown` turn oluşuyor, bu da `speaker_at()`'te gereksiz `speaker_ambiguous` bayrağını ve turn parçalanmasını tetikliyor.
*Düzeltme:* `b-a < RATE` olan son parçayı ayrı turn açmak yerine önceki pencereyle birleştir (döngüden önce range sınırını `end` yerine `end - int(RATE)` gibi ayarla veya kalan kuyruğu bir önceki `b`'ye ekle).

**2. `pipeline.py — Pipeline.process`: identity sözlüğü şekli tutarsız**
`vector` yoksa (kısa ses ya da `ambiguous=True`) `identity = {'name': None}` atanıyor; ama `store.identify()` normal yolda her zaman `{'name','similarity','margin'}` üçlüsünü döndürüyor. "Ölçemedik" ile "ölçtük, eşleşme yok" durumları aynı görünüyor ve `metrics['identity']['similarity']` okuyan herhangi bir tüketici (rapor/export) KeyError alır.
*Düzeltme:* Eksik durumda da `{'name':None,'similarity':None,'margin':None}` döndür.

**3. `pipeline.py — Pipeline.process`: eksik ASR metrikleri sessizce "güvenilir" sayılıyor**
`metrics.get('avg_logprob',0)` ve `metrics.get('no_speech_prob',0)` varsayılanları sırasıyla eşiklerin (`-0.8`, `0.5`) güvenli tarafında. ASR backend bu alanları döndürmezse ve `confidence_unavailable` bayrağını da set etmezse, segment hiçbir uyarı bayrağı olmadan yüksek güvenle sunulur.
*Düzeltme:* Varsayılanı `None` yap, `None` ise doğrudan `confidence_unavailable` ekle (backend garantisine güvenme).

**4. `capture.py — record()`: `process.wait(timeout=15)` korumasız, meeting kaydı sonsuza dek "processing" kalabilir**
Yakalama süreci kapanmayı reddederse `subprocess.TimeoutExpired` yakalanmadan yükselir; bu durumda `store.status(mid, ...)` hiç çağrılmaz ve `finally` bloğu sadece process/thread temizler, DB durumunu güncellemez. Kullanıcıya kalıcı olarak "processing" durumunda, hatasız görünen bir toplantı kalır.
*Düzeltme:* `try: code=process.wait(timeout=15) except subprocess.TimeoutExpired: process.kill(); code=process.wait(); errors.append('capture did not exit')` şeklinde sar, ardından mevcut `store.status` çağrısını çalıştır.

**5. `capture.py — record()`: `create_meeting` çağrısı `Popen`'dan önce, hata durumunda yetim kayıt**
Binary bulunamazsa/başlatılamazsa `subprocess.Popen` istisna fırlatır; bu satır `try/finally` bloğunun dışında olduğu için `store.status`/temizlik hiç çalışmaz, `mid` "processing" durumunda kalıcı yetim kayıt olarak DB'de kalır.
*Düzeltme:* `Popen` çağrısını da `try` bloğuna al veya `create_meeting`'i `Popen` başarılı döndükten sonra çağır.

**6. `store.py — Store.identify()`: ağırlıksız ortalama, provenance/sample sayısı kontrolsüz**
Bir isme kayıtlı tüm örnekler (süre, sayı, provenance fark etmeksizin) eşit ağırlıkla ortalanıyor; tek 3 saniyelik gürültülü örnek, çok sayıda temiz örneği dengeleyebilir. Ayrıca farklı `provenance` (ör. `manual` vs. bir test oturumu etiketi) aynı isimde sessizce birleşiyor — enrollment bütünlüğü için minimum örnek sayısı/ süre ağırlıklandırması yok.
*Düzeltme:* `profiles()` sorgusundakine benzer şekilde `identify()`'de de minimum toplam süre/örnek sayısı eşiği uygula, ya da ortalamayı süreyle ağırlıklandır.

**7. `benchmark.py — benchmark()` / REPORT.md üretimi: eksik `peak_rss_bytes` sessizce "0.000 GB" olarak raporlanıyor**
`r.get("peak_rss_bytes",0)/1e9`, alan `result.json`'da yoksa (ör. eski/parçalı çıktı) gerçek bir ölçüm gibi görünen "0.000" GB üretir; oysa "—" ile "ölçülemedi" ayrımı yapılmalı.
*Düzeltme:* `r.get("peak_rss_bytes")` (varsayılansız) kontrolü yap, `None` ise tabloda `"—"` bas.

**8. `MeetingCapture.swift — run()`: Ekran Kaydı izni için erken/açıklayıcı kontrol yok**
Mikrofon izni açık ve anlaşılır bir hata mesajıyla (`AVCaptureDevice.requestAccess`) kontrol ediliyor, ama `SCShareableContent.excludingDesktopWindows` çağrısından önce eşdeğer bir Ekran Kaydı izin kontrolü/istemi yok. İzin verilmemişse sistem, teşhis edilmesi zor genel bir hata fırlatır — açık onay/aydınlatılmış rıza gerektiren bir üründe ilk çalıştırma teşhisini zayıflatıyor.
*Düzeltme:* `SCShareableContent` çağrısını yakala, hata durumunda mikrofon dalındakine benzer açık bir `NSLocalizedDescriptionKey` mesajıyla (System Settings > Privacy & Security > Screen Recording) yeniden fırlat.
