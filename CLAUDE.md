@AGENTS.md

## Claude Code'a özel
- Uzun iş için opus alt ajan, `isolation: worktree`; birleştirme ve sürüm ana oturumda.
- Uzun koşuları (tam test, paket derleme, noter) ön planda tek tek koş: arka plan işler bellek azlığında öldürülüyor.
- Sürüm ritüeli ve ölçülmüş eşikler `docs/ITERATION_CHECKPOINT.md` sonunda; oradan devam et, yeniden keşfetme.
