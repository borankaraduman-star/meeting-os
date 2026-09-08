"""Whisper adapters. All inference consumes previously downloaded local models."""
from pathlib import Path
import json
import subprocess
import tempfile
import soundfile as sf
from .audio import RATE

class ASR:
    def __init__(self, engine='mlx', model=None, language='tr', vocabulary=(), cpp_bin='whisper-cli'):
        self.engine, self.language, self.cpp_bin = engine, language, cpp_bin
        self.prompt = ', '.join(vocabulary)[:1000]
        self.model = str(Path(model).expanduser().resolve()) if model else None
        if not self.model or not Path(self.model).exists():
            raise ValueError('A local model path is required. Run models fetch first.')
        self.loaded = None
        if engine == 'whisper':
            import whisper
            self.loaded = whisper.load_model(self.model, device='cpu')
    def transcribe(self, audio):
        options = dict(language=None if self.language == 'auto' else self.language,
            task='transcribe', initial_prompt=self.prompt or None, word_timestamps=True,
            condition_on_previous_text=False, temperature=0.0)
        if self.engine == 'mlx':
            import mlx_whisper
            return mlx_whisper.transcribe(audio, path_or_hf_repo=self.model, **options)['segments']
        if self.engine == 'whisper':
            return self.loaded.transcribe(audio, fp16=False, **options)['segments']
        if self.engine != 'cpp': raise ValueError('Unknown ASR engine')
        with tempfile.TemporaryDirectory(prefix='meeting-os-') as tmp:
            wav = Path(tmp)/'input.wav'; prefix = Path(tmp)/'result'
            sf.write(wav, audio, RATE, subtype='PCM_16')
            command = [self.cpp_bin, '-m', self.model, '-f', str(wav), '-l', self.language,
                       '-ojf', '-of', str(prefix), '-np', '--prompt', self.prompt]
            run = subprocess.run(command, capture_output=True, text=True, timeout=600)
            if run.returncode: raise RuntimeError('whisper.cpp failed: '+run.stderr[-2000:])
            data = json.loads(prefix.with_suffix('.json').read_text())
            return [{'start':s['offsets']['from']/1000, 'end':s['offsets']['to']/1000,
                     'text':s['text'], 'words':[], 'confidence_unavailable':True}
                    for s in data['transcription']]
