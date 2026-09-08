# macOS capture permissions and build identity

Meeting OS needs microphone and screen/system audio permission. It records audio,
not screen frames. Grants belong to the responsible application: for recordings
started in the desktop UI, that is `local.boran.meeting-os`, even though Python
starts the separate `MeetingCapture` helper. A Terminal test does not validate
the desktop application's permission.

## Confirmed September 8 failure

The system TCC log explicitly reported `Failed to match existing code requirement`
for Meeting OS and `kTCCServiceScreenCapture`. Its saved and running cdhash values
differed. Both build scripts had used ad-hoc signatures. Re-adding an existing
entry without removing the old grant left that mismatch intact; an enabled switch
was not proof of access.

## Build policy

Both builders now use `scripts/signing.py`. A unique valid existing code-signing
certificate is selected on first build, or select its SHA-1 explicitly with
`MEETING_OS_SIGNING_IDENTITY`. Its identity is pinned in the local, ignored
`build/signing-identity.json`. Later builds refuse a missing or different identity.
They stage and verify the new app before replacement, preserve the old bundle in
`build/app-backups`, and refuse replacement when the target executable is running.
Build/install serially with the application closed; the process check is a
snapshot, not a system-wide launch lock. Backups are retained for manual cleanup.

The certificate and private key remain in the macOS keychain. No private key is
exported, no trust setting is changed, and no custom permissive code requirement
is installed. Signing authorization may require the user's keychain confirmation.

For an explicit ad-hoc source bootstrap on a Mac without a certificate, set
`MEETING_OS_SIGNING_IDENTITY=-` on **each** build. This mode cannot preserve
permissions across changed builds and is not the supported stable update path.
Do not distribute this machine's local identity pin. For normal end-user installs,
ship a consistently signed, notarized application; that release work is separate
from this local development repair.

To deliberately change certificates, close the application, retain a backup of
the pin, then remove the pin and select the intended identity. Treat this as a
permission migration. Never silently fall back to ad-hoc signing.

## One-time migration of the old grant

After replacing the old ad-hoc application with the consistently signed build:

1. Quit Meeting OS and ensure no capture/finalization is active.
2. Remove its stale entry from Screen & System Audio Recording, or reset only
   this application's grant with `tccutil reset ScreenCapture local.boran.meeting-os`.
3. Add the current application in System Settings and approve it. macOS may require
   the user's Touch ID/password. Relaunch, then approve Microphone if prompted.
4. Start and stop a short recording from the actual desktop UI. Inspect the native
   journal for `started`, finalized `mic` and `system` chunks, and `stopped`.
   Confirm a second launch/recording does not prompt again.

Never edit TCC databases, reset unrelated apps, or treat a checkbox alone as a test.
macOS can still require consent after revocation, certificate changes, or its own
periodic policy. Stable signing fixes our update-induced identity mismatch, not
every possible future OS prompt.

Reference: [Apple TN3127, code signing requirements](https://developer.apple.com/documentation/technotes/tn3127-inside-code-signing-requirements).
