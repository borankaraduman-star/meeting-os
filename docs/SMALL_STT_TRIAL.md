# Multilingual Small Q5_1 trial — 2026-09-09

Downloaded only model weights from ggerganov/whisper.cpp pinned revision5359861c739e955e79d9a303bcbc70fb988958b1.190,085,487bytes; SHA256ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb verified against upstream LFS metadata. Existing Turbo weights retained; defaults unchanged. No private audio upload, paid API, recording or service changes.

Same12s private microphone chunk and current isolated live phase code, no ASR checkpoint reads: previous Turbo22.49s /1,290,750,592bytes sampled process-group peak; Small11.01s /806,734,104bytes. Small parent at ASR85,000,864bytes. OS pressure normal at Small start/end. Prior Turbo was measured earlier, so this is not a randomized environmental comparison.

Small emitted4segments vsTurbo3, sameS0speaker label and unchanged3diarization turns. Both have uncertain/different first-phrase tokens; later clauses similar with punctuation/boundary differences. No human reference, no correctness percentage, no English/code-switch coverage in this excerpt. Numeric evidence benchmarks/results/small-model-native-2026-09-09.json; private text stays in build outputs.

Current bounded comparison session7307, controller89179, build/mode-comparison-small. Five-minute live replay failed ResourceProbeError after21.22s (only silent system chunk completed); OS observed normal afterward. This is not proven model OOM. Five-minute batch worker89927 is running; retain same controller and do not start duplicate inference. Controller advances only successful modes to30minutes and skips30minutes on an observed MemoryPressureError. Scope remains30minute acceptance, not this short-clip performance result.

## Terminal outcome

Controller7307/PID89179 terminated normally after bounded tests. Five-minute batch completed: both sources300s,68segments saved,137.4357s guarded elapsed,136.2588s pipeline elapsed (RTF0.454),851,233,072bytes sampled process-group peak; parent83,608,128→92,422,864bytes; pressure1atstart/end. All copied source signatures/hashes unchanged; no profiles enrolled.

Thirty-minute batch was attempted after this pass and failed MemoryPressureError after5.8776s, sampled104,809,600bytes in its group before failure. Both assembled private mono16k FLOAT files have valid1800s headers (115,200,080bytes each), so assembly completed; the precise subsequent model stage was not recorded. Do not attribute the failure to a proven particular model or claim a reliable30minute ETA. No output text was committed to this private test DB before failure. No further automatic retry.

Live5min failed on ResourceProbeError after21.22s with only one silent source chunk and no speech rows; no live latency or30minlive acceptance. The smaller model does not fix the unresolved resource-probe failure. Shared system headroom remains the blocker for30minbatch; lowering Whisper weights alone did not establish end-to-end capacity. No guard relaxed or service closed.

Original526rawWAV files,270segments and101ASR checkpoint rows still present. Defaults unchanged; smaller model remains optional experimental local artifact. New model inference used no ASR cache; warm OS caches and changing shared workload remain comparison limitations. See small-model-modes-2026-09-09.json. Work stopped after the failed30mingate; no test/model worker remains.
