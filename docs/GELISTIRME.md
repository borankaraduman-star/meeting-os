# İki kişiyle paralel geliştirme

Kurallar `AGENTS.md`'de (Claude Code `CLAUDE.md` üzerinden aynı dosyayı okur; Codex doğrudan okur). Burada akış var.

## Roller
- **Sürüm sahibi (Boran):** Developer ID sertifikası, noter profili, GitHub Releases, sunucu erişimi bu Mac'te.
  Sürümü yalnız o çıkarır: `sh scripts/release.sh <sürüm>`.
- **Geliştirici:** kendi Mac'inde `sh scripts/install.sh` ile git kanalı kurulumu (uygulama kendi sertifikasıyla
  derlenir, kendi verisiyle çalışır). Paket üretemez, `release.sh --app-only` ile yalnız kendi uygulamasını yeniler.

## Akış
1. `git fetch && git switch -c <ad>/<konu> origin/v0.1`
2. Claude Code ya da Codex'e işi ver; `AGENTS.md`'yi otomatik okur. Ajan worktree'de çalışsın, dalına commit atsın.
3. Testler yerelde yeşil (`AGENTS.md` → "Kurulum ve testler"), sonra `git push -u origin <dal>` ve `gh pr create -B v0.1`.
4. CI (`.github/workflows/tests.yml`: Python + Swift, macOS runner) yeşil → karşı taraf gözden geçirir (Claude Code'da
   `/code-review`, Codex'te "review this PR") → `gh pr merge --merge`.
5. Sürüm gerektiğinde: sürüm sahibi `docs/releases/vX.md` yazar, `sh scripts/release.sh X` koşar, `docs/ITERATION_CHECKPOINT.md`
   sonuna kısa not ekler. Ekip Mac'leri paketi uygulama içinden alır; git kanalı Mac'ler `Güncelle` ile.

## Aynı anda aynı dosya
- Sürüm numarası üç dosyada; PR'lar bump yapmaz. Sürüm notu dosyası her sürüm için yenidir, çakışmaz.
- `docs/ITERATION_CHECKPOINT.md` yalnız sona eklenir; çakışırsa iki bloğu da tut.
- `meeting_os/cli.py` alt komut listeleri, `meeting_os/desktop.py` housekeeping dönüşü, `docs/KULLANIM.md`: birleşim (ikisini de tut).
- İş paylaşımı önerisi: biri Swift/UI (`desktop/`), diğeri Python (`meeting_os/`, `server/`); aynı sprintte aynı modüle iki PR açmayın.

## Veri ve gizlilik
Her geliştiricinin kendi Mac'i, kendi veri klasörü ve kendi OpenRouter anahtarı vardır; ortak olan yalnız ekip bulutu
(`docs/EKIP.md`). Gerçek toplantı sesi ya da transkripti test verisine, PR'a, depoya girmez (`tests/fixtures` sentetiktir).
