import tempfile,unittest,struct
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from meeting_os.diarization_audio_key import hash_snapshot

class Tests(unittest.TestCase):
    def test_peak_timestamp_is_not_audio_identity(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a.wav';b=Path(d)/'b.wav'
            sf.write(a,np.arange(1600,dtype=np.float32)/16000,16000,subtype='FLOAT')
            raw=bytearray(a.read_bytes());peak=raw.index(b'PEAK');raw[peak+12:peak+16]=struct.pack('<I',123)
            b.write_bytes(raw)
            self.assertNotEqual(a.read_bytes(),b.read_bytes())
            np.testing.assert_array_equal(sf.read(a,dtype='float32')[0],sf.read(b,dtype='float32')[0])
            with patch('meeting_os.diarization_audio_key.check_pressure'):
                self.assertEqual(hash_snapshot(a)[1],hash_snapshot(b)[1])
    def test_sample_change_invalidates(self):
        with tempfile.TemporaryDirectory() as d,patch('meeting_os.diarization_audio_key.check_pressure'):
            a=Path(d)/'a.wav';samples=np.zeros(16000,dtype=np.float32)
            sf.write(a,samples,16000,subtype='FLOAT');key=hash_snapshot(a)[1]
            samples[99]=np.nextafter(np.float32(0),np.float32(1))
            sf.write(a,samples,16000,subtype='FLOAT')
            self.assertNotEqual(key,hash_snapshot(a)[1])
    def test_invalid_format_and_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as d,patch('meeting_os.diarization_audio_key.check_pressure'):
            a=Path(d)/'a.wav'
            for rate,data,subtype in [(8000,np.zeros(10),'FLOAT'),(16000,np.zeros(10),'PCM_16'),(16000,np.array([float('nan')]),'FLOAT')]:
                sf.write(a,data,rate,subtype=subtype)
                with self.assertRaises(ValueError):hash_snapshot(a)
