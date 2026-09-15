# İki kişiyle paralel geliştirme

Kurallar `AGENTS.md`'de: Codex onu doğrudan, Claude Code `CLAUDE.md` üzerinden okur — yani iki kişinin dört ajanı da
aynı yönergeleri görür. Burada akış ve ilk gün var.

## Roller

| | Sürüm sahibi (Boran) | İkinci geliştirici |
|---|---|---|
| Depo | `~/Library/Application Support/MeetingOS/repo-v0.1` | istediği yer, örn. `~/dev/meeting-os` |
| Uygulama | Developer ID imzalı, noter onaylı paket üretir | kendi sertifikasıyla yerel derleme |
| Sürüm | `sh scripts/release.sh <sürüm>` | `sh scripts/release.sh <sürüm> --app-only` (yalnız kendi Mac'i) |
| Erişim | GitHub Releases, `meetingos-sync` sunucusu, anahtar zinciri | depoya push (PR ile), sunucuya yalnız okuma |

Sertifika, noter profili ve sunucu anahtarları taşınmaz: paket ve yayın tek Mac'ten çıkar. Bu bilinçli — imzalayan
kimlik değişirse uygulama içi güncelleme paketi reddeder (`docs/BUNDLE.md`).

## Bir kez: depoyu ekibe aç

Depo sahibi: `sh scripts/setup-team.sh <github-kullanıcı-adı>`. Betik arkadaşınızı push yetkisiyle davet eder ve
`v0.1` dalını korur: PR zorunlu, `python` ve `swift` CI işleri yeşil olmalı, bir onay gerekir, force-push kapalı.
Yönetici muafiyeti açık bırakılır, böylece `release.sh` doğrudan push'unu yapmaya devam eder.

## Bir kez: ikinci Mac

```sh
git clone -b v0.1 https://github.com/borankaraduman-star/meeting-os.git ~/dev/meeting-os
sh ~/dev/meeting-os/scripts/install.sh          # Homebrew, Python 3.12, venv, modeller, uygulama
```

Kendi OpenRouter anahtarı (kendi faturası) ve kendi verisi olur; veri klasörü her Mac'te
`~/Library/Application Support/MeetingOS`. Ekibe katılmak isterse Boran'ın kişisel davet bağlantısı yeter.
Gerçek toplantı sesi ve transkripti asla depoya, PR'a ya da teste girmez.

## Günlük akış

1. `git fetch && git switch -c <ad>/<konu> origin/v0.1` — dal adı kişiyi söylesin (`boran/…`, `<arkadaş>/…`).
2. İşi Claude Code'a ya da Codex'e ver. Ajan `AGENTS.md`'yi okur; uzun işler worktree'de koşar, kendi dalına commit atar.
3. Yerelde testler: `MEETING_OS_TEST_IGNORE_PRESSURE=1 .venv/bin/python -m unittest discover -s tests` ve
   `cd desktop && swift test`.
4. `git push -u origin <dal>` → `gh pr create -B v0.1`. CI iki işi de koşar (macOS runner; ffmpeg paketin
   gönderdiği `imageio-ffmpeg` ikilisiyle gelir, Homebrew beklenmez).
5. Karşı taraf gözden geçirir: Claude Code'da `/code-review`, Codex'te "review this PR". Sonra `gh pr merge --merge`.
6. Sürüm gerekince sürüm sahibi `docs/releases/vX.md` yazar, `sh scripts/release.sh X` koşar, değişiklik günlüğü
   artefaktını ve `docs/ITERATION_CHECKPOINT.md` sonunu günceller.

## Çakışmayı baştan önleme

- **İş bölümü:** biri `desktop/` (Swift/UI), diğeri `meeting_os/` + `server/` (Python). Aynı hafta aynı modüle iki
  PR açmayın; açacaksanız önce kim hangi dosyaya dokunacak konuşun.
- **Sürüm numarası** üç dosyada (`meeting_os/__init__.py`, `scripts/build-desktop.sh`, `docs/KULLANIM.md` 1. satır):
  PR'lar bump yapmaz, yalnız `release.sh` yapar.
- **Yalnız sona eklenen dosyalar:** `docs/ITERATION_CHECKPOINT.md`. Çakışırsa iki bloğu da tutun.
- **Birleşim (union) ile çözülenler:** `meeting_os/cli.py` alt komut listeleri, `meeting_os/desktop.py` housekeeping
  dönüş sözlüğü, `docs/KULLANIM.md`, `docs/LEARNING.md`, `docs/EKIP.md`.
- Ajanlara aynı anda aynı dosyayı verdiyseniz geniş `replace` yaptırmayın: 11 Eylül'de iki dal `path.name.replace(...)`
  yüzünden birbirine değdi. Birleştirme sonrası tam takım şart.

## CI ne koşar

`.github/workflows/tests.yml`, her PR'da ve `v0.1`'e her push'ta, iki iş: **python** (1328 test, bellek baskısı
bayrağı açık) ve **swift** (353 test). Yeşil değilse PR birleşmez. Yerel Mac'te bayraksız koşarsanız ~40 sahte
"bellek baskısı" hatası olağandır — uygulamanın gerçek korumaları testte kapatılmaz, yalnız test koşucusu için.
