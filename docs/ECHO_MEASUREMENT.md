# B1 read-only echo measurement

`meeting_os.echo.measure_echo(system, mic)` inspects mono normalized 16kHz arrays, each at most five seconds. No file access, model loading, network, audio mutation, suppression, transcript changes or speaker inference. The caller must supply a shared nominal timeline; differing start timestamps must be aligned first.

The bounded search uses anti-aliased 2kHz samples, normalized cross-correlation and lags within ±250ms. Positive lag means microphone follows system. Results abstain on insufficient signal, low correlation, competing peaks or the search boundary. Thresholds are provisional fixture heuristics, not calibrated confidence. A correlated copy reports signed projected gain and residual energy on the aligned overlap only. Residual energy may reflect noise, distortion, alignment error or near-end speech; it cannot establish double-talk. Correlation alone cannot establish an acoustic echo path.

Run: `.venv/bin/python -m unittest tests.test_echo`

Fixtures cover delayed attenuated copies, unrelated near-end noise, simultaneous independent content, periodic ambiguity, silence, short/invalid/oversized arrays, polarity reversal and negative lag. These are deterministic synthetic signal controls, not natural speech or diarization accuracy evidence. Inputs are verified unchanged. No duplicate-reduction claim: nothing is removed.

Next checkpoint: timeline-aware window aggregation and drift measurement, speech-shaped adversarial fixtures, followed by bounded hardware speaker/headphone controls. Integrate evidence into transcript/UI only after those measurements; preserve both raw channels throughout. Natural overlapping conversation still requires consented human reference data.

Local M4/16GiB measurement: one five-second deterministic uniform-noise fixture (120ms delay, gain0.35) took13.60ms, recovered120ms and gain0.350000. This is one warm-process measurement, not a performance distribution or a recording pipeline measurement.

Claude reviewed the complete initial module and five initial fixtures. Confirmed local-mean bias with an asymmetric DC-offset red/green regression; now normalize each aligned overlap and enforce its own energy floor. Added separated-copy ambiguity, negative lag/polarity and boundary coverage (nine tests total). Equal scores prefer the smallest absolute lag; separated comparable peaks still abstain.

Review limits: sample rate is an explicit caller contract, not inferable from a waveform spectrum. Gain is signed and not capped at one because channel amplification/polarity differ. Correlation0.75 implies residual energy at most0.4375 under this projection, so the suggested near-one residual example cannot occur. Exact search-edge abstention remains; a wider arbitrary boundary margin has no calibration evidence yet. Within10ms competing paths are unresolved at this checkpoint. Before UI use, validate speech-shaped, impulsive, drifting and real hardware examples and explain residual energy explicitly. No waveform or transcript sent to Claude.

## B2 timeline-aware sampled evidence

`measure_timed_echo` aligns the common interval from independently timestamped bounded arrays. Input timestamps must be finite numeric seconds in0..14400; nominal offsets round to16kHz samples. Disjoint or <0.5s overlap abstains. Complex PCM is rejected; concentrated impulses (<32ms effective energy support) no longer count as adequate evidence. These thresholds remain conservative synthetic heuristics.

`summarize_echo_windows` accepts at most256 distinct nonoverlapping windows. At least three correlated windows with midpoint span>=10s are needed for a least-squares lag trend; any fit residual>2ms withholds the trend. Output says `lag_trend_ppm`, never verified clock drift. Sparse sampling can miss device/echo changes between windows. Accepted and total counts are explicit.

Use the read-only file harness from the repo:

```sh
.venv/bin/python scripts/measure-echo.py --system /absolute/system.wav --mic /absolute/mic.wav --max-windows 32
```

Inputs must already be mono16kHz WAV. Use `--system-start` and `--mic-start` for independent recording origins; assembled full files share zero. Each read is at most five seconds; files may span up to four hours. Output is JSON numeric evidence without filenames, audio, transcript or identities. It performs no suppression and has no UI/pipeline integration.

Synthetic controls recovered60ms delay despite a200ms input-origin offset, and100ppm known lag trend across three speech-shaped windows. Step changes, short spans, duplicate/overlapping windows, independent content, tonal ambiguity and impulses abstain/reject; mixtures and original files are preserved. Speech-shaped noise is not natural speech.

Existing local13.1949375s built-in speaker/mic capture was sampled at0..5s and8.1949375..13.1949375s: correlations0.70736 and0.61724, both inconclusive; accepted0/2, no drift estimate. This is a new measurement of an old controlled recording, not a new hardware run or successful acoustic-echo identification. Do not lower thresholds to make it pass. Numeric report remains in the local MeetingOS echo-timeline-review cache; no raw content was sent for review.

Claude B2 review: malformed summary rows now consistently reject with ValueError; actual overlap count is clamped to both input lengths. The permanently false clock-drift field is intentional. A separately reproduced fractional-origin file-window bug was fixed with integer sample scheduling and1ns floating-point comparison tolerance (far below one sample). File-harness review led to JSON serialization inside the sanitized error handler and an explicit nonnegative read bound; integer scheduling already makes the suggested past-end scenario unreachable. No threshold was tuned to the old hardware recording.
