# 1.0.2 first-run fix

Root cause: source archive omitted built app/runtime/models by design, while
Meeting OS.command only opened an already built app. README made that entry
point appear suitable for a new Mac without executing setup.

Launcher now invokes install-mac.sh if app is absent. Installer checks Apple
Silicon/macOS15, runs official Homebrew installer if missing (standard interactive
prompts preserved), installs missing Python3.12/ffmpeg, checks Swift tools and runs
existing setup. Apple tool installer may require reopening launcher when finished.
Setup errors leave terminal readable and save installation.log. No sudo passwords
are collected by Meeting OS. No security permission bypass is introduced.

Three launcher subprocess tests (fresh, already installed, installer failure),
including paths with spaces: two failed before fix, all three passed after.
Installer shell syntax checked. These use an isolated stub for installation and
open, preventing network/package changes during tests. Full fresh Mac dependency
and model installation is NOT verified on this already configured machine.

Homebrew bootstrap source: https://brew.sh/ (official installation command).

Review disposition: bootstrap stays directly attached to terminal so interactive
Homebrew prompts are not piped; only noninteractive project setup goes through tee.
Build scripts explicitly invoked with sh, reducing executable-bit dependency.
Launcher executable mode is preserved in ZIP and checked. macOS quarantine/consent
is not bypassed; README points to system security UI.
