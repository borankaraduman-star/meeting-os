# B1 read-only echo measurement

`meeting_os.echo.measure_echo(system, mic)` inspects mono normalized 16kHz arrays, each at most five seconds. No file access, model loading, network, audio mutation, suppression, transcript changes or speaker inference. The caller must supply a shared nominal timeline; differing start timestamps must be aligned first.

The bounded search uses anti-aliased 2kHz samples, normalized cross-correlation and lags within ±250ms. Positive lag means microphone follows system. Results abstain on insufficient signal, low correlation, competing peaks or the search boundary. Thresholds are provisional fixture heuristics, not calibrated confidence. A correlated copy reports signed projected gain and residual energy on the aligned overlap only. Residual energy may reflect noise, distortion, alignment error or near-end speech; it cannot establish double-talk. Correlation alone cannot establish an acoustic echo path.

Run: `.venv/bin/python -m unittest tests.test_echo`

Fixtures cover delayed attenuated copies, unrelated near-end noise, simultaneous independent content, periodic ambiguity, silence, short/invalid/oversized arrays, polarity reversal and negative lag. These are deterministic synthetic signal controls, not natural speech or diarization accuracy evidence. Inputs are verified unchanged. No duplicate-reduction claim: nothing is removed.

Next checkpoint: timeline-aware window aggregation and drift measurement, speech-shaped adversarial fixtures, followed by bounded hardware speaker/headphone controls. Integrate evidence into transcript/UI only after those measurements; preserve both raw channels throughout. Natural overlapping conversation still requires consented human reference data.

Local M4/16GiB measurement: one five-second deterministic uniform-noise fixture (120ms delay, gain0.35) took13.60ms, recovered120ms and gain0.350000. This is one warm-process measurement, not a performance distribution or a recording pipeline measurement.

Claude reviewed the complete initial module and five initial fixtures. Confirmed local-mean bias with an asymmetric DC-offset red/green regression; now normalize each aligned overlap and enforce its own energy floor. Added separated-copy ambiguity, negative lag/polarity and boundary coverage (nine tests total). Equal scores prefer the smallest absolute lag; separated comparable peaks still abstain.

Review limits: sample rate is an explicit caller contract, not inferable from a waveform spectrum. Gain is signed and not capped at one because channel amplification/polarity differ. Correlation0.75 implies residual energy at most0.4375 under this projection, so the suggested near-one residual example cannot occur. Exact search-edge abstention remains; a wider arbitrary boundary margin has no calibration evidence yet. Within10ms competing paths are unresolved at this checkpoint. Before UI use, validate speech-shaped, impulsive, drifting and real hardware examples and explain residual energy explicitly. No waveform or transcript sent to Claude.
