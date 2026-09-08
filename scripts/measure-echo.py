#!/usr/bin/env python3
"""Read bounded windows from two16kHz mono WAVs; emit numeric echo evidence only."""
import argparse
import json
import math
from pathlib import Path
import sys
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from meeting_os.echo import measure_timed_echo, summarize_echo_windows, _time


def inspect_pair(system, mic, *, system_start=0., mic_start=0., max_windows=32):
    system_start, mic_start = _time(system_start), _time(mic_start)
    if type(max_windows) is not int or not 1 <= max_windows <= 256:
        raise ValueError('Expected1..256 windows')
    with sf.SoundFile(system) as a, sf.SoundFile(mic) as b:
        for audio, start in ((a, system_start), (b, mic_start)):
            if audio.samplerate != 16000 or audio.channels != 1 or audio.format != 'WAV':
                raise ValueError('Expected16kHz mono WAV files')
            if audio.frames/16000+start > 14400:
                raise ValueError('At most four hours are supported')
        start = max(system_start, mic_start)
        end = min(system_start+a.frames/16000, mic_start+b.frames/16000)
        span = max(0., end-start)
        base = [int(math.ceil((start-origin)*16000)) for origin in (system_start, mic_start)]
        available = max(0, min(a.frames-base[0], b.frames-base[1]))
        count = min(max_windows, max(1, available//80000)) if available else 0
        rows = []
        for index in range(count):
            step = 0 if count == 1 else (available-80000)*index//(count-1)
            offsets = [offset+step for offset in base]
            for audio, offset in zip((a,b), offsets): audio.seek(offset)
            length = max(0, min(80000, a.frames-offsets[0], b.frames-offsets[1]))
            rows.append(measure_timed_echo(a.read(length), b.read(length),
                system_start=system_start+offsets[0]/16000, mic_start=mic_start+offsets[1]/16000))
        return {'scope': 'sampled_echo_evidence_no_suppression',
                'common_span_seconds': span, 'summary': summarize_echo_windows(rows), 'windows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--mic', type=Path, required=True)
    parser.add_argument('--system-start', type=float, default=0.)
    parser.add_argument('--mic-start', type=float, default=0.)
    parser.add_argument('--max-windows', type=int, default=32)
    args = parser.parse_args()
    try:
        report = inspect_pair(args.system, args.mic, system_start=args.system_start,
                              mic_start=args.mic_start, max_windows=args.max_windows)
        encoded = json.dumps(report, indent=2, allow_nan=False)
    except (ValueError, OSError, RuntimeError):
        print(json.dumps({'status': 'failed', 'error_code': 'invalid_or_unreadable_audio'}))
        return 1
    print(encoded)
    return 0


if __name__ == '__main__':
    sys.exit(main())
