import os, shutil, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class LauncherTests(unittest.TestCase):
    def run_launcher(self,installed=False,fail=False):
        with tempfile.TemporaryDirectory(prefix='meeting setup ') as tmp:
            p=Path(tmp);(p/'scripts').mkdir();(p/'bin').mkdir()
            shutil.copy(ROOT/'Meeting OS.command',p/'Meeting OS.command')
            (p/'scripts/install-mac.sh').write_text('echo install >> calls\n'+('exit 17\n' if fail else 'mkdir -p "build/Meeting OS.app"\n'))
            (p/'bin/open').write_text('#!/bin/sh\necho open >> calls\n');(p/'bin/open').chmod(0o755)
            if installed:(p/'build/Meeting OS.app').mkdir(parents=True)
            result=subprocess.run(['/bin/zsh',str(p/'Meeting OS.command')],env={**os.environ,'PATH':str(p/'bin')+':'+os.environ['PATH']},capture_output=True,text=True)
            return result,(p/'calls').read_text().splitlines() if (p/'calls').exists() else []
    def test_fresh_archive_installs_then_opens(self):
        r,c=self.run_launcher();self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(c,['install','open'])
    def test_installed_app_opens_without_reinstall(self):
        r,c=self.run_launcher(installed=True);self.assertEqual(r.returncode,0);self.assertEqual(c,['open'])
    def test_failed_install_does_not_open(self):
        r,c=self.run_launcher(fail=True);self.assertNotEqual(r.returncode,0);self.assertEqual(c,['install'])
