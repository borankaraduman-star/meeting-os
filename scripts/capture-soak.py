#!/usr/bin/env python3
"""Bounded capture-only hardware run. Raw audio stays in a new local directory."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from meeting_os.supervisor import run_guarded, ChildFailure, JobCancelledError, JobMemoryLimitError, JobTimeoutError
from meeting_os.resources import MemoryPressureError, ResourceProbeError
from meeting_os.capture_metrics import timeline_metrics


def run_soak(output, minutes, binary):
    if minutes not in (5, 15, 30, 60):
        raise ValueError('Unsupported test duration')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    # No model, assembly, deletion, volume/device changes or playback.
    report = {'minutes_requested': minutes, 'scope': 'hardware_capture_only', 'status': 'failed'}
    phase = 'supervision_failed'
    try:
        with (output/'worker.jsonl').open('w') as log:
            report['resources'] = run_guarded([
                str(binary), '--seconds', str(minutes*60), '--chunk-seconds', '12',
                '--output', str(output/'capture'),
            ], timeout=minutes*60+30, isolated=True, output_stream=log, failure_details=False)
        phase = 'validation_failed'
        path = output/'worker.jsonl'
        with path.open('rb') as stream:
            data = stream.read(8*1024*1024+1)
        if len(data) > 8*1024*1024:
            raise ValueError('Journal limit')
        events = [json.loads(line) for line in data.splitlines()]
        if not all(isinstance(event, dict) for event in events):
            raise ValueError('Invalid journal')
        report['timeline'] = timeline_metrics(e for e in events if e.get('event') == 'chunk')
        # Never equate exit0 or metadata with a hardware acceptance pass.
        report['status'] = 'captured_pending_acceptance'
    except ChildFailure:
        report['error_code'] = 'capture_failed'
    except MemoryPressureError:
        report['error_code'] = 'memory_pressure'
    except ResourceProbeError:
        report['error_code'] = 'resource_probe_failed'
    except JobMemoryLimitError:
        report['error_code'] = 'memory_limit'
    except JobTimeoutError:
        report['error_code'] = 'timeout'
    except (JobCancelledError, KeyboardInterrupt):
        report['error_code'] = 'canceled'
    except Exception:
        report['error_code'] = phase
    finally:
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes', type=int, choices=(5, 15, 30, 60), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run_soak(args.output, args.minutes, ROOT/'build/MeetingCapture.app/Contents/MacOS/MeetingCapture')
    print(json.dumps(report))
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    sys.exit(main())
