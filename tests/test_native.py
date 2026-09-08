import subprocess
import unittest
from pathlib import Path
class NativeCaptureTests(unittest.TestCase):
    @unittest.skipUnless((Path(__file__).resolve().parents[1]/'build/MeetingCapture.app/Contents/MacOS/MeetingCapture').exists(),'build native recorder first')
    def test_native_pcm_writer(self):
        import sys
        script=Path(__file__).resolve().parents[1]/'scripts/verify-capture.py'
        result=subprocess.run([sys.executable,str(script)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
