"""Silero VAD (6.2.1) torch'suz: resmi ONNX modeli + `get_speech_timestamps`'ın numpy karşılığı.

`assets/silero_vad.onnx`, silero-vad 6.2.1 paketinin kendi `silero_vad/data/silero_vad.onnx` dosyasıdır (MIT;
`load_silero_vad(onnx=True)`'nun yüklediği dosya). Aşağıdaki `SileroVAD`, paketin `OnnxWrapper`'ının 16 kHz
dalı: 512 örneklik pencere, önceki pencerenin son 64 örneği bağlam olarak başa eklenir, durum [2,1,128]
pencereden pencereye taşınır. `get_speech_timestamps` paketin `utils_vad.get_speech_timestamps`'ının satır
satır karşılığıdır (16 kHz, return_seconds=False); `tests/test_onnx_equivalence.py` torch kuruluyken
zaman damgalarının JIT modelli torch yoluyla aynı olduğunu aynı ses ve parametrelerle denetler.
"""
from pathlib import Path

import numpy as np

ONNX_PATH = Path(__file__).resolve().parent/'assets'/'silero_vad.onnx'
ONNX_SHA256 = '1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3'
RATE = 16000
WINDOW = 512
CONTEXT = 64


class SileroVAD:
    def __init__(self, path=ONNX_PATH, threads=1):
        from .optional import require
        ort = require('onnxruntime', 'Konuşma algılama (VAD)')
        options = ort.SessionOptions()
        # silero_vad's own OnnxWrapper: one thread each, the same budget `import silero_vad` gave torch.
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self.session = ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
        self._sr = np.array(RATE, dtype=np.int64)
        self.reset_states()

    def reset_states(self):
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT), dtype=np.float32)

    def __call__(self, chunk):
        """Speech probability of one 512-sample window, as the float `model(chunk, 16000).item()` returns."""
        x = np.concatenate([self._context, np.asarray(chunk, dtype=np.float32).reshape(1, WINDOW)], axis=1)
        out, self._state = self.session.run(None, {'input': x, 'state': self._state, 'sr': self._sr})
        self._context = x[:, -CONTEXT:]
        return float(out[0, 0])


def get_speech_timestamps(audio, model, threshold=0.5, sampling_rate=RATE, min_speech_duration_ms=250,
                          max_speech_duration_s=float('inf'), min_silence_duration_ms=100, speech_pad_ms=30,
                          return_seconds=False, neg_threshold=None, min_silence_at_max_speech=98,
                          use_max_poss_sil_at_max_speech=True):
    if sampling_rate != RATE: raise ValueError('Konuşma algılama yalnız 16 kHz ses alır')
    if return_seconds: raise ValueError('return_seconds desteklenmiyor; örnek sayısı döner')
    audio = np.asarray(audio)
    if audio.ndim != 1: raise ValueError('Konuşma algılama tek kanallı ses ister')
    window_size_samples = WINDOW
    model.reset_states()
    min_speech_samples = sampling_rate*min_speech_duration_ms/1000
    speech_pad_samples = sampling_rate*speech_pad_ms/1000
    max_speech_samples = sampling_rate*max_speech_duration_s-window_size_samples-2*speech_pad_samples
    min_silence_samples = sampling_rate*min_silence_duration_ms/1000
    min_silence_samples_at_max_speech = sampling_rate*min_silence_at_max_speech/1000
    audio_length_samples = len(audio)

    speech_probs = []
    for current_start_sample in range(0, audio_length_samples, window_size_samples):
        chunk = np.asarray(audio[current_start_sample:current_start_sample+window_size_samples], dtype=np.float32)
        if len(chunk) < window_size_samples:
            chunk = np.pad(chunk, (0, int(window_size_samples-len(chunk))))
        speech_probs.append(model(chunk))

    triggered = False
    speeches = []
    current_speech = {}
    if neg_threshold is None:
        neg_threshold = max(threshold-0.15, 0.01)
    temp_end = 0
    prev_end = next_start = 0
    possible_ends = []

    for i, speech_prob in enumerate(speech_probs):
        cur_sample = window_size_samples*i
        if (speech_prob >= threshold) and temp_end:
            sil_dur = cur_sample-temp_end
            if sil_dur > min_silence_samples_at_max_speech:
                possible_ends.append((temp_end, sil_dur))
            temp_end = 0
            if next_start < prev_end:
                next_start = cur_sample
        if (speech_prob >= threshold) and not triggered:
            triggered = True
            current_speech['start'] = cur_sample
            continue
        if triggered and (cur_sample-current_speech['start'] > max_speech_samples):
            if use_max_poss_sil_at_max_speech and possible_ends:
                prev_end, dur = max(possible_ends, key=lambda x: x[1])
                current_speech['end'] = prev_end
                speeches.append(current_speech)
                current_speech = {}
                next_start = prev_end+dur
                if next_start < prev_end+cur_sample:
                    current_speech['start'] = next_start
                else:
                    triggered = False
                prev_end = next_start = temp_end = 0
                possible_ends = []
            else:
                if prev_end:
                    current_speech['end'] = prev_end
                    speeches.append(current_speech)
                    current_speech = {}
                    if next_start < prev_end:
                        triggered = False
                    else:
                        current_speech['start'] = next_start
                    prev_end = next_start = temp_end = 0
                    possible_ends = []
                else:
                    current_speech['end'] = cur_sample
                    speeches.append(current_speech)
                    current_speech = {}
                    prev_end = next_start = temp_end = 0
                    triggered = False
                    possible_ends = []
                    continue
        if (speech_prob < neg_threshold) and triggered:
            if not temp_end:
                temp_end = cur_sample
            sil_dur_now = cur_sample-temp_end
            if not use_max_poss_sil_at_max_speech and sil_dur_now > min_silence_samples_at_max_speech:
                prev_end = temp_end
            if sil_dur_now < min_silence_samples:
                continue
            else:
                current_speech['end'] = temp_end
                if (current_speech['end']-current_speech['start']) > min_speech_samples:
                    speeches.append(current_speech)
                current_speech = {}
                prev_end = next_start = temp_end = 0
                triggered = False
                possible_ends = []
                continue

    if current_speech and (audio_length_samples-current_speech['start']) > min_speech_samples:
        current_speech['end'] = audio_length_samples
        speeches.append(current_speech)

    for i, speech in enumerate(speeches):
        if i == 0:
            speech['start'] = int(max(0, speech['start']-speech_pad_samples))
        if i != len(speeches)-1:
            silence_duration = speeches[i+1]['start']-speech['end']
            if silence_duration < 2*speech_pad_samples:
                speech['end'] += int(silence_duration//2)
                speeches[i+1]['start'] = int(max(0, speeches[i+1]['start']-silence_duration//2))
            else:
                speech['end'] = int(min(audio_length_samples, speech['end']+speech_pad_samples))
                speeches[i+1]['start'] = int(max(0, speeches[i+1]['start']-speech_pad_samples))
        else:
            speech['end'] = int(min(audio_length_samples, speech['end']+speech_pad_samples))
    return speeches
