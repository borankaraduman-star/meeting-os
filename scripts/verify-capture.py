#!/usr/bin/env python3
"""Native PCM writer check; does not request microphone permissions."""
import json
from pathlib import Path
import subprocess
import tempfile
import soundfile as sf
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as t:
    run=subprocess.run([str(root/'build/MeetingCapture.app/Contents/MacOS/MeetingCapture'),'--self-test','--output',t],capture_output=True,text=True,check=True)
    events=[json.loads(line) for line in run.stdout.splitlines()]
    assert {e['source'] for e in events}=={'mic','system'}
    for event in events:
        x,rate=sf.read(event['path'])
        assert rate==16000 and len(x)==16000
        assert abs(event['duration']-1)<1e-6
        assert max(abs(x))>.09
        assert event['start']==(.25 if event['source']=='mic' else .5)
    assert not list(Path(t).glob('*.partial.wav'))
print('Native capture self-test: separate sources, PCM, timing and finalized WAVs passed.')
