import unittest,tempfile,json,struct,warnings
from pathlib import Path
from unittest.mock import patch
import numpy as np,soundfile as sf
from meeting_os.final_vad import isolated_regions,validate_regions,main
class Tests(unittest.TestCase):
 def test_worker_maps_float_wav_at_real_data_offset_without_reading_payload(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.wav';out=Path(d)/'out.json'
   samples=np.tile(np.array([-1.5,-0.,1e-7,0.,2.],dtype='float32'),15000)
   sf.write(p,samples,16000,subtype='FLOAT')
   # Exercise RIFF chunk parsing rather than assuming a fixed WAV header.
   raw=p.read_bytes();extra=b'JUNK'+struct.pack('<I',18)+b'fixture padding!!!'
   self.assertEqual(len(extra),26)
   p.write_bytes(raw[:4]+struct.pack('<I',len(raw)+len(extra)-8)+raw[8:12]+extra+raw[12:])
   before=p.read_bytes();calls=[]
   def regions(audio):
    self.assertIsInstance(audio,np.memmap);self.assertEqual(audio.mode,'c')
    self.assertTrue(audio.flags.writeable);self.assertEqual(audio.dtype,np.dtype('float32'))
    np.testing.assert_array_equal(audio.view('uint32'),samples.view('uint32'))
    calls.append(True);return [(1,len(audio)-1)]
   with patch('sys.argv',['worker',str(p),str(out),str(len(samples))]),patch('soundfile.SoundFile.read',side_effect=AssertionError('full payload read')),patch('meeting_os.audio.speech_regions',side_effect=regions),warnings.catch_warnings():
    warnings.simplefilter('error');main()
   self.assertEqual(calls,[True]);self.assertEqual(json.loads(out.read_text()),[[1,len(samples)-1]])
   self.assertEqual(p.read_bytes(),before)
 def test_worker_rejects_nonfinite_samples_before_vad(self):
  for bad in (float('nan'),float('inf'),-float('inf')):
   with self.subTest(bad=bad),tempfile.TemporaryDirectory() as d:
    p=Path(d)/'a.wav';out=Path(d)/'out';samples=np.zeros(65537,dtype='float32');samples[-1]=bad
    sf.write(p,samples,16000,subtype='FLOAT')
    finite=np.isfinite;sizes=[]
    def bounded_finite(a):
     sizes.append(a.size);self.assertLessEqual(a.size,65536);return finite(a)
    with patch('sys.argv',['worker',str(p),str(out),str(len(samples))]),patch('meeting_os.audio.speech_regions') as vad,patch('meeting_os.final_vad.np.isfinite',side_effect=bounded_finite),self.assertRaisesRegex(ValueError,'Invalid VAD samples'):main()
    vad.assert_not_called();self.assertFalse(out.exists())
    self.assertEqual(sizes,[65536,1])
 def test_worker_rejects_materialized_readonly_wrong_dtype_shape_rate_or_length(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'a.wav';out=root/'out';sf.write(p,np.zeros(10),16000,subtype='FLOAT')
   backing=root/'mapping';backing.write_bytes(bytes(1024))
   for kind in ('ndarray','readonly','float64','non_native','stereo','length','rate'):
    with self.subTest(kind=kind):
     rate=8000 if kind=='rate' else 16000
     mapped=np.memmap(backing,mode='r' if kind=='readonly' else 'c',dtype='float64' if kind=='float64' else '>f4' if kind=='non_native' else 'float32',shape=(5,2) if kind=='stereo' else (11,) if kind=='length' else (10,))
     if kind=='ndarray':mapped=np.zeros(10,dtype='float32')
     with patch('sys.argv',['worker',str(p),str(out),'10']),patch('scipy.io.wavfile.read',return_value=(rate,mapped)),patch('meeting_os.audio.speech_regions') as vad,self.assertRaisesRegex(ValueError,'Invalid VAD mapping'):main()
     vad.assert_not_called();self.assertFalse(out.exists())
 def test_worker_does_not_suppress_other_wav_warnings(self):
  from scipy.io import wavfile
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.wav';out=Path(d)/'out';sf.write(p,np.zeros(10),16000,subtype='FLOAT')
   def warned(*args,**kwargs):warnings.warn('Reached EOF prematurely',wavfile.WavFileWarning)
   with patch('sys.argv',['worker',str(p),str(out),'10']),patch('scipy.io.wavfile.read',side_effect=warned),warnings.catch_warnings():
    warnings.simplefilter('error')
    with self.assertRaises(wavfile.WavFileWarning):main()
   self.assertFalse(out.exists())
 def test_worker_rejects_invalid_header_without_vad(self):
  for rate,channels,subtype,frames in ((8000,1,'FLOAT',10),(16000,2,'FLOAT',10),(16000,1,'PCM_16',10),(16000,1,'FLOAT',11)):
   with self.subTest(values=(rate,channels,subtype,frames)),tempfile.TemporaryDirectory() as d:
    p=Path(d)/'a.wav';out=Path(d)/'out';sf.write(p,np.zeros((10,channels)),rate,subtype=subtype)
    with patch('sys.argv',['worker',str(p),str(out),str(frames)]),patch('meeting_os.audio.speech_regions') as vad,self.assertRaisesRegex(ValueError,'Invalid VAD snapshot'):main()
    vad.assert_not_called();self.assertFalse(out.exists())
 def test_worker_rejects_source_change_without_output(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.wav';out=Path(d)/'out';sf.write(p,np.zeros(10),16000,subtype='FLOAT')
   def regions(audio):
    # Change metadata without truncating a live mmap.
    import os
    st=p.stat();os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns+1000000));return []
   with patch('sys.argv',['worker',str(p),str(out),'10']),patch('meeting_os.audio.speech_regions',side_effect=regions),self.assertRaisesRegex(ValueError,'VAD input changed'):main()
   self.assertFalse(out.exists())
 def test_invalid_timeline_rejected(self):
  for rows in ([[0,16001]],[[2,2]],[[True,3]],[[4,5],[1,2]]):
   with self.assertRaises(ValueError):validate_regions(rows,16000)
 def test_worker_failure_and_changed_snapshot_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.wav';sf.write(p,np.zeros(16000),16000,subtype='FLOAT')
   with patch('meeting_os.final_vad.run_guarded',side_effect=RuntimeError('failed')),self.assertRaises(RuntimeError):isolated_regions(p,16000)
   def worker(cmd,**kwargs):
    Path(cmd[-2]).write_text('[[0,16000]]');p.write_bytes(b'changed')
   with patch('meeting_os.final_vad.run_guarded',side_effect=worker),self.assertRaises(ValueError):isolated_regions(p,16000)
