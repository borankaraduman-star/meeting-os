"""Torch'suz ses izi ve VAD'ın torch yoluyla eşdeğerliği (2026-10-22, docs/BUNDLE.md "Ses izi ve VAD: torch'suz").

Kayıtlı ses profilleri Resemblyzer'in torch çıktısıyla saklandı ve `model_id` korunuyor; bu yüzden ONNX yolunun
aynı vektörü vermesi bir sözleşmedir, iyileştirme değil. İki katman:

* `GoldenReference` HER ZAMAN koşar (CI'da torch yok): torch yolunun bu kliplerde ürettiği vektörler ve VAD zaman
  damgaları `tests/fixtures/onnx-equivalence.json`'da; ONNX yolu kosinüs ≥ 0.9999 ve birebir aynı damgaları
  vermeli. Altın dosya torch kuruluyken `python -m tests.test_onnx_equivalence --write-golden` ile yeniden yazılır.
* `LiveTorch` torch + Resemblyzer + silero-vad kuruluysa (requirements-local-models.txt) iki yolu aynı anda koşar,
  sentetik sesler ve uç uzunluklar dahil; yoksa atlanır.

Sesler yalnız depodaki herkese açık fikstürler (FLEURS-tr, LibriSpeech kurgusu, TTS) ve burada üretilen sentetik
sinyallerdir; hiçbir kullanıcı kaydı kullanılmaz (`capture/*.wav` bilerek yok).
"""
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT/'tests/fixtures/onnx-equivalence.json'
BENCH = ROOT/'benchmarks'
RATE = 16000
MIN_COSINE = 0.9999
VAD_ARGS = dict(sampling_rate=RATE, min_speech_duration_ms=250, min_silence_duration_ms=500, speech_pad_ms=200,
                max_speech_duration_s=28, return_seconds=False)   # meeting_os.audio.speech_regions, unchanged

FILES = [f'fleurs-tr/{i:02d}.wav' for i in range(12)] + [
    'human-constructed/four-voices.wav', 'synthetic/turkish.wav', 'synthetic/silence.wav',
    'code-switch-synthetic/mixed.wav'] + [f'cpp-batch-smoke/clip-{i}.wav' for i in range(1, 5)]


def load(name):
    from meeting_os.audio import read_audio
    return read_audio(BENCH/name)


def clips():
    """(label, audio) pairs: whole short files, the identity worker's window shapes (2.5 s, 7 s, 60 s cap) over
    the four-speaker file, and the 1-second floor (one zero-padded partial)."""
    out = []
    for name in FILES:
        audio = load(name)
        if len(audio) >= RATE and name != 'synthetic/silence.wav': out.append((name, audio[:60*RATE]))
    four = load('human-constructed/four-voices.wav')
    for seconds in (1.0, 2.5, 7.0, 60.0):
        n = int(seconds*RATE)
        for start in range(0, max(1, len(four)-n), max(n, 20*RATE)):
            out.append((f'four-voices[{start}:{start+n}]', four[start:start+n]))
    return out


def long_meeting():
    """The twelve FLEURS files back to back with every quiet run squeezed to ≤ 6 windows (192 ms): ~72 s of
    unbroken speech, so the 28 s max_speech_duration_s cut (possible_ends branch) really runs."""
    def squeeze(audio, keep=6):
        frames = audio[:len(audio)//512*512].reshape(-1, 512)
        rms = np.sqrt((frames**2).mean(1)); quiet = rms < 0.05*rms.max(); out = []; run = 0
        for frame, q in zip(frames, quiet):
            run = run+1 if q else 0
            if run <= keep: out.append(frame)
        return np.concatenate(out)
    return np.concatenate([squeeze(load(f'fleurs-tr/{i:02d}.wav')) for i in range(12)])


def synthetic():
    """Deterministic speech-like signals: harmonic voices with syllable-rate envelopes, gaps, noise."""
    rng = np.random.default_rng(20261022); t = np.arange(12*RATE)/RATE; out = []
    for f0 in (110.0, 190.0, 260.0):
        voice = sum(np.sin(2*np.pi*f0*k*t)/k for k in range(1, 12))
        envelope = (np.sin(2*np.pi*4.0*t) > -0.2)*(np.sin(2*np.pi*0.35*t) > -0.5)
        signal = 0.1*voice*envelope + 0.01*rng.standard_normal(len(t))
        out.append((f'synthetic-{int(f0)}hz', signal.astype(np.float32)))
    out.append(('white-noise', (0.05*rng.standard_normal(5*RATE)).astype(np.float32)))
    return out


def cosine(a, b):
    a = np.asarray(a, dtype=np.float64); b = np.asarray(b, dtype=np.float64)
    return float(a@b/np.linalg.norm(a)/np.linalg.norm(b))


def torch_available():
    return all(importlib.util.find_spec(m) is not None for m in ('torch', 'resemblyzer', 'silero_vad'))


class GoldenReference(unittest.TestCase):
    """Runs without torch: the ONNX path against what the torch path produced on these exact clips."""

    @classmethod
    def setUpClass(cls):
        cls.golden = json.loads(GOLDEN.read_text(encoding='utf-8'))

    def test_canonical_files_are_pinned_and_carry_the_pretrained_model_id(self):
        """Profiles saved under 'resemblyzer:39373b86598fa3da' (sha256 of pretrained.pt) keep matching only
        because THIS file is the one proven equivalent; any other file gets its own id."""
        from meeting_os import vad_onnx, voice_encoder as V
        self.assertEqual(hashlib.sha256(V.ONNX_PATH.read_bytes()).hexdigest(), V.ONNX_SHA256)
        self.assertEqual(hashlib.sha256(vad_onnx.ONNX_PATH.read_bytes()).hexdigest(), vad_onnx.ONNX_SHA256)
        encoder = V.VoiceEncoder()
        self.assertEqual(encoder.model_id, 'resemblyzer:39373b86598fa3da')
        self.assertEqual(encoder.model_id, 'resemblyzer:'+V.SOURCE_SHA256[:16])
        meta = encoder.session.get_modelmeta().custom_metadata_map
        self.assertEqual(meta['source_sha256'], V.SOURCE_SHA256)
        self.assertEqual(V.model_id_for('0'*64), 'resemblyzer:'+'0'*16)

    def test_voiceprints_match_the_torch_reference(self):
        from meeting_os.voice_encoder import VoiceEncoder
        encoder = VoiceEncoder(); reference = self.golden['resemblyzer']; scores = []
        labels = [label for label, _ in clips()]
        self.assertEqual(sorted(labels), sorted(reference), 'altın dosya bu kliplerle yazılmamış')
        for label, audio in clips():
            score = cosine(encoder.embed_utterance(audio), reference[label]); scores.append(score)
            self.assertGreaterEqual(score, MIN_COSINE, label)
        self.assertGreaterEqual(len(scores), 20)

    def test_vad_timestamps_match_the_torch_reference(self):
        from meeting_os.vad_onnx import SileroVAD, get_speech_timestamps
        model = SileroVAD(); reference = self.golden['vad']
        for name in FILES:
            self.assertEqual(get_speech_timestamps(load(name), model, **VAD_ARGS), reference[name], name)
        self.assertEqual(get_speech_timestamps(long_meeting(), model, **VAD_ARGS), reference['fleurs-long'])
        # The 28 s cap really cut: every segment is shorter than 28 s although the speech runs ~72 s unbroken.
        self.assertTrue(all(s['end']-s['start'] <= 28*RATE+2*200*RATE//1000 for s in reference['fleurs-long']))
        self.assertGreater(len(reference['fleurs-long']), 4)


@unittest.skipUnless(torch_available(), 'torch/Resemblyzer/silero-vad yok (requirements-local-models.txt)')
class LiveTorch(unittest.TestCase):
    """Both paths side by side, including synthetic signals the golden file does not carry."""

    def test_resemblyzer_vectors_are_the_same(self):
        from resemblyzer import VoiceEncoder as TorchEncoder
        from meeting_os.voice_encoder import VoiceEncoder
        torch_encoder = TorchEncoder(device='cpu', verbose=False); onnx_encoder = VoiceEncoder()
        for label, audio in clips()+synthetic():
            score = cosine(onnx_encoder.embed_utterance(audio), torch_encoder.embed_utterance(audio))
            self.assertGreaterEqual(score, MIN_COSINE, label)

    def test_silero_timestamps_are_the_same(self):
        import silero_vad, torch
        from meeting_os.vad_onnx import SileroVAD, get_speech_timestamps
        jit = silero_vad.load_silero_vad(); onnx_model = SileroVAD()
        signals = [(name, load(name)) for name in FILES]+[('fleurs-long', long_meeting())]+synthetic()
        for label, audio in signals:
            expected = silero_vad.get_speech_timestamps(torch.from_numpy(audio), jit, **VAD_ARGS)
            self.assertEqual(get_speech_timestamps(audio, onnx_model, **VAD_ARGS), expected, label)

    def test_canonical_onnx_is_the_bundled_pretrained_weights(self):
        import resemblyzer
        from meeting_os.voice_encoder import SOURCE_SHA256
        weights = Path(resemblyzer.__file__).parent/'pretrained.pt'
        self.assertEqual(hashlib.sha256(weights.read_bytes()).hexdigest(), SOURCE_SHA256)


@unittest.skipUnless(importlib.util.find_spec('librosa') is not None, 'librosa yok')
class LibrosaMel(unittest.TestCase):
    def test_filterbank_and_mel_match_librosa(self):
        import librosa
        from meeting_os.voice_encoder import mel_basis, mel_spectrogram
        np.testing.assert_allclose(mel_basis(), librosa.filters.mel(sr=RATE, n_fft=400, n_mels=40), rtol=1e-6, atol=1e-9)
        for label, audio in clips()[:6]+synthetic():
            expected = librosa.feature.melspectrogram(y=audio, sr=RATE, n_fft=400, hop_length=160, n_mels=40).astype(np.float32).T
            np.testing.assert_allclose(mel_spectrogram(audio), expected, rtol=1e-4, atol=1e-6, err_msg=label)


def write_golden():
    """Torch reference values for GoldenReference. Needs torch + Resemblyzer + silero-vad."""
    import silero_vad, torch
    from resemblyzer import VoiceEncoder as TorchEncoder
    encoder = TorchEncoder(device='cpu', verbose=False); jit = silero_vad.load_silero_vad()
    golden = {'note': 'torch 2.14 + Resemblyzer 0.1.4 pretrained.pt + silero-vad 6.2.1 JIT; tests/test_onnx_equivalence.py',
              'resemblyzer': {label: [float(f'{x:.8g}') for x in encoder.embed_utterance(audio)] for label, audio in clips()},
              'vad': {name: silero_vad.get_speech_timestamps(torch.from_numpy(load(name)), jit, **VAD_ARGS) for name in FILES}}
    golden['vad']['fleurs-long'] = silero_vad.get_speech_timestamps(torch.from_numpy(long_meeting()), jit, **VAD_ARGS)
    GOLDEN.write_text(json.dumps(golden, ensure_ascii=False, separators=(',', ':'))+'\n', encoding='utf-8')
    print(f'yazıldı: {GOLDEN} ({len(golden["resemblyzer"])} vektör, {len(golden["vad"])} VAD dizisi)')


if __name__ == '__main__':
    if '--write-golden' in sys.argv: write_golden()
    else: unittest.main()
