# Meeting OS benchmark — synthetic

Synthetic runs only validate plumbing; they do not establish meeting accuracy.

| Config | Case | WER | Entity recall | RTF incl. startup | Peak RSS GB | Status |
|---|---|---:|---:|---:|---:|---|
| MLX turbo + Resemblyzer | turkish-tts | 0.143 | 0.818 | 0.442 | 1.217 | ok |
| MLX turbo + Resemblyzer | digital-silence | 0.000 | — | 0.285 | 0.310 | ok |
| MLX large-v3 + Resemblyzer | turkish-tts | 0.143 | 0.818 | 0.635 | 1.815 | ok |
| MLX large-v3 + Resemblyzer | digital-silence | 0.000 | — | 0.315 | 0.310 | ok |
| whisper.cpp turbo q5 + Resemblyzer | turkish-tts | 0.143 | 0.818 | 1.211 | 1.285 | ok |
| whisper.cpp turbo q5 + Resemblyzer | digital-silence | 0.000 | — | 0.231 | 0.310 | ok |
| OpenAI Whisper turbo CPU + Resemblyzer | turkish-tts | 0.143 | 0.818 | 1.111 | 3.987 | ok |
| OpenAI Whisper turbo CPU + Resemblyzer | digital-silence | 0.000 | — | 1.254 | 5.119 | ok |
| MLX turbo + ECAPA | turkish-tts | 0.143 | 0.818 | 0.414 | 2.388 | ok |
| MLX turbo + ECAPA | digital-silence | 0.000 | — | 0.327 | 0.545 | ok |
