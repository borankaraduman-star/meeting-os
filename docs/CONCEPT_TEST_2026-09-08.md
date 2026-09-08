# This Mac: concept acceptance test — 2026-09-08

## Verdict

**Not accepted as a healthy end-to-end meeting application on this shared 16 GiB M4 Mac.** System capture and a lower-memory transcription alternative worked; the default inference stack and local analysis both hit OS memory pressure. Protective termination prevented another uncontrolled run. This is evidence under the current desktop workload, not proof the models cannot run on an otherwise idle 16 GiB Mac.

## Method

A 34.487-second, 58-word synthetic Turkish product meeting was generated locally with macOS Yelda. It contains two named tasks (İpek by Friday, Çağrı tomorrow), a decision not to ship this week, an unapproved pricing proposal explicitly not to become a task, and a test-payment-service risk. It is a controlled concept fixture, **not a real multi-speaker meeting or a natural speech accuracy benchmark**.

A separate watchdog sampled OS memory pressure and `ri_phys_footprint` every 250 ms, with a 3.5 GiB footprint ceiling and 180-second wall deadline. On any non-normal pressure it killed only the isolated test process group. First verified timeout behavior with a sleeping process: terminated at 1.17 seconds. Limits are sampled, not a guarantee against every OS failure. No memory stress tools were used.

All test database/audio/logs are local at `~/Library/Caches/MeetingOS/concept-test`. No user meeting database was modified. No private recordings were sent to Claude. No audio/log files were published.

## Observed results

| Stage | Result | Evidence |
| --- | --- | --- |
| Default MLX turbo + Sherpa + Resemblyzer import | Failed acceptance | OS pressure triggered termination after 6.13 s; peak sampled footprint 2,688,043,792 bytes; no transcript produced |
| Native system capture | Passed this fixture | Capture exited 0 with stopped event; 40.41 s reconstructed system audio; reference correlation 0.99347 at 3.222 s offset |
| Native microphone capture | Not validated | Separate 40.46 s file exists but RMS is exactly zero; mute/device/permission/absence of input not distinguished |
| CPU quantized turbo transcription, GPU disabled, 2 threads | Passed this fixture | Recorded system audio processed in 11.73 s; peak footprint 1,227,163,136 bytes; normalized word error 0/58, including İpek and Çağrı |
| Local Qwen analysis on the actual CPU transcript | Failed acceptance | OS pressure triggered termination after 8.66 s; peak footprint 3,094,187,128 bytes; no analysis result |
| Speaker diarization / persistent identity | Not validated in this run | Default pipeline aborted; CPU alternative tested ASR only; single synthetic voice cannot establish multi-speaker quality |
| Summary/task correctness | Not validated | Local analysis did not complete; cannot claim task recall, ownership or rejected-proposal handling passed |
| GUI end-to-end | Not validated | Native helper and CLI/model components exercised; GUI-control tools unavailable |

CPU transcript was inserted unedited into a **test-only** SQLite meeting via the existing Store/Segment API, then the actual `meeting_os analyze` command was run. This manually staged path is explicitly not a pass of the application's default import/finalize pipeline. The CPU binary was invoked directly with `-ng -t 2`; these options are not yet the app's automatic low-memory fallback.

OS memory pressure returned to normal after both guarded aborts. No unrelated applications were terminated or settings changed.

## Product implication / next changes

1. Ship independent inference supervision to both GUI and CLI; guard must survive blocked native inference and leave recoverable status.
2. Integrate a measured low-memory CPU/quantized ASR mode and stage diarization separately instead of loading the combined stack unconditionally. The successful direct CPU experiment is a candidate, not a shipped automatic fallback.
3. Add microphone level/silence feedback so an existing but empty file is not mistaken for a functioning microphone.
4. Make local summary optional/deferred under pressure; benchmark a smaller analysis model before making it automatic on this machine. Do not retry the failing Qwen run unchanged.
5. Once stable, test multiple natural Turkish speakers, persistent identity across meetings, code switching and long recordings. Today's result does not validate those requirements.

Claude Code Sonnet independently reviewed the initial failure evidence using the existing Max session and agreed that the default run was not an accepted end-to-end test; recommended separating capture and resource-tiered inference. Subsequent CPU and analysis measurements above were measured by Codex, not claimed as Claude-reviewed.
