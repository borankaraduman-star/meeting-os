İki dosyayı (`pipeline.py`, `desktop.py`) inceleyip kalan somut, yüksek öncelikli sorunları özetliyorum.

## 1. `pipeline.py` — Gerçek embedding ile çöküş (kritik, doğruluk hatası)

```python
vector = None if ambiguous else self.diarizer.embedder.embed(...)
identity = self.store.identify(vector, ...) if vector else {'name':None,...}
```

`embed()` bir numpy dizisi döndürüyorsa (embedding vektörü — birden fazla elemanlı array), `if vector` ifadesi `ValueError: truth value of an array with more than one element is ambiguous` fırlatır. `None` kontrolü doğru yapılmış (`None if ambiguous else ...`), ama sonraki truthiness testi yanlış — `vector is None` olması gerekirken `vector` dizisinin kendisi test ediliyor. Bu, ambiguous olmayan **her** segmentte (yani normal, kimliklendirilebilir konuşma anında) çökme demektir. 29 testin geçmiş olması muhtemelen mock embedder'ların skaler/boyut-1 döndürmesinden kaynaklanıyor; gerçek MLX/sherpa embedder'la production'da patlar.

**Fix:**
```python
identity = self.store.identify(vector, self.diarizer.embedder.model_id, self.identity_threshold, self.identity_margin) if vector is not None else {'name':None,'similarity':None,'margin':None}
```

## 2. `desktop.py` — Kalite/durum kısıtları yalnızca UI'de, backend'de yok (yüksek öncelik, veri bütünlüğü)

Rapor edilen tasarım gereksinimleri şunlar: "enrollment provisional/ambiguous/short-context'i engeller" ve "label'lar yalnızca complete meeting'lerde düzenlenebilir." Ancak `dispatch()` içinde bu kurallar **hiç doğrulanmıyor**:

- `enroll`: yalnızca `confirmed_clean is True` bayrağını kontrol ediyor; segmentin `provisional` / `speaker_ambiguous` / `short_context_diarization` flag'lerini hiç sorgulamıyor. UI bug'ı, race condition veya ileride yapılacak bir UI değişikliği bu kapıyı bypass edebilir. Enrollment atomik ve kalıcı olduğundan (kimlik veritabanına yazılıyor, gelecekteki tüm toplantıları etkiliyor), sunucu tarafında hiçbir güvence olmaması blast radius'u geniş bir açık bırakıyor.
- `label` / `edit_text`: hedef toplantının `complete` durumda olup olmadığını hiç kontrol etmiyor. Aktif kayıt sırasında (provisional/incomplete) bir relabel isteği gelirse, canlı identity eşleştirmesini veya audit trail'i bozabilir.

Bu, "atomic transaction + idempotent" gibi doğru yapılmış alt katman garantilerinin üstüne, üst katmanda (giriş doğrulama sınırı) eksik bir kontrol eklenmesi gerektiği anlamına geliyor — tam olarak sistem sınırında yapılması gereken validasyon türü.

**Fix (store'un gerçek accessor'larına göre uyarlanmalı):**
```python
if action=='enroll':
    if request.get('confirmed_clean') is not True: raise ValueError('...')
    segment = store.get_segment(request['meeting'], int(request['segment']))
    if segment['flags'] & {'provisional','speaker_ambiguous','short_context_diarization'}:
        raise ValueError('Segment does not meet clean-sample criteria')
    store.enroll_segment(...)

if action in ('label','edit_text'):
    if store.meeting_status(request['meeting']) != 'complete':
        raise ValueError('Editable only on complete meetings')
    ...
```

## 3. `live.py` — "provisional" durumdan çıkış yolu görünmüyor (doğrulama gerekli, muhtemelen kapsam dışı)

Kullanıcı Ctrl+C ile temiz şekilde durdurup (`captured[0]>0`, `code==0`, hata yok) çıktığında, meeting durumu yalnızca `'provisional'` olarak ayarlanıyor; bu dosyada `'complete'`'e geçiş yok. Eğer finalize adımı başka bir modülde ise sorun yok, ama değilse toplantılar sonsuza dek "provisional" kalır ve #2'deki label/edit kısıtı yüzünden asla düzenlenemez hale gelir. Bu dosyada finalize çağrısı görülmediğinden doğrulanması gerekiyor; kod olarak somut bir hata iddia etmiyorum, sadece #2 ile birleştiğinde ortaya çıkabilecek bir kilitlenme riskini işaretliyorum.

**Öncelik sırası:** #1 (kesin çökme, MLX/gerçek embedder ile üretimde tetiklenir) → #2 (sessiz veri bütünlüğü açığı) → #3 (doğrulama gerektiren olası kilitlenme).
