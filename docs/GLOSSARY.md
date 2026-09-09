# Proje sözlüğü ve Slack agent istemi

Meeting OS `glossary.jsonl` dosyasını üç yerde kullanır: bulut STT yazım ipucu (yalnız prompt kabul eden modeller; etkisi sağlayıcıya bağlı, OpenRouter üzerinden 9 Eylül 2026 A/B ölçümünde fark görülmedi), transkript sonrası düzeltme önerileri (yerel benzerlik ≥0.84, isteğe bağlı gpt-4.1-mini doğrulaması, Kontrol sekmesinde tek tıkla uygulama, özgün metin korunur) ve analiz bağlamı (kısaltma açılımı).

## Slack agent’a verilecek istem

```
Görev: Slack mesajlarımdan (tüm kanallar ve DM'ler, son 6 ay) işimle ilgili
özel terim, kısaltma, ürün/proje/ekip/kişi adı ve jargon sözlüğü çıkar.
Amaç: Türkçe toplantı ses kayıtlarını yazıya dökerken bu kelimelerin doğru
yazılması. Genel Türkçe ve genel İngilizce kelimeleri alma; yalnız dışarıdan
birinin bilemeyeceği ya da yanlış duyulabilecek terimleri al.

Her terim için tek satır JSON yaz (JSON Lines), başka açıklama ekleme:
{"term":"PMD","expansion":"Product Management Daily","category":"kısaltma",
 "aliases":["pi em di","PM daily"],"mishearings":["pemede","PMB"],
 "context":"ürün ekibinin günlük toplantısı","example":"PMD'de rollout'u konuştuk",
 "confidence":"yüksek","source_count":14}

Kurallar:
- category: kısaltma | ürün | proje | ekip | kişi | teknik terim | müşteri | jargon
- aliases: sesli konuşmada söylendiği biçimler (harf harf okunuş, Türkçe telaffuz).
- mishearings: bir konuşma tanıma modelinin bunu yanlış yazabileceği olası biçimler.
- expansion bilinmiyorsa null yaz, uydurma.
- Kişi adlarında yalnız ad ve soyadı; unvan, e-posta, telefon ekleme.
- source_count mesajlarda kaç kez geçtiği; 2'nin altındakileri alma.
- En sık geçen 300 terimle sınırla, source_count'a göre sırala.
- Terim büyük/küçük harf ve Türkçe karakter olarak Slack'te yazıldığı kanonik biçimde olsun.
```

Çıktıyı `glossary.jsonl` olarak kaydedip uygulamada **Sözlük ve ses profilleri → glossary.jsonl içe aktar…** ile yükleyin. Uygulama en fazla 500 terim tutar; `aliases` ve `mishearings` 12’şer öğeyle sınırlıdır.
