# Preserve captured float samples through ASR handoff

The short hardware test contained 20 mono16k system samples above unity (peak 1.0567). Both capture assembly and CPP serial/batch handoff wrote PCM16, clipping these values and quantizing low-level samples. Reproduction with ±1.08 and ±1e-6 failed in both locations before the change.

Assembly and CPP temporary input files now use FLOAT WAV. No gain, normalization, sample-rate, channel, segmentation or speaker policy change. Arrays already use float32. Assembly checks expected source-timeline output size at four bytes/frame plus 100 MiB reserve before opening each output. This preflight does not reserve disk against concurrent writers. Float temporaries need about twice PCM16 disk space; originals are unchanged. Existing retry copies/digest/atomic transcript protections remain.

Three fidelity tests cover exact peaks/quiet samples, time gaps, original immutability, serial and batch files, and insufficient-space rejection before output creation. Combined with pipeline, CPP batch, bounded-final and retry-capture suites: 25 tests passed. Installed native CPP accepted a FLOAT WAV containing three seconds of public Turkish speech and produced a nonempty segment in 4.86s. This verifies format compatibility, not a recognition-quality gain. No private transcript was sent externally.

Assembly of the actual 18-second test capture retained system peak 1.056701 and all 20 over-unity samples. Numeric evidence: `benchmarks/results/float-audio-fidelity-2026-09-08.json`. Raw hardware audio remains ignored/local. Native decoder/model internal amplitude behavior is not proven by adapter file equality; extreme source amplitudes remain an independent quality concern.

Claude was assigned a bounded description-only review but returned an attempted tool-call text instead of a review. No completed independent approval is claimed. Existing earlier WER comparisons used PCM16 handoff and must not be represented as post-change scores. Future matched accuracy/live-latency validation remains required.
