"""Read visible Meeting OS accessibility geometry; never start a recording.

Run on macOS with the app open and Automation/Accessibility already authorized.
Pass --require ID repeatedly for controls that must remain inside the window.
No transcript, meeting title, audio, or profile values are collected.
"""
import argparse
import json
import subprocess
from pathlib import Path

SCRIPT = r'''
const se = Application('System Events');
const w = se.processes.byName('MeetingOS').windows[0];
const controls = [];
for (const n of w.entireContents()) {
    try {
        const id = n.attributes.byName('AXIdentifier').value();
        if (!id) continue;
        controls.push({id:id,role:n.role(),position:n.position(),size:n.size(),enabled:n.enabled()});
    } catch (_) {}
}
JSON.stringify({window:{position:w.position(),size:w.size()},controls:controls});
'''


def inspect(required):
    result = subprocess.run(['osascript', '-l', 'JavaScript', '-e', SCRIPT],
                            capture_output=True, text=True, check=True, timeout=30)
    report = json.loads(result.stdout)
    wx, wy = report['window']['position']
    ww, wh = report['window']['size']
    violations = []
    for identifier in required:
        matches = [c for c in report['controls'] if c['id'] == identifier]
        if not matches:
            violations.append({'id': identifier, 'reason': 'missing'})
        for control in matches:
            x, y = control['position']
            width, height = control['size']
            if not (width > 0 and height > 0 and x >= wx and y >= wy + 28
                    and x + width <= wx + ww + 1 and y + height <= wy + wh + 1):
                violations.append({'id': identifier, 'reason': 'outside_content_bounds'})
    report['required'] = required
    report['violations'] = violations
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require', action='append', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = inspect(args.require)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(payload)
    print(payload)
    raise SystemExit(bool(report['violations']))


if __name__ == '__main__':
    main()
