"""Resemblyzer ses izi, torch'suz: aynı ağ ONNX'te, ön işleme numpy'de.

Neden: paket yalnız bu küçük LSTM için 475 MB'lık torch taşıyordu (+ librosa/numba/llvmlite yalnız mel için).
Ağ `scripts/convert-resemblyzer-onnx.py` ile bir kez çevrildi (`assets/resemblyzer.onnx`); burada kalan her
şey Resemblyzer 0.1.4'ün `VoiceEncoder.embed_utterance` + `audio.wav_to_mel_spectrogram` + `librosa
.feature.melspectrogram` (center=True, sıfır dolgu, periyodik Hann, güç 2, Slaney mel) davranışının birebir
karşılığıdır. `tests/test_onnx_equivalence.py` torch kuruluyken aynı klipler için iki yolun vektörlerini
karşılaştırır (kosinüs ≥ 0.9999) ve mel/filtre bankasını librosa'ya karşı denetler.

Model kimliği: kayıtlı ses profilleri `'resemblyzer:'+sha256(pretrained.pt)[:16]` ile saklandı ve eşleşme
yalnız aynı kimlikteki profillerle yapılır (`Store.profiles`, `cloud_finalize`). ONNX dosyası o .pt'nin
aynı ağırlıklarıdır ve çıktısı eşdeğerlik testinde aynı vektördür; bu yüzden kanonik ONNX dosyası (özeti
ONNX_SHA256'ya sabit) kaynak .pt'nin kimliğini taşır ve hiçbir profil yeniden kaydı gerekmez. Başka her dosya
kendi özetiyle tanınır — eskiden özel bir .pt için olduğu gibi — yani denetlenmemiş bir dosya asla eski
profillerle eşleşmiş sayılmaz.
"""
import hashlib
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

ASSETS = Path(__file__).resolve().parent/'assets'
ONNX_PATH = ASSETS/'resemblyzer.onnx'
#: sha256 of assets/resemblyzer.onnx as written by scripts/convert-resemblyzer-onnx.py (torch 2.14, opset 17).
ONNX_SHA256 = '107f7802391b06c9261b533cb3b614d864cab86a6d9d4dfab1e1d6b8272edc72'
#: sha256 of Resemblyzer 0.1.4's pretrained.pt, the weights the ONNX file was converted from. Every saved
#: profile's model id is 'resemblyzer:' + the first 16 hex of this.
SOURCE_SHA256 = '39373b86598fa3da9fcddee6142382efe09777e8d37dc9c0561f41f0070f134e'

# resemblyzer/hparams.py
SAMPLING_RATE = 16000
N_FFT = int(SAMPLING_RATE*25/1000)      # mel_window_length 25 ms → 400
HOP = int(SAMPLING_RATE*10/1000)        # mel_window_step 10 ms → 160
N_MELS = 40
PARTIAL_FRAMES = 160                    # 1.6 s
EMBEDDING_SIZE = 256


def model_id_for(digest):
    """The canonical ONNX file carries its source .pt's id (see module docstring); anything else its own."""
    return 'resemblyzer:'+(SOURCE_SHA256 if digest == ONNX_SHA256 else digest)[:16]


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- mel (librosa 1.0 semantics)

def _hz_to_mel(freqs):
    """librosa.hz_to_mel(htk=False): Slaney — linear below 1 kHz, logarithmic above."""
    freqs = np.asanyarray(freqs, dtype=np.float64)
    f_sp = 200.0/3; mels = freqs/f_sp
    min_log_hz = 1000.0; min_log_mel = min_log_hz/f_sp; logstep = math.log(6.4)/27.0
    return np.where(freqs >= min_log_hz, min_log_mel+np.log(np.maximum(freqs, min_log_hz)/min_log_hz)/logstep, mels)


def _mel_to_hz(mels):
    mels = np.asanyarray(mels, dtype=np.float64)
    f_sp = 200.0/3; freqs = f_sp*mels
    min_log_hz = 1000.0; min_log_mel = min_log_hz/f_sp; logstep = math.log(6.4)/27.0
    return np.where(mels >= min_log_mel, min_log_hz*np.exp(logstep*(mels-min_log_mel)), freqs)


@lru_cache(maxsize=1)
def mel_basis():
    """librosa.filters.mel(sr=16000, n_fft=400, n_mels=40, fmin=0, fmax=sr/2, htk=False, norm='slaney'),
    float32 [40, 201]."""
    fftfreqs = np.fft.rfftfreq(n=N_FFT, d=1.0/SAMPLING_RATE)
    mel_f = _mel_to_hz(np.linspace(_hz_to_mel(0.0), _hz_to_mel(SAMPLING_RATE/2), N_MELS+2))
    fdiff = np.diff(mel_f)
    ramps = np.subtract.outer(mel_f, fftfreqs)
    weights = np.zeros((N_MELS, 1+N_FFT//2), dtype=np.float32)
    for i in range(N_MELS):
        lower = -ramps[i]/fdiff[i]
        upper = ramps[i+2]/fdiff[i+1]
        weights[i] = np.maximum(0, np.minimum(lower, upper))
    enorm = 2.0/(mel_f[2:N_MELS+2]-mel_f[:N_MELS])
    weights *= enorm[:, np.newaxis]
    weights.flags.writeable = False
    return weights


@lru_cache(maxsize=1)
def _window():
    """scipy.signal.get_window('hann', 400, fftbins=True): the periodic Hann window librosa uses."""
    n = np.arange(N_FFT, dtype=np.float64)
    window = 0.5-0.5*np.cos(2.0*np.pi*n/N_FFT)
    window.flags.writeable = False
    return window


def mel_spectrogram(wav):
    """resemblyzer.audio.wav_to_mel_spectrogram: power mel, NOT log; float32 [frames, 40]."""
    y = np.asarray(wav, dtype=np.float32)
    pad = N_FFT//2
    y = np.pad(y, (pad, pad), mode='constant')                 # center=True, pad_mode='constant'
    n_frames = 1+(len(y)-N_FFT)//HOP
    frames = np.lib.stride_tricks.sliding_window_view(y, N_FFT)[::HOP][:n_frames]
    # librosa multiplies the float32 frames by its float64 window, runs rfft in float64 and stores complex64.
    spectrum = np.fft.rfft(frames*_window(), axis=1).astype(np.complex64)
    power = np.abs(spectrum)**2                                # float32 [frames, 201]
    return (power@mel_basis().T).astype(np.float32)


def partial_slices(n_samples, rate=1.3, min_coverage=0.75):
    """resemblyzer.VoiceEncoder.compute_partial_slices, unchanged."""
    assert 0 < min_coverage <= 1
    samples_per_frame = int(SAMPLING_RATE*10/1000)
    n_frames = int(np.ceil((n_samples+1)/samples_per_frame))
    frame_step = int(np.round((SAMPLING_RATE/rate)/samples_per_frame))
    assert 0 < frame_step, 'The rate is too high'
    assert frame_step <= PARTIAL_FRAMES, 'The rate is too low'
    wav_slices, mel_slices = [], []
    steps = max(1, n_frames-PARTIAL_FRAMES+frame_step+1)
    for i in range(0, steps, frame_step):
        mel_range = np.array([i, i+PARTIAL_FRAMES])
        wav_range = mel_range*samples_per_frame
        mel_slices.append(slice(*mel_range))
        wav_slices.append(slice(*wav_range))
    last = wav_slices[-1]
    coverage = (n_samples-last.start)/(last.stop-last.start)
    if coverage < min_coverage and len(mel_slices) > 1:
        mel_slices = mel_slices[:-1]
        wav_slices = wav_slices[:-1]
    return wav_slices, mel_slices


class VoiceEncoder:
    """Drop-in for resemblyzer.VoiceEncoder.embed_utterance on CPU."""

    def __init__(self, weights=None, threads=1):
        from .optional import require
        ort = require('onnxruntime', 'Konuşmacı tanıma (ses izi)')
        self.weights = Path(weights).resolve(strict=True) if weights else ONNX_PATH.resolve(strict=True)
        if self.weights.suffix == '.pt':
            raise ValueError('Bu kurulum torch taşımıyor: .pt ağırlıkları önce scripts/convert-resemblyzer-onnx.py ile ONNX\'e çevrilmeli.')
        self.digest = file_digest(self.weights)
        self.model_id = model_id_for(self.digest)
        options = ort.SessionOptions()
        # One intra-op thread: the budget the torch path ran under (silero_vad's import set
        # torch.set_num_threads(1) and final_identity kept it), so identity never competes with a meeting.
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self.session = ort.InferenceSession(str(self.weights), sess_options=options, providers=['CPUExecutionProvider'])

    def partial_embeds(self, mels):
        return self.session.run(None, {'mels': np.ascontiguousarray(mels, dtype=np.float32)})[0]

    def embed_utterance(self, wav, rate=1.3, min_coverage=0.75):
        wav = np.asarray(wav, dtype=np.float32)
        wav_slices, mel_slices = partial_slices(len(wav), rate, min_coverage)
        max_wave_length = wav_slices[-1].stop
        if max_wave_length >= len(wav):
            wav = np.pad(wav, (0, max_wave_length-len(wav)), 'constant')
        mel = mel_spectrogram(wav)
        mels = np.array([mel[s] for s in mel_slices])
        partial = self.partial_embeds(mels)
        raw = np.mean(partial, axis=0)
        return raw/np.linalg.norm(raw, 2)
