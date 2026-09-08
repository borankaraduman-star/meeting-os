Static review only — no tools/tests run, nothing executed.

**1. `intelligence.py: validate_record` — owner silently dropped on case/whitespace mismatch**
Trigger: a named speaker makes an explicit first-person commitment (`"Ben yaparım" — Ahmet Yılmaz`), LLM returns `owner="Ahmet Yılmaz"`, but the stored `speaker_name` differs by case/whitespace (e.g. trailing space from ASR, or Turkish `İ/i` casing).
```python
any(r.get('speaker_name')==owner and re.search(...) for r in selected)
```
uses raw `==` while every other owner/speaker comparison in the codebase goes through `normalize()` (see `memory.py:actions`, `mcp.py` speaker_contributions). A legitimate explicit commitment gets its owner nulled out for a formatting reason, not a real ambiguity. Should compare `normalize(r.get('speaker_name') or '')==normalize(owner)`.

**2. `intelligence.py: analyze_rows` — evidence validated against the whole meeting, not the batch shown to the model**
Trigger: any meeting long enough to produce ≥2 chunks (`chunks()`, budget=2800).
```python
item=validate_record(parse_json(raw),rows)
```
passes the *full* `rows` (all segments in the meeting) instead of `batch` (the segments actually included in that prompt). `validate_record` builds `by_id` from whatever it's given, so a response for batch 2 can cite a `segment_id`/quote from a segment that was never in batch 2's prompt, and it will still pass because that segment exists somewhere in the full `rows`. This breaks the "evidence-bound" guarantee the module claims — evidence should be restricted to `by_id` built from the actual `batch`, not the whole transcript.

**3. `assistant.py: ask()` — quotes validated against full segment text, but model only sees a truncated excerpt**
Trigger: any search hit whose `text` is longer than 2400 characters.
```python
'text': h['text'][:2400]  # sent to the model
...
rows=[{**h,'source':'archive','flags':[]} for h in hits]  # full h['text'] used for validation
```
`validate_record` checks the quote against `by_id[sid]['text']`, which is the *untruncated* text, not the 2400-char slice actually shown to the LLM. A quote from beyond char 2400 (content the model never saw) can still pass validation. The check should run against the same truncated string that was put in the prompt.

**4. `mcp.py: call()` — `search_meetings` returns a bare list, breaking the tool response contract**
Trigger: any `tools/call` with `name="search_meetings"`.
```python
if name=='search_meetings':return mem.search(args['query'],speaker=args.get('speaker'))
```
Every other tool (`list_meetings`, `list_actions`, `get_meeting`, `speaker_contributions`) returns `{'items': [...], 'next_offset': ...}`. `search_meetings` returns a raw array instead, so a client that generically reads `result['items']` will crash or silently get nothing for this one tool.

**5. `intelligence.py: parse_json` — fails if the model emits any text outside the code fence**
Trigger: local model response like `"İşte analiz:\n```json\n{...}\n```"` (leading text before the fence, common with instruction-following slippage in local models).
```python
if text.startswith('```'):text=re.sub(...).strip()
value=json.loads(text)
```
The fence-stripping only triggers when the *entire* trimmed response starts with `` ``` ``. Any preamble/trailing prose around a fenced JSON block makes `json.loads` throw, consuming both retry attempts and raising `ValueError`, even though a valid JSON object exists in the response. Consider extracting the first balanced `{...}` (or fenced block anywhere in the text) rather than requiring the whole string to start with the fence.
