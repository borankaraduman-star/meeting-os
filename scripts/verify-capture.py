#!/usr/bin/env python3
"""Native PCM writer check; does not request microphone permissions.

No argument: run the helper's --self-test and check the chunks it writes.
With a recording folder: read that folder's journal and check the chunks it announced, read-only. Chunks are
deleted once the cloud transcript is complete, so a finished meeting reports its assembled *-full.* files instead.
"""
import json
import os
import sys
from pathlib import Path
import subprocess
import tempfile
import numpy as np
import soundfile as sf

CLIP = 0.9999   # float32 read of a PCM_16 sample sitting on ±32767


def clipped(path):
    """Samples pinned to the top of the scale, and the peak, in one pass over the file."""
    count = 0
    peak = 0.0
    with sf.SoundFile(path) as f:
        while True:
            block = f.read(f.samplerate*10, dtype='float32')
            if not len(block): break
            peak = max(peak, float(np.abs(block).max()))
            count += int((np.abs(block) >= CLIP).sum())
    return count, peak


def report(label, path, *, want_pcm16):
    info = sf.info(path)
    if want_pcm16: assert info.subtype == 'PCM_16', f'{label}: {info.subtype}, expected PCM_16'
    count, peak = clipped(path)
    frames = info.frames or 1
    print(f'  {label}: {info.subtype} {info.samplerate} Hz x{info.channels} {info.duration:.1f} s · '
          f'peak {peak:.4f} · clipped {count} ({100.0*count/frames:.3f} %)')
    return count, frames


def summarize(kind, results):
    if not results:
        print(f'No {kind} to check.')
        return
    clip = sum(c for c, _ in results)
    total = sum(n for _, n in results)
    print(f'Summary: {len(results)} {kind}, {total} samples, {clip} clipped ({100.0*clip/max(total,1):.4f} %) · '
          + ('no clipping' if clip == 0 else 'CLIPPING PRESENT'))


def capture_binary(root):
    """The helper to exercise. MEETING_OS_CAPTURE_BIN points this at a plain `swift build` product, so the
    check can run without the signed app bundle (building one needs codesign, which not every session has)."""
    override = os.environ.get('MEETING_OS_CAPTURE_BIN')
    if override:
        path = Path(override).expanduser()
        if not path.is_file(): raise SystemExit(f'MEETING_OS_CAPTURE_BIN yok: {path}')
        return path
    return root/'build/MeetingCapture.app/Contents/MacOS/MeetingCapture'


def self_test(root):
    binary = capture_binary(root)
    with tempfile.TemporaryDirectory() as t:
        run = subprocess.run([str(binary), '--self-test', '--output', t], capture_output=True, text=True, check=True)
        events = [json.loads(line) for line in run.stdout.splitlines()]
        assert {e['source'] for e in events} == {'mic', 'system'}
        results = []
        for event in events:
            x, rate = sf.read(event['path'])
            assert rate == 16000 and len(x) == 16000
            assert abs(event['duration']-1) < 1e-6
            assert max(abs(x)) > .09
            assert event['start'] == (.25 if event['source'] == 'mic' else .5)
            results.append(report(event['source'], event['path'], want_pcm16=True))
        assert not list(Path(t).glob('*.partial.wav'))
        summarize('chunks', results)
    print(f'Native capture self-test ({binary}): separate sources, PCM_16, timing and finalized WAVs passed.')


def recording(directory):
    directory = Path(directory)
    journal = directory/'capture-native.jsonl'
    events = []
    for line in journal.read_text(encoding='utf-8', errors='replace').splitlines():
        try: event = json.loads(line)
        except ValueError: continue
        if isinstance(event, dict) and event.get('event') == 'chunk': events.append(event)
    print(f'{directory.name}: {len(events)} chunk events in {journal.name}')
    results = []
    missing = 0
    for event in events:
        path = Path(event.get('path', ''))
        if not path.is_file():
            missing += 1
            continue
        results.append(report(f"{event['source']}-{event.get('index')}", path, want_pcm16=True))
    if missing: print(f'  {missing} chunk files are no longer on disk (removed once the cloud transcript completed).')
    summarize('chunks', results)
    assembled = sorted(p for p in directory.glob('*-full.*') if p.suffix in ('.wav', '.flac'))
    if assembled:
        print('Assembled audio (kept after the chunks are compacted away):')
        summarize('assembled files', [report(p.name, p, want_pcm16=False) for p in assembled])


root = Path(__file__).resolve().parents[1]
if len(sys.argv) > 1: recording(sys.argv[1])
else: self_test(root)
