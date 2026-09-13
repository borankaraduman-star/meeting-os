"""Exercise the release shell script without certificates, Apple services, or real signing."""

import hashlib
import os
from pathlib import Path
import plistlib
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]

# Only OS integration commands are replaced in a temporary script copy. Its shell
# control flow, JSON parsing, file publication, and cleanup all run for real.
FAKE_TOOL = r'''
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[1]).name
args = sys.argv[2:]
failure = os.environ.get("FAIL_STEP", "")
step = name
if name == "security":
    raise SystemExit("Tests must never access the keychain")
elif name == "file":
    print("Mach-O 64-bit executable arm64")
    raise SystemExit(0)
elif name == "codesign":
    if "--verify" in args:
        step = "verify"
    elif args[-1].endswith("python3"):
        step = "sign-runtime"
    elif args[-1].endswith("MeetingCapture.app"):
        step = "sign-helper"
    else:
        step = "sign-app"
    if failure == "sign-with-entitlements" and step == "sign-runtime" and "--entitlements" in args:
        step = failure
elif name == "xcrun":
    step = "notary" if args[0] == "notarytool" else "staple"
elif name == "spctl":
    step = "assess"
elif name == "ditto":
    step = "submit-zip" if args[-1].endswith("submit.zip") else "release-zip"
elif name == "shasum":
    step = "checksum"

if step == failure:
    # Even a failed notary command emitting Accepted must not pass the gate.
    print('{"status":"Accepted"}' if step == "notary" else "injected " + step + " failure")
    if name == "ditto":
        Path(args[-1]).write_bytes(b"partial zip")
    raise SystemExit(7)

if name == "xcrun" and step == "notary":
    payload = os.environ.get("NOTARY_PAYLOAD", '{"id":"test-id","status":"Accepted","message":"Processing complete"}')
    if "--output-format" in args and args[args.index("--output-format") + 1] == "json":
        print(payload)
    else:
        print("Processing complete\n" + payload)
elif name == "ditto":
    Path(args[-1]).write_bytes(b"verified release zip")
elif name == "shasum":
    import hashlib
    print(hashlib.sha256(Path(args[-1]).read_bytes()).hexdigest() + "  " + args[-1])
'''


class SignNotarizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="meetingos notarize test ")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.app = self.folder / "bundle" / "Meeting OS.app"
        resources = self.app / "Contents" / "Resources"
        (resources / "repo/build/MeetingCapture.app").mkdir(parents=True)
        runtime = resources / "runtime/bin/python3"
        runtime.parent.mkdir(parents=True)
        runtime.write_text("fake Mach-O")
        runtime.chmod(0o755)
        (self.app / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundleShortVersionString": "1.2.3",
        }))
        self.output = self.folder / "Meeting-OS-1.2.3.zip"
        self.checksum = self.folder / "Meeting-OS-1.2.3.zip.sha256"
        self.output.write_bytes(b"previous release")
        self.checksum.write_text("previous checksum\n")
        mock_bin = self.folder / "mock-bin"
        mock_bin.mkdir()
        fake_tool = self.folder / "fake_tool.py"
        fake_tool.write_text(FAKE_TOOL)
        source = (ROOT / "scripts/sign-notarize.sh").read_text()
        for command in ("/usr/bin/security", "/usr/bin/codesign", "/usr/bin/file",
                        "/usr/bin/ditto", "/usr/sbin/spctl", "xcrun", "shasum"):
            target = mock_bin / Path(command).name
            target.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " "
                              + shlex.quote(str(fake_tool)) + ' "$0" "$@"\n')
            target.chmod(0o755)
            if command.startswith("/"):
                source = source.replace(command, shlex.quote(str(target)))
        self.script = self.folder / "sign-notarize.sh"
        self.script.write_text(source)
        self.env = {
            **os.environ,
            "PATH": str(mock_bin) + os.pathsep + os.environ.get("PATH", ""),
            "MEETING_OS_DEVID": "test identity; not a certificate",
            "MEETING_OS_NOTARY_PROFILE": "offline-test-profile",
            "FAIL_STEP": "",
        }

    def run_script(self, **env):
        self.output.write_bytes(b"previous release")
        self.checksum.write_text("previous checksum\n")
        return subprocess.run(
            ["/bin/sh", str(self.script), str(self.app)],
            env={**self.env, **env}, text=True, capture_output=True, timeout=30,
        )

    def assert_preserved_release(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.output.read_bytes(), b"previous release")
        self.assertEqual(self.checksum.read_text(), "previous checksum\n")
        self.assertNotIn("==> hazır:", result.stdout)

    def test_failed_release_step_preserves_previous_zip_and_checksum(self):
        for step in ("sign-runtime", "sign-helper", "sign-app", "verify", "notary",
                     "staple", "assess", "submit-zip", "release-zip", "checksum"):
            with self.subTest(step=step):
                self.assert_preserved_release(self.run_script(FAIL_STEP=step))

    def test_failed_entitled_signature_is_not_retried_without_entitlements(self):
        self.assert_preserved_release(self.run_script(FAIL_STEP="sign-with-entitlements"))

    def test_only_accepted_json_status_can_replace_release(self):
        for payload in ('{"status":"Invalid"}', '{"status":"In Progress"}',
                        '{"message":"Accepted"}', '{"status":"accepted"}',
                        '{"status":true}', 'not json'):
            with self.subTest(payload=payload):
                self.assert_preserved_release(self.run_script(NOTARY_PAYLOAD=payload))

    def test_accepted_release_replaces_zip_and_checksum(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.output.read_bytes(), b"verified release zip")
        self.assertEqual(self.checksum.read_text(), hashlib.sha256(b"verified release zip").hexdigest() + "\n")
        self.assertIn("==> hazır:", result.stdout)


if __name__ == "__main__":
    unittest.main()
