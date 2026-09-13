# Fresh-Mac simulation of the shipped bundle — 2026-09-13

What a new teammate's Mac does with `Meeting-OS-1.2.86.zip`, run end to end against a scratch `HOME` so the
real `~/Library/Application Support/MeetingOS` was never touched. Everything below is a command that was
actually run and the output it actually produced.

**Headline: the in-app update is dead.** `Meeting OS.app` ships no `swap-update.sh` — not in 1.2.86, not in
1.2.85 — so `update_start` answers `{"error": "swap-update.sh bulunamadı"}` and always will. The rest of the
first-launch path is clean: the bundle relocates, the invite writes both files at 0600, the v1.2.64-shaped
database migrates without a crash, and the swap machinery itself is correct in all three of its branches
(success, refuse, restore) once the script is put where it can be found.

## Environment

| | |
|---|---|
| Bundle under test | `build/Meeting-OS-1.2.86.zip` (348 693 656 B), extracted to a scratch dir |
| Previous bundle | `v1.2.85` zip from GitHub Releases, sha256 `f7f78bee…3eb327` |
| Scratch `HOME` | `…/scratchpad/fresh-home` (and `…/old-home` for step 3) |
| OpenRouter key | fake `sk-or-v1-fresh-test-0000000000`, never used for a call |
| `team_url` | pinned to `http://127.0.0.1:9` before any team action |
| Network actually used | GitHub Releases only (`latest.json`, the 1.2.85 and 1.2.86 zips) — all public |
| `open` | stubbed by a logging script on `PATH`; no GUI was launched |

## Pass / fail

| # | Step | Result |
|---|---|---|
| 1 | Unzip, `codesign --verify --deep --strict` | **pass** |
| 1 | `runtime.json`, `runtime/bin/python3`, `runtime/bin/ffmpeg`, `repo/meeting_os` present | **pass** |
| 1 | Relocation: `import resemblyzer, silero_vad, sherpa_onnx, torch` from the moved bundle | **pass** |
| 1 | `Resources/swap-update.sh` **or** `repo/scripts/swap-update.sh` present | **FAIL — P0** |
| 2 | `setup_status` on a fresh Mac: no key, no team | **pass** |
| 2 | `team_join` from a personal link: token + key written 0600, sync error reported not raised | **pass** |
| 2 | `setup_status` again: team configured, key present | **pass** |
| 2 | `report_settings_set` (user name) | **pass** |
| 2 | `storage_housekeeping` on an empty database | **pass** |
| 2 | `heartbeat`, `team_flush` | **pass** (one stray stderr line, P3) |
| 3 | `setup_status` / `snapshot` / `storage_housekeeping` / `quality daily` on a v1.2.64-shaped DB | **pass** |
| 3 | `samples.created` re-added and backfilled by the `ALTER` migration | **pass** |
| 4 | Worker: resume → sha256 → `ditto` → `swap-update.sh` → `done`, `.previous` kept, `open` called | **pass** |
| 4 | Failed swap (a): read-only target folder → refused, old app intact, Turkish message | **pass** |
| 4 | Failed swap (b): rename fails mid-swap → old app restored, Turkish message | **pass** |
| — | `tests/test_bundle_layout.py` + `tests/test_updater_bundle.py` (50 tests) | pass — **and miss the P0** |

---

## P0 — the shipped app cannot update itself

### What happens

```
$ printf '{"action":"update_start","app_path":"/Applications/Meeting OS.app","pid":1}' \
    | "Meeting OS.app/Contents/Resources/runtime/bin/python3" -m meeting_os.desktop
{"error": "swap-update.sh bulunamadı"}
```

Same answer from the installed 1.2.85, which correctly sees that 1.2.86 exists first:

```
$ … '{"action":"update_check"}'
{"available": true, "behind": 1, "local": "1.2.85", "remote": "1.2.86", "target": "1.2.86",
 "file": "Meeting-OS-1.2.86.zip", "sha256": "801046fe…7fe1bf", "size": 348693656, …}
$ … '{"action":"update_start", …}'
{"error": "swap-update.sh bulunamadı"}
```

### Why

`updater.swap_script()` looks in two places:

```python
def swap_script(rt, root):
    inside = Path(rt.get('_path', '.')).parent/'swap-update.sh'   # Contents/Resources/
    if inside.is_file(): return inside
    return Path(root)/'scripts'/'swap-update.sh'                  # Contents/Resources/repo/scripts/
```

Neither exists in the shipped app:

```
$ ls -l "…/Meeting OS.app/Contents/Resources/swap-update.sh"
ls: …: No such file or directory
$ ls -ld "…/Meeting OS.app/Contents/Resources/repo/scripts"
ls: …: No such file or directory
$ find "…/Contents/Resources/repo" -maxdepth 3 -name '*.sh'      # (no output)
```

`Contents/Resources` holds exactly `AppIcon.icns`, `repo/`, `runtime/`, `runtime.json`.
`scripts/build-bundle.sh` never writes `Resources/swap-update.sh` (`grep -n swap scripts/build-bundle.sh`
returns nothing), and the repo copy is governed by one line in `scripts/bundle_manifest.py`:

```python
#: Nothing under scripts/ runs at runtime: probe.py and reports.py only NAME `scripts/install.sh`,
#: `scripts/update.sh` and `scripts/fix-signing-prompts.sh` inside hint strings, and the bundle channel
#: replaces the git update path altogether. Kept as an explicit empty list so a future runtime dependency
#: has somewhere obvious to go.
REPO_SCRIPTS: list = []
```

The comment is the bug. The bundle channel does not *replace* the git update path's scripts — it introduces a
new runtime dependency on one of them, `scripts/swap-update.sh`, which `updater.run_download()` spawns as the
last step of every update. This has been true since `ff9fd14` ("bundle: self-contained Meeting OS.app"), the
commit that both introduced the bundle channel and set `REPO_SCRIPTS = []`.

### Why the tests are green

`tests/test_bundle_layout.py::test_nothing_under_scripts_is_needed_at_runtime` exists to catch precisely this:

```python
self.assertEqual(M.REPO_SCRIPTS, [])
runner = []
for path in (ROOT / 'meeting_os').glob('*.py'):
    text = path.read_text(encoding='utf-8')
    for marker in ("run(['sh'", 'Popen(["sh"', "Popen(['sh'", "'scripts/build"):
        if marker in text: runner.append(path.name)
self.assertEqual(runner, [])
```

`updater.py` spawns its shell as `Popen(['/bin/sh', str(swap), …])`. None of the four markers match
`Popen(['/bin/sh'`, so `runner` is empty for the wrong reason and the test asserts `[] == []`. Verified:

```
  marker "run(['sh'"            -> no match
  marker 'Popen(["sh"'          -> no match
  marker "Popen(['sh'"          -> no match
  marker "'scripts/build"       -> no match
  actual literal in file: "Popen(['/bin/sh'" -> present
```

`tests/test_updater_bundle.py` passes a **fake** swap script into `run_download()`, so it proves the worker
calls *a* script correctly and never asks whether the real one ships. 50 tests, all green, bug intact.

### What a real teammate sees

`auto_update` defaults to `false`, so this does not fire on its own. It fires when they act on the update the
app is advertising: the sidebar and the menu-bar item both show **"Güncelle ve yeniden başlat"** (with
"1 değişiklik"), they click it, and `App.swift:startUpdate()` takes the `catch` branch —
`self.error = error.localizedDescription` — so the app shows an error banner reading
`swap-update.sh bulunamadı` and stays on the old version. Forever, and on every retry.

**There is no in-app way out of this.** A teammate on 1.2.85 cannot reach 1.2.86, and a teammate on 1.2.86
will not reach 1.2.87. Every upgrade until this is fixed has to be Boran re-sending the download link and the
teammate dragging the app to Uygulamalar again — and the first bundle carrying the fix must be distributed
that way too.

### Fix

One line in `scripts/bundle_manifest.py`:

```python
REPO_SCRIPTS: list = ['swap-update.sh']
```

`build-bundle.sh` already copies `REPO_SCRIPTS` into `repo/scripts/` and `swap_script()` already falls back
there, so nothing else changes. The alternative documented in `docs/BUNDLE.md`
(`Contents/Resources/swap-update.sh`, which wins over the repo copy) works too but needs a new line in
`build-bundle.sh` and lands outside the manifest that the layout tests read.

Then either fix the marker list in `test_nothing_under_scripts_is_needed_at_runtime` — it should also look for
`/bin/sh` — or keep the direct assertion added here. `tests/test_bundle_swap_script.py` (new, committed with
this review) is **RED until the manifest line lands**, and asserts the requirement rather than pattern-matching
the source:

```
FAIL: test_the_manifest_copies_the_script_the_bundle_channel_runs
AssertionError: 'swap-update.sh' not found in [] : the bundle update channel runs scripts/swap-update.sh; …
FAIL: test_swap_script_resolves_to_a_real_file_inside_a_bundle
AssertionError: False is not true : update_start would raise "swap-update.sh bulunamadı"; resolved to
  …/Meeting OS.app/Contents/Resources/repo/scripts/swap-update.sh
```

---

## Step 1 — unzip, signature, relocation

```
$ ditto -x -k build/Meeting-OS-1.2.86.zip <scratch>/bundle          # 3.8 s, exit 0
$ codesign --verify --deep --strict --verbose=2 "<scratch>/bundle/Meeting OS.app"
…/Meeting OS.app: valid on disk
…/Meeting OS.app: satisfies its Designated Requirement            # exit 0
$ codesign -dv …
Identifier=local.boran.meeting-os    TeamIdentifier=WHA43MLZN6
Signed Time=Sep 11, 2026 at 10:30:40 PM     Sealed Resources version=2 rules=13 files=8953
```

The signature survives the move to a path it was not built at. Layout:

```
OK   Contents/Resources/runtime.json
OK   Contents/Resources/runtime/bin/python3
OK   Contents/Resources/runtime/bin/ffmpeg
OK   Contents/Resources/repo/meeting_os
MISS Contents/Resources/swap-update.sh        <- P0
MISS Contents/Resources/invite.json           <- expected: GitHub channel ships no secrets
MISS Contents/Resources/download.secret       <- expected: download_base overrides it
```

```json
{"python": "runtime/bin/python3", "repo": "repo", "bundled": true, "version": "1.2.86",
 "download_base": "https://github.com/borankaraduman-star/meeting-os/releases/latest/download"}
```

Relocation test, run from the extracted bundle at its new path:

```
$ ./runtime/bin/python3 -c "import resemblyzer, silero_vad, sherpa_onnx, torch; print('IMPORTS OK')"
…/site-packages/webrtcvad.py:1: UserWarning: pkg_resources is deprecated as an API. …
IMPORTS OK
torch 2.14.0
$ ./runtime/bin/python3 -c "import sys; print(sys.prefix)"
<scratch>/bundle/Meeting OS.app/Contents/Resources/runtime          # relocated correctly
$ ./runtime/bin/ffmpeg -version | head -1
ffmpeg version 7.1
$ ./runtime/bin/python3 -V
Python 3.12.14
```

`doctor` from inside the bundle finds the capture helper, the bundled ffmpeg and the sherpa model, and reports
`resemblyzer/silero_vad/sherpa_onnx: true` with the local-model packages absent, which is the intended shape.

## Step 2 — first launch

Every call is the bundled bridge with `cwd=repo`, `PATH=runtime/bin:$PATH`, scratch `HOME`.

**`setup_status` (fresh).** Exit 0, **stderr empty**.

```json
{"team_root_kind": "none", "api_key": false, "api_key_keychain": false,
 "team_cloud": {"configured": false, "url": "https://hermes-vps.tail2d8c7e.ts.net/meetingos", …},
 "glossary_terms": 19, "reports_writable": true, "update_behind": 0, "update_error": ""}
```

It created `meeting-os.sqlite` and made one network call (`latest.json` from GitHub) that said "up to date",
which is correct: the installed 1.2.86 *is* latest. Note there is no `bundled` key in this answer — Swift
reads `runtime.json` itself via `BundleInfo`, per `docs/BUNDLE.md`.

**`team_join`** with `meetingos://join?team=<64 hex>&key=sk-or-v1-fresh-test-0000000000`, after pinning
`team_url` to `http://127.0.0.1:9`. Exit 0, **stderr empty**:

```json
{"joined": true, "team_id_short": "040d7b", "key_written": true,
 "synced": {"pushed": 0, "pulled": 0, …,
            "error": "URLError: <urlopen error [Errno 61] Connection refused>"}}
```

The unreachable server came back as an error inside the answer, exactly as `accept_invite`'s docstring
promises — nothing raised, the join still succeeded. Modes are right:

```
drwx------  <DATA>            -rw-------  <DATA>/team.token        (65 B)
-rw-------  <DATA>/openrouter.key   (0600)  -rw-------  <DATA>/settings.json
-rw-------  <DATA>/meeting-os.sqlite        -rw-------  <DATA>/team-cloud-state-040d7b.json
```

**`setup_status` (after).** `api_key: true`, `team_root_kind: "cloud"`, `team_id_short: "040d7b"`,
`url: "http://127.0.0.1:9"`. Exit 0, stderr empty.

**`report_settings_set`** → `user_name: "Yeni Arkadas"`, `user_name_confirmed: true`. Exit 0, stderr empty.

**`storage_housekeeping` on an empty database.** Exit 0, **stderr empty, no exception** — the specific thing
this step was there to check. It ran every idle derivation on zero rows and each one degraded rather than
divided by zero:

```json
{"learning": {"removed": 0, "rows": 1}, "calibration": {"n": 0, "enough": false,
 "line": "kalibrasyon: veri yetersiz (n=0)"},
 "experiments": {"ran": true, "verdicts": {"identity_bars": "insufficient", "review_order": "insufficient",
                                           "hint_ranking": "insufficient"}},
 "preferences": {"detail": null, "fresh": true}, "task_errors": {"classes": {…all 0}, "fresh": true},
 "retention_days": 30, "removed_meetings": 0, "retention_warning": null}
```

**`heartbeat`.** Exit 0, wrote `team/040d7b/reports/<host>/heartbeat.json`. One stderr line (below).

**`team_flush`.** Exit 0, stderr empty, `{"flushed": false, "pending": false, "reasons": [], "error": null}` —
the empty-outbox short circuit, no network at all. Forced (`"force": true`) it took the real path and returned
`{"flushed": true, …, "error": "URLError: <urlopen error [Errno 61] Connection refused>"}`.

### P3 — a Python exception string is shown to the user in the middle of a Turkish sentence

`team_cloud` stores the raw `str(exc)` and `SetupStatus.swift:151` interpolates it verbatim:

```swift
return SetupCheck(id:"team",title:"Ekip bilgi tabanı",state:.optional,
                  hint:"bulut şu an erişilemiyor (\(lastError))"+…)
```

An offline teammate reads **"bulut şu an erişilemiyor (URLError: \<urlopen error [Errno 61] Connection
refused\>); yerel bilgi korunuyor, bağlanınca eşitlenir"**. The same string is written into `errors.jsonl`,
which is what `docs/BASLANGIC.md` tells them to send to Boran:

```json
{"kind": "cloud", "message": "Ekip bulutu eşitlenemedi: URLError: <urlopen error [Errno 61] Connection refused>", …}
```

Keep the raw form in the journal (it is diagnostic), map the common `URLError`/`timeout` cases to a Turkish
sentence for the card.

### P3 — a `UserWarning` on the bridge's stderr

```
$ … '{"action":"heartbeat","app":{"version":"1.2.86"}}'
…/site-packages/webrtcvad.py:1: UserWarning: pkg_resources is deprecated as an API. …
  import pkg_resources
{"path": "…/heartbeat.json"}
```

Harmless today — the bridge's contract is stdout and the JSON is clean — but it fires on every action that
reaches `webrtcvad`, and `setuptools` ≥ 81 will turn it into an `ImportError`. Pin `setuptools<81` in the
bundle or stop importing `pkg_resources`.

## Step 3 — data migration from a v1.2.64-shaped database

`git show v1.2.64:meeting_os/store.py` confirms the exact old shape: `samples` had `deleted_by` but **not**
`created`, `corrections` already had `previous_name` and `feedback`, and every table listed in the brief
(`learning_events`, `insight_edits`, `review_results`, `team_words`, `team_profile_blocks`, `word_dismissals`,
`taught_words`) is created lazily by its own module with `CREATE TABLE IF NOT EXISTS` at point of use.

Seeded a meeting (3 segments, 2 speakers, 1 sample, 1 correction) with the current code, then downgraded:

```sql
DROP TABLE IF EXISTS learning_events;  -- the only one that had actually materialised
DROP TABLE IF EXISTS insight_edits; … DROP TABLE IF EXISTS taught_words;
CREATE TABLE samples_old(id INTEGER PRIMARY KEY, name TEXT, model TEXT, vector TEXT,
                         duration REAL, provenance TEXT, deleted_by TEXT);
INSERT INTO samples_old SELECT id,name,model,vector,duration,provenance,deleted_by FROM samples;
DROP TABLE samples; ALTER TABLE samples_old RENAME TO samples;
```

```
tables:  corrections meetings profile_stats rejections samples segments text_edits
samples: id name model vector duration provenance deleted_by          <- no `created`
```

Then, through the bundled bridge and CLI — **every one exit 0 with empty stderr, no crash**:

| Action | Result |
|---|---|
| `setup_status` | `team_root_kind: "cloud"`, `api_key: true` |
| `snapshot` | 1 meeting, `{"segments": 3, "seconds": 14.0, "speakers": 2, "names": ["Boran"]}`, 3 segments |
| `storage_housekeeping` | full answer, `learning.rows: 0` (table recreated empty) |
| `quality daily` (CLI) | full metric block, `meetings: 1`, `meetings_analysed: {"n":0,"d":1,"rate":0.0}` |
| `quality report` (CLI) | `transcript_words: 8`, `edits_per_1000_words: 0.0` |
| `doctor` (CLI) | clean |

The `ALTER` migration ran and backfilled, exactly as its comment promises:

```
samples: id name model vector duration provenance deleted_by created
1|Boran|m-old-1:0|2026-09-13T19:31:34      -- dated from the meeting the provenance names
```

**No migration defect found.** The lazy-`CREATE TABLE` convention is what carries this: a table that is not
there is created by the first module that needs it rather than crashing a reader.

## Step 4 — real update swap

1.2.85 installed at `<scratch>/Applications/Meeting OS.app`, `open` stubbed, the worker invoked exactly as
`start_bundle()` spawns it. To exercise the resume path for real, a 300 000 000-byte prefix of the 1.2.86 zip
was pre-placed in the cache; the worker fetched the remaining ~48.7 MB with a `Range` request.

```
$ python3 -m meeting_os.updater --bundle-download \
    --base https://github.com/borankaraduman-star/meeting-os/releases/latest/download \
    --data-dir "<scratch>/fresh-home/Library/Application Support/MeetingOS" \
    --app "<scratch>/Applications/Meeting OS.app" --pid 91482 \
    --swap "<scratch>/swap-update.sh" --from-version 1.2.85 --cache "<scratch>/cache"
WORKER_EXIT=0
```

`--swap` had to point at the repo's copy: the bundle carries none (P0). Everything else is the shipped path.

**`update-status.json` transitions**

| state | message | evidence |
|---|---|---|
| `downloading` | `Yeni sürüm indiriliyor · %N` + `percent` | written per percent change |
| `verifying` | `Paket doğrulanıyor` | sha256 matched `801046fe…7fe1bf` |
| `extracting` | `Paket açılıyor` | `ditto -x -k` into `cache/meeting-os-update.7sbm4gj5` |
| `swapping` | `Yeni sürüm yerine konuyor · uygulama yeniden açılacak` | `{"state":"swapping","from":"1.2.85","to":"1.2.86","percent":100,"time":"2026-09-13 19:33:04"}` |
| `done` | `Güncellendi: 1.2.86` | `{"state":"done","from":"","to":"1.2.86","time":"2026-09-13 19:33:26"}` |

Resume worked: the cached file went from 300 000 000 to 348 693 656 B, and the completed zip passed sha256
(a restart-from-zero would also have passed, but the transfer took ~30 s for ~48 MB, not ~350 MB).

**`update.log`**

```
== 2026-09-13 19:33:04 takas başladı (…/cache/meeting-os-update.7sbm4gj5/Meeting OS.app → …/Applications/Meeting OS.app, pid 91482)
== 2026-09-13 19:33:26 takas tamam (…/Applications/Meeting OS.app · 1.2.86)
```

22 s between the two lines: the script waited out the `sleep 30` stand-in before touching anything. After:

```
Meeting OS.app            -> 1.2.86
Meeting OS.app.previous   -> 1.2.85
[fake-open 19:33:27] args: …/Applications/Meeting OS.app
staging dir: gone (rmdir succeeded)
```

`.previous` kept, quarantine strip attempted, `open` called on the new app. **Correct in every particular.**

### Failed swap (a) — target folder not writable

```
$ chmod 500 "<scratch>/Applications"
$ sh swap-update.sh "<staging>/Meeting OS.app" "<scratch>/Applications/Meeting OS.app" <pid>
SWAP_EXIT=1
```

```json
{"state":"failed","from":"","to":"1.2.86",
 "message":"Uygulama klasörü yazılabilir değil (…/Applications) · uygulamayı Uygulamalar'a taşıyın",
 "time":"2026-09-13 19:34:01"}
```

```
update.log: swap: …/Applications yazılabilir değil
Applications/Meeting OS.app -> 1.2.85    (untouched)
staging: emptied (rm -rf "$NEW")
open: never called
```

Refused before touching the installed app, Turkish message that names the remedy. **Pass.**

### Failed swap (b) — rename fails after the old app was moved aside

Staging dir made read-only, so `mv "$TARGET" "$PREV"` succeeds and `mv "$NEW" "$TARGET"` fails — the restore
branch:

```
update.log:
  mv: rename …/staging/Meeting OS.app to …/Applications/Meeting OS.app: Permission denied
  swap: yeni sürüm yerine konamadı; eski sürüm geri alınıyor
{"state":"failed","from":"","to":"1.2.86",
 "message":"Yeni sürüm yerine konamadı; eski sürüm geri alındı","time":"2026-09-13 19:34:24"}
Applications/Meeting OS.app -> 1.2.85    (restored from .previous)
[fake-open 19:34:24] args: …/Applications/Meeting OS.app
```

Old app restored and reopened. **Pass.**

### P3 — branch (a) leaves the app closed

By the time `swap-update.sh` runs, the app has already quit (Swift quits on `swapping`). The restore branch
reopens it (`open "$TARGET"`, line 70) but the not-writable branch (line 44-48) just `exit 1`s. A teammate who
runs Meeting OS from `~/Downloads` clicks update, watches it download for minutes, and is left with no app on
screen and no message until they relaunch by hand. One `open "$TARGET" 2>/dev/null || true` before that
`exit 1` makes the two branches behave the same.

### P3 — the 350 MB zip is never deleted

Nothing removes `~/Library/Caches/MeetingOS/update/Meeting-OS-<version>.zip` after a successful swap:
`swap-update.sh` only `rmdir`s the (empty) staging folder, and `run_download` unlinks the zip only when sha256
*fails*. Each release has a new filename, so they accumulate — with `.previous` (~1 GB) and the app itself
(~1 GB) that is ~2.4 GB after the first update and +350 MB per release after that. `Caches` is purgeable by
macOS, which is the documented reason for putting it there, so this is minor — but `run_download` could
`unlink()` the zip once the swap script is spawned.

### `from` is lost on the last two writes

`updater.write_status` carries `from_version` through `swapping`, but `swap-update.sh`'s `status()` hardcodes
`"from":""`, so the final `done` (and both `failed`s) report `{"from":""}`. The shell script genuinely does not
know the old version — it only reads the *new* app's `Info.plist`. Cosmetic unless something starts reading
`from`; worth one argument if a "1.2.85 → 1.2.86" line is ever wanted.

## What a real teammate would see, start to finish

1. Downloads ~350 MB from GitHub, drags the app to Uygulamalar, hits Gatekeeper once, "Yine de Aç". **Works.**
2. Welcome screen asks for a name and offers the invite box. Pastes the `meetingos://join?…&key=…` link.
   Team and key land in one action, both files 0600. **Works.** If the team server is unreachable they get a
   Turkish sentence with a raw Python `URLError` in the middle of it (P3).
3. Setup card goes green: key present, team `040d7b`, glossary 19 terms, reports writable. **Works.**
4. Records, transcribes, summarises — not exercised here (no real OpenRouter calls), but the bundle imports
   every package the cloud path needs from its relocated path and finds its own ffmpeg and sherpa model.
5. Two weeks later the sidebar says **"Güncelle ve yeniden başlat · 1 değişiklik"**. They click it. An error
   banner appears reading `swap-update.sh bulunamadı` and the app stays on the old version. Clicking again
   does the same thing. **This is the whole finding.** Boran has to hand-deliver every release until the
   manifest line lands — including the one that fixes it.

## Recommended order

1. `REPO_SCRIPTS = ['swap-update.sh']` in `scripts/bundle_manifest.py`; cut 1.2.87; distribute it by link,
   since no installed copy can pull it. (P0)
2. Fix or replace `test_nothing_under_scripts_is_needed_at_runtime`; keep
   `tests/test_bundle_swap_script.py` green from then on. (P0's guard)
3. `open "$TARGET"` on the not-writable branch of `swap-update.sh`. (P3)
4. Turkish mapping for `URLError`/timeout on the setup card; keep the raw string in `errors.jsonl`. (P3)
5. `zip_path.unlink()` after the swap script is spawned; pin `setuptools<81` in the bundle. (P3)

## Reproducing

Scratch `HOME`, a fake key, `team_url` at `http://127.0.0.1:9`, and a logging `open` on `PATH` are enough —
no signing, no install scripts, no real OpenRouter call. Logs and status files from this run are under
`<scratchpad>/logs/`; the extracted bundles and the 350 MB zips were deleted afterwards.
