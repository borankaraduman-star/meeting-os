import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class CppBootstrapTests(unittest.TestCase):
    def run_case(self, cached=False, fail_fetch=False, initialized=True, corrupt=False):
        with tempfile.TemporaryDirectory(prefix='cpp setup ') as tmp:
            p=Path(tmp);(p/'scripts').mkdir();(p/'bin').mkdir();(p/'build/whisper.cpp').mkdir(parents=True)
            if initialized:(p/'build/whisper.cpp/.git').mkdir()
            if corrupt:(p/'corrupt').touch()
            shutil.copy(ROOT/'scripts/build-whisper-cpp.sh',p/'scripts/build-whisper-cpp.sh')
            if cached:(p/'has-commit').touch()
            if fail_fetch:(p/'fail-fetch').touch()
            (p/'bin/git').write_text('''#!/bin/sh
[ "$1" = -C ] && shift 2
printf '%s\\n' "$1" >> calls
case "$1" in
 init) mkdir -p "$2/.git";;
 rev-parse) test ! -f corrupt;;
 cat-file) test -f has-commit;;
 fetch) test ! -f fail-fetch || exit 23; touch has-commit;;
 checkout) test -f has-commit || exit 24;;
 *) exit 25;;
esac
''')
            (p/'bin/cmake').write_text('''#!/bin/sh
echo cmake >> calls
mkdir -p build/whisper.cpp/out/bin
printf '#!/bin/sh\\nexit 0\\n' > build/whisper.cpp/out/bin/whisper-cli
chmod +x build/whisper.cpp/out/bin/whisper-cli
''')
            for name in ('git','cmake'):(p/'bin'/name).chmod(0o700)
            keep=p/'build/whisper.cpp/preserved.txt';keep.write_text('retain')
            result=subprocess.run(['/bin/sh',str(p/'scripts/build-whisper-cpp.sh')],env={**os.environ,'PATH':str(p/'bin')+':'+os.environ['PATH'],'CMAKE_BIN':str(p/'bin/cmake')},capture_output=True,text=True)
            return result,(p/'calls').read_text().splitlines(),keep.read_text()
    def test_missing_pinned_commit_is_fetched_before_build(self):
        result,calls,keep=self.run_case()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertLess(calls.index('fetch'),calls.index('checkout'))
        self.assertEqual(keep,'retain')
    def test_cached_pin_needs_no_network(self):
        result,calls,_=self.run_case(cached=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('fetch',calls)
    def test_fetch_failure_preserves_cache_and_never_builds(self):
        result,calls,keep=self.run_case(fail_fetch=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('cmake',calls)
        self.assertEqual(keep,'retain')

    def test_fresh_directory_initializes_then_fetches(self):
        result,calls,keep=self.run_case(initialized=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertLess(calls.index('init'),calls.index('fetch'))
        self.assertEqual(keep,'retain')
    def test_malformed_repo_is_preserved_without_fetch_or_build(self):
        result,calls,keep=self.run_case(corrupt=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('fetch',calls)
        self.assertNotIn('cmake',calls)
        self.assertEqual(keep,'retain')
