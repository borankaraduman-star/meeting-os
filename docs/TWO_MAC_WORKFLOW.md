# İki Mac akışı: kullanım Mac’i ↔ geliştirme Mac’i

## Kullanım Mac’inde (günlük toplantılar)
- Uygulama açılışta ve her 6 saatte bir `git fetch` ile GitHub `v0.1` dalını kontrol eder. Yeni commit varsa kenar çubuğunda “Yeni sürüm hazır · N değişiklik” kartı ve **Güncelle ve yeniden başlat** düğmesi çıkar.
- Ayarlar → Güncelleme ve raporlar → “açılışta kendiliğinden güncelle” açılırsa kayıt/iş yokken açılışta otomatik güncellenir.
- Güncelleme `scripts/update.sh` ile uygulamanın dışında koşar: uygulama kapanır → `git merge --ff-only origin/v0.1` → gerekirse pip / kayıt yardımcısı → `build-desktop.sh` (sabitlenmiş imza kimliği, izinler korunur) → uygulama yeniden açılır. Sonuç `~/Library/Application Support/MeetingOS/update-status.json` ve `update.log`; bir sonraki açılışta “Güncelleme tamam · a → b” görünür. Yerel değişiklik varsa güncelleme yapılmaz.
- Her transkript ve analiz sonunda toplantı raporu `iCloud Drive/MeetingOS-Reports/<mac-adı>/<tarih>_<toplantı>.json` dosyasına yazılır (Ayarlar’dan kapatılabilir). İçerik: süre, parça/ücret, yankı, konuşmacı küme/benzerlik/isim, kontrol kuyruğu sayıları, analiz sayıları, kimlik karnesi, son hata satırları (yollar maskelenir). Transkript metni yalnız “metni de ekle” açıksa girer.

## Geliştirme Mac’inde (bu Mac)
1. Oturum başında `.venv/bin/python -m meeting_os reports summarize` — bütün Mac’lerin raporları, hata sayıları, isimsiz konuşmacı oranı, maliyet.
2. Sorunlu raporu aç (`iCloud Drive/MeetingOS-Reports/<mac>/…json`), nedeni bul, düzelt, test et, commit + `git push origin v0.1`.
3. Kullanım Mac’i bir sonraki açılışta günceller (veya kartta tek tık).

Sürüm etiketi/GitHub Release yalnız kilometre taşlarında (`scripts/package-source.py` + `gh release create`); günlük akış dal üzerinden yürür.


## Kurulum durumu kartı (1.2.11+)

Kullanım Mac’inde bir şey çalışmıyorsa önce Ayarlar (⌘,) → **Kurulum durumu**: izinler, OpenRouter anahtarı, sözlük, sürüm ve teşhis raporu klasörünün yazılabilirliği tek listede; kırmızı maddede “İzin iste” ya da “Ayarları aç” doğrudan ilgili yere götürür. Geliştirme Mac’inde rapor görünmüyorsa kullanım Mac’inde bu karttaki “Teşhis raporları” satırına bakın (kapalı / klasör yok / kaç rapor yazıldı).
