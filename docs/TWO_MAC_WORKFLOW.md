# İki Mac akışı: kullanım Mac’i ↔ geliştirme Mac’i

## Kullanım Mac’inde (günlük toplantılar)
- Uygulama açılışta ve her 6 saatte bir `git fetch` ile GitHub `v0.1` dalını kontrol eder. Yeni commit varsa kenar çubuğunda “Yeni sürüm hazır · N değişiklik” kartı ve **Güncelle ve yeniden başlat** düğmesi çıkar.
- Ayarlar → Güncelleme ve raporlar → “açılışta kendiliğinden güncelle” açılırsa kayıt/iş yokken açılışta otomatik güncellenir.
- Güncelleme `scripts/update.sh` ile uygulamanın dışında koşar: uygulama kapanır → `git merge --ff-only origin/v0.1` → gerekirse pip / kayıt yardımcısı → `build-desktop.sh` (sabitlenmiş imza kimliği, izinler korunur) → uygulama yeniden açılır. Sonuç `~/Library/Application Support/MeetingOS/update-status.json` ve `update.log`; bir sonraki açılışta “Güncelleme tamam · a → b” görünür. Yerel değişiklik varsa güncelleme yapılmaz.
- Her transkript ve analiz sonunda toplantı raporu `iCloud Drive/MeetingOS-Reports/<mac-adı>/<tarih>_<toplantı>.json` dosyasına yazılır (Ayarlar’dan kapatılabilir). İçerik: süre, parça/ücret, yankı, konuşmacı küme/benzerlik/isim, kontrol kuyruğu sayıları, analiz sayıları, kimlik karnesi, son hata satırları (yollar maskelenir) ve `capture` bloğu (kaynak başına parça dosyası sayısı, süreden beklenen sayı, günlükteki `gap`/`error` olayları ve toplam boşluk saniyesi, birleştirilmiş `*-full.wav` boyutları). Transkript metni yalnız “metni de ekle” açıksa girer.
- Toplantıdan bağımsız nabız: `.venv/bin/python -m meeting_os reports heartbeat` (ya da köprüde `{"action":"heartbeat"}`) aynı klasöre `<mac-adı>/heartbeat.json` yazar ve her seferinde üzerine yazar. İçerik: yazılma zamanı, sürüm/commit, toplantı sayısı ve durum dağılımı, son tamamlanan toplantı, recordings/imports/sqlite boyutları, boş disk, bellek baskısı, `pmset -g therm` CPU_Speed_Limit, yük ortalaması ve son 5 hata satırı. Rapor paylaşımı kapalıysa yazılmaz.

## Geliştirme Mac’inde (bu Mac)
1. Oturum başında `.venv/bin/python -m meeting_os reports summarize` — önce **uyarı listesi** (stderr: 3 gündür nabız yok, disk 3 GB altı, gece öz-testi başarısız, bulutta anahtar/kredi yüzünden bekleyen toplantı, kayıt sürerken parça gelmiyor, bellek baskısı), sonra bütün Mac’lerin raporları, hata sayıları, isimsiz konuşmacı oranı, maliyet. Her Mac için `heartbeat` satırı: son görülme, boş disk, termal, günlük `probe` özeti (`Öz-test temiz` ya da eksik madde). Nabız saatte bir yazılır; öz-test günde bir kez, kayıt yokken, nabızla birlikte koşar (`probe-last.json` önbelleği).
2. Sorunlu raporu aç (`iCloud Drive/MeetingOS-Reports/<mac>/…json`), nedeni bul, düzelt, test et, commit + `git push origin v0.1`.
3. Kullanım Mac’i bir sonraki açılışta günceller (veya kartta tek tık).

Sürüm etiketi/GitHub Release yalnız kilometre taşlarında (`scripts/package-source.py` + `gh release create`); günlük akış dal üzerinden yürür.


## Kurulum durumu kartı (1.2.11+)

Kullanım Mac’inde bir şey çalışmıyorsa önce Ayarlar (⌘,) → **Kurulum durumu**: izinler, OpenRouter anahtarı, sözlük, sürüm ve teşhis raporu klasörünün yazılabilirliği tek listede; kırmızı maddede “İzin iste” ya da “Ayarları aç” doğrudan ilgili yere götürür. Geliştirme Mac’inde rapor görünmüyorsa kullanım Mac’inde bu karttaki “Teşhis raporları” satırına bakın (kapalı / klasör yok / kaç rapor yazıldı).
