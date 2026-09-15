# Meeting OS — ajan ve geliştirici yönergeleri

Bu dosyayı Claude Code (`CLAUDE.md` üzerinden) ve Codex okur. Kısa tut; ayrıntı `docs/` altında.

## Ne bu
macOS SwiftUI uygulaması (`desktop/`) + Python arka uç (`meeting_os/`) + kayıt yardımcısı (`capture/`). Zoom kaydı →
OpenRouter Türkçe transkript → konuşmacı tanıma → özet/görev. 3–5 teknik olmayan kullanıcı; ilkeler: **kayıt asla
kaybolmaz, kullanıcı asla ortada kalmaz, toplantı asla yavaşlamaz, metin buluta yalnız beyaz listeyle çıkar.**

## Önce oku
`docs/KULLANIM.md` (ürün sözleşmesi), `docs/EKIP.md` ("Buluta ne çıkar"), `docs/BUNDLE.md` (paket/güncelleme),
`docs/TEAM_CLOUD.md`, `docs/ITERATION_CHECKPOINT.md` son 150 satır (ne yapıldı, ne açık), `docs/reviews/` (denetimler).

## Kurulum ve testler
- Depo `~/Library/Application Support/MeetingOS/repo-v0.1`, venv `.venv` (`sh scripts/install.sh` kurar). Python 3.12.
- Python: `MEETING_OS_TEST_IGNORE_PRESSURE=1 .venv/bin/python -m unittest discover -s tests` (≈2 dk). Bu değişken
  olmadan bellek baskısı altındaki bir Mac'te ~40 sahte hata çıkar; uygulamanın korumaları değişmez.
  Tek modül: `.venv/bin/python -m unittest tests.test_X`. Modülleri **sırayla** koş, paralel değil (bellek).
- Swift: `cd desktop && swift build && swift test`. UI testi yok; mantık saf yardımcılara çıkarılıp test edilir.
- Her davranış değişikliği bir testle gelir; denetim bulguları `tests/test_audit_repro.py` deseniyle önce kırmızı yazılır.

## Yasaklar (ajanlar için mutlak)
- `~/Library/Application Support/MeetingOS` gerçek veri klasörüne dokunma; testler `tempfile` kullanır. `meeting_os
  reports settings --set` **her zaman** gerçek klasöre yazar — ajanlar çalıştırmaz.
- `codesign`, `scripts/signing.py`, `scripts/sign-notarize.sh`, `security` komutları, anahtar zinciri: yalnız sürüm sahibi.
- Uygulamayı açma/kapatma, `open`, `osascript`: yalnız sürüm sahibi. Paket içindeki `repo/`'dan import yapma (mühür bozulur).
- Sunucuya (`root@100.87.35.111`, `/var/lib/meetingos-sync`) yazma; okuma serbest, `pkill -f` kullanma (`[e]cho` deseni).
- Gizli dosyalar (`openrouter.key`, `team.token`, `invite.json`, `download.secret`) depoya ya da pakete girmez. Depo herkese açık.

## Nasıl çalışırız
- Dal: `v0.1` bütünleşme dalı, korumalı. Her iş `<kisi>/<konu>` dalında, PR ile; CI (Python + Swift testleri) yeşil olmadan
  birleşmez. Sürüm sahibi doğrudan itebilir (yalnız sürüm commit'leri için).
- Ajanlar worktree'de çalışır (`git worktree add`), dalını commit'ler; birleştirmeyi insan yapar (`git merge --no-ff`).
  Çakışma sıcak noktaları: `meeting_os/__init__.py` + `scripts/build-desktop.sh` + `docs/KULLANIM.md` 1. satır (sürüm —
  yalnız sürüm sahibi bump'lar), `docs/ITERATION_CHECKPOINT.md` (yalnız sona ekle), `meeting_os/cli.py` choices (union),
  `meeting_os/desktop.py` housekeeping dönüşü (union). LEARNING/KULLANIM/EKIP çakışmaları birleşim ile çözülür.
- Stil: yoğun, yorumlar NEDEN'i anlatır (Türkçe alıntılar dahil), gereksiz soyutlama yok. Hata metinleri Türkçe cümle,
  ham Python istisnası kullanıcıya gösterilmez (günlükte kalır).
- Rapor: yapılan/doğrulanan ile "kodlandı ama denenmedi" ayrı; dosya:satır ve test adı ver.

## Sürüm (yalnız sürüm sahibi, Developer ID olan Mac)
`sh scripts/release.sh 1.2.90` — `docs/releases/v1.2.90.md` yazılmış olmalı. Betik: sürüm bump, CHANGELOG, uygulama
derle+kur, push+tag, paket derle, Developer ID imza + Apple noter, GitHub Releases (latest) + VPS aynası. Ayrıntı
`docs/BUNDLE.md`. Diğer geliştirici `--app-only` ile yalnız yerel uygulamayı derleyip dener; paket üretemez.
