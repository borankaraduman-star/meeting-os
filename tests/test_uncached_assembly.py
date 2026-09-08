import hashlib
import contextlib
import io
import json
import os
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from meeting_os import audio
from scripts.uncached_assembly import install_uncached_assembly


class UncachedAssemblyTests(unittest.TestCase):
    def workspace(self):
        return tempfile.TemporaryDirectory(prefix='meeting-os-retry-'+'a'*32+'-')

    def fixture(self, root):
        events = []
        for source in ('mic', 'system'):
            for start, rate, seconds in ((0., 16000, .03), (.05, 48000, .025), (.06, 16000, .02)):
                path = root/f'{len(events):06d}.wav'
                x = np.linspace(-1.75, 2., round(rate*seconds), dtype=np.float32)
                sf.write(path, np.column_stack((x, x*.5)), rate, subtype='FLOAT')
                events.append({'event':'chunk', 'source':source, 'start':start, 'path':str(path)})
        (root/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
        return [Path(e['path']) for e in events]

    def test_exact_pcm_for_resampling_stereo_gaps_overlaps_and_peaks(self):
        original_soundfile = sf.SoundFile
        with self.workspace() as tmp:
            root = Path(tmp).resolve();sources = self.fixture(root)
            hashes = {p:hashlib.sha256(p.read_bytes()).digest() for p in sources}
            baseline = audio.assemble_capture(root)
            expected = {source:sf.read(path,dtype='float32')[0] for source,path in baseline.items()}
            for path in baseline.values():Path(path).unlink()
            descriptors = []
            telemetry = io.StringIO()
            def apply_flag(fd, command, value):
                self.assertEqual((command,value),(48,1));os.fstat(fd)
                descriptors.append(fd)
            with patch.object(audio,'assemble_capture',audio.assemble_capture),patch('scripts.uncached_assembly.fcntl.fcntl',side_effect=apply_flag),contextlib.redirect_stderr(telemetry):
                counts = install_uncached_assembly()
                self.assertIs(sf.SoundFile,original_soundfile)
                result = audio.assemble_capture(root)
                self.assertIs(sf.SoundFile,original_soundfile)
            self.assertEqual(counts,{'source_fds':12,'destination_fds':2})
            self.assertEqual(len(descriptors),14)
            markers = [json.loads(line)['uncached_assembly_applied'] for line in telemetry.getvalue().splitlines()]
            self.assertEqual(markers,[{'source_fds':1,'destination_fds':0},{'source_fds':3,'destination_fds':1}])
            for source,path in result.items():
                actual,rate = sf.read(path,dtype='float32')
                self.assertEqual(rate,16000)
                np.testing.assert_array_equal(actual,expected[source])
                self.assertGreater(float(np.max(actual)),1.)
                np.testing.assert_array_equal(actual[480:800],np.zeros(320,dtype=np.float32))
            self.assertEqual({p:hashlib.sha256(p.read_bytes()).digest() for p in sources},hashes)

    def test_flag_failure_closes_descriptor_and_restores_soundfile(self):
        original_soundfile = sf.SoundFile;descriptors = []
        def fail(fd, *args):
            descriptors.append(fd);raise OSError('uncached unsupported')
        with self.workspace() as tmp:
            root = Path(tmp).resolve();self.fixture(root)
            with patch.object(audio,'assemble_capture',audio.assemble_capture),patch('scripts.uncached_assembly.fcntl.fcntl',side_effect=fail):
                counts = install_uncached_assembly()
                with self.assertRaisesRegex(OSError,'uncached unsupported'):audio.assemble_capture(root)
            self.assertIs(sf.SoundFile,original_soundfile)
            self.assertEqual(counts,{'source_fds':0,'destination_fds':0})
            self.assertEqual(len(descriptors),1)
            with self.assertRaises(OSError):os.fstat(descriptors[0])

    def test_journal_accepts_unresolved_tempfile_paths_used_by_retry_capture(self):
        with self.workspace() as tmp:
            root = Path(tmp);self.fixture(root)
            with patch.object(audio,'assemble_capture',audio.assemble_capture),patch('scripts.uncached_assembly.fcntl.fcntl'):
                counts = install_uncached_assembly()
                result = audio.assemble_capture(root)
            self.assertEqual(counts,{'source_fds':12,'destination_fds':2})
            self.assertEqual(set(result),{'mic','system'})

    def test_decode_failure_restores_soundfile(self):
        original_soundfile = sf.SoundFile
        with self.workspace() as tmp:
            root = Path(tmp).resolve();sources = self.fixture(root)
            before = [p.read_bytes() for p in sources]
            with patch.object(audio,'assemble_capture',audio.assemble_capture),patch('scripts.uncached_assembly.fcntl.fcntl'),patch.object(audio,'read_audio',side_effect=ValueError('decode failed')):
                install_uncached_assembly()
                with self.assertRaisesRegex(ValueError,'decode failed'):audio.assemble_capture(root)
            self.assertIs(sf.SoundFile,original_soundfile)
            self.assertEqual([p.read_bytes() for p in sources],before)

    def test_non_snapshot_root_and_oversized_journal_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(audio,'assemble_capture',audio.assemble_capture),patch('scripts.uncached_assembly.fcntl.fcntl') as apply_flag:
                install_uncached_assembly()
                with self.assertRaisesRegex(ValueError,'private retry snapshot'):audio.assemble_capture(tmp)
                apply_flag.assert_not_called()
        with self.workspace() as tmp:
            root = Path(tmp).resolve();self.fixture(root)
            with patch.object(audio,'assemble_capture',audio.assemble_capture),patch('scripts.uncached_assembly.fcntl.fcntl') as apply_flag,patch('meeting_os.recovery_audio.MAX_JOURNAL_BYTES',32):
                install_uncached_assembly()
                with self.assertRaisesRegex(ValueError,'retry journal'):audio.assemble_capture(root)
                apply_flag.assert_not_called()

    @unittest.skipUnless(sys.platform=='darwin','F_NOCACHE is a macOS descriptor flag')
    def test_real_uncached_flag_on_synthetic_wavs(self):
        original_soundfile = sf.SoundFile
        with self.workspace() as tmp:
            root = Path(tmp).resolve();self.fixture(root)
            baseline = audio.assemble_capture(root)
            expected = {source:sf.read(path,dtype='float32')[0] for source,path in baseline.items()}
            for path in baseline.values():Path(path).unlink()
            with patch.object(audio,'assemble_capture',audio.assemble_capture):
                counts = install_uncached_assembly()
                result = audio.assemble_capture(root)
            self.assertIs(sf.SoundFile,original_soundfile)
            self.assertEqual(counts,{'source_fds':12,'destination_fds':2})
            self.assertEqual(set(result),{'mic','system'})
            for source,path in result.items():
                np.testing.assert_array_equal(sf.read(path,dtype='float32')[0],expected[source])

    def test_symlink_source_and_destination_are_rejected_without_mutation(self):
        for target in ('source','destination'):
            with self.subTest(target=target),self.workspace() as tmp,tempfile.TemporaryDirectory() as other:
                root = Path(tmp).resolve();sources = self.fixture(root)
                outside = Path(other)/'outside.wav';outside.write_bytes(sources[0].read_bytes());before=outside.read_bytes()
                link = sources[0] if target=='source' else root/'mic-full.wav'
                if link.exists():link.unlink()
                link.symlink_to(outside)
                with patch.object(audio,'assemble_capture',audio.assemble_capture),patch('scripts.uncached_assembly.fcntl.fcntl'):
                    install_uncached_assembly()
                    with self.assertRaises((ValueError,OSError)):audio.assemble_capture(root)
                self.assertEqual(outside.read_bytes(),before)

    def test_unsupported_mode_is_rejected_and_class_restored(self):
        original_soundfile = sf.SoundFile
        with self.workspace() as tmp:
            root = Path(tmp).resolve();sources = self.fixture(root);before=sources[0].read_bytes()
            def unexpected(directory):
                with sf.SoundFile(sources[0],'r+'):
                    self.fail('unsupported mode opened')
            with patch.object(audio,'assemble_capture',unexpected),patch('scripts.uncached_assembly.fcntl.fcntl'):
                install_uncached_assembly()
                with self.assertRaises(ValueError):audio.assemble_capture(root)
            self.assertIs(sf.SoundFile,original_soundfile)
            self.assertEqual(sources[0].read_bytes(),before)
