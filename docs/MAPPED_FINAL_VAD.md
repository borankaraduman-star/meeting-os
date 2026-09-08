# Mapped final VAD waveform

Real retry repeatedly stopped during VAD even after uncached snapshot/assembly and removal of a confirmed stopped Gradle daemon. The old worker read the entire FLOAT WAV into an anonymous array, and the silence gate allocated another waveform-sized np.abs temporary. Each array is64,000bytes per audio second.

The final worker now validates the same SoundFile header and uses scipy.io.wavfile.read(path,mmap=True). It requires a native float32, mono, writable copy-on-write np.memmap of the exact expected frame count/rate, rejects materialized fallback and retains bounded finite checks and input signatures. Only the exact benign non-data chunk warning is suppressed. Mapping remains alive through Torch views; it is not explicitly closed early. Only the final worker uses mapping; the shared silence gate now reduces65536-sample blocks and preserves threshold/NaN semantics. Silero model, state reset,512-sample windows, timing parameters and segmentation logic are unchanged.

Tests validate exact sample bits including WAV metadata offsets, invalid headers/mappings, mutations/no output, warning propagation, bounded allocations and gate behavior. Native95.58s public human constructed fixture produces exactly the same13sample spans. Sampled outer footprint319,767,896→309,003,608bytes; elapsed1.96→1.31s in one baseline-then-mapped run. These short single-order observations are not a full-meeting memory/latency claim. Clean file-backed pages remain reclaimable; model memory and overall OS pressure still apply. Evidence mapped-vad-native-2026-09-09.json.

Real long acceptance pending. Source-only implementation delegated locally; native validation performed by Codex. Do not treat this as Claude review until an actual review is recorded.
