"""Local embeddings and conservative clustering; no automatic profile training."""
import hashlib
from pathlib import Path
import numpy as np
from .audio import RATE, speech_regions
from .store import unit, cosine

class Embedder:
    def __init__(self, engine='resemblyzer', model=None):
        self.engine = engine
        if engine == 'resemblyzer':
            from resemblyzer import VoiceEncoder
            import resemblyzer
            weights = Path(model) if model else Path(resemblyzer.__file__).parent/'pretrained.pt'
            self.encoder = VoiceEncoder(device='cpu', weights_fpath=weights)
            self.model_id = 'resemblyzer:'+hashlib.sha256(weights.read_bytes()).hexdigest()[:16]
        elif engine == 'ecapa':
            if not model or not Path(model).is_dir(): raise ValueError('ECAPA requires a local model directory')
            from speechbrain.inference.speaker import EncoderClassifier
            self.encoder = EncoderClassifier.from_hparams(source=str(Path(model).resolve()), savedir=str(Path(model).resolve()), overrides={'pretrained_path':str(Path(model).resolve())}, run_opts={'device':'cpu'})
            self.model_id = 'ecapa:'+hashlib.sha256((Path(model)/'embedding_model.ckpt').read_bytes()).hexdigest()[:16]
        else: raise ValueError('Unknown embedding engine')
    def embed(self, audio):
        if len(audio) < RATE: return None
        if self.engine == 'resemblyzer':
            vector = self.encoder.embed_utterance(audio)
        else:
            import torch
            with torch.inference_mode():
                vector = self.encoder.encode_batch(torch.from_numpy(audio).unsqueeze(0)).squeeze().numpy()
        return unit(vector.tolist())

class Clusterer:
    def __init__(self, threshold=0.75):
        self.threshold = threshold
        self.centroids = []
    def assign(self, vector):
        if vector is None: return 'unknown'
        scores = [cosine(vector, c) for c in self.centroids]
        if scores and max(scores) >= self.threshold:
            # Keep exemplars fixed: avoid chain drift from short/noisy turns.
            return f'S{int(np.argmax(scores))}'
        self.centroids.append(vector)
        return f'S{len(self.centroids)-1}'

class Diarizer:
    def __init__(self, embedder, mode='cluster', model=None, threshold=0.75, isolate_sherpa=False):
        self.embedder, self.mode = embedder, mode
        self.clusters = {}
        self.threshold = threshold
        self.isolate_sherpa = isolate_sherpa
        self.pipeline = None
        if mode == 'sherpa':
            import sherpa_onnx as sherpa
            root = Path(model) if model else Path(__file__).resolve().parents[1]/'models/sherpa'
            self.sherpa_root = root.resolve()
            cfg = sherpa.OfflineSpeakerDiarizationConfig(
                segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
                    pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(root/'sherpa-onnx-pyannote-segmentation-3-0/model.onnx')), num_threads=2),
                embedding=sherpa.SpeakerEmbeddingExtractorConfig(model=str(root/'titanet-small.onnx'), num_threads=2),
                clustering=sherpa.FastClusteringConfig(num_clusters=-1, threshold=threshold),
                min_duration_on=.3, min_duration_off=.5)
            if not cfg.validate(): raise ValueError('Sherpa local models are missing or invalid')
            self.sherpa_config = cfg
        if mode == 'pyannote':
            if not model or not Path(model).exists(): raise ValueError('pyannote requires an explicitly downloaded local pipeline')
            from pyannote.audio import Pipeline
            self.pipeline = Pipeline.from_pretrained(str(Path(model).resolve()))
    def turns(self, audio, source):
        if self.mode == 'sherpa' and self.isolate_sherpa:
            from .isolated_diarization import isolated_turns
            return isolated_turns(audio,source,self.sherpa_root,self.threshold)
        if self.mode == 'sherpa':
            import sherpa_onnx as sherpa
            # Fresh clustering for each finalized recording; IDs are recording-local.
            output = sherpa.OfflineSpeakerDiarization(self.sherpa_config).process(audio.astype(np.float32)).sort_by_start_time()
            duration = len(audio)/RATE
            return [(max(0,float(t.start)), min(duration,float(t.end)), f'{source}:S{t.speaker}')
                    for t in output if min(duration,float(t.end)) > max(0,float(t.start))]
        if self.mode == 'pyannote':
            import torch
            output = self.pipeline({'waveform':torch.from_numpy(audio).unsqueeze(0), 'sample_rate':RATE})
            annotation = getattr(output, 'speaker_diarization', output)
            return [(turn.start, turn.end, f'{source}:{speaker}') for turn, _, speaker in annotation.itertracks(yield_label=True)]
        cluster = self.clusters.setdefault(source, Clusterer(self.threshold))
        turns = []
        for start,end in speech_regions(audio):
            # 2.5s windows detect within-VAD speaker changes; this is a baseline,
            # cannot recover overlapping voices. Final pyannote is recommended.
            for a in range(start,end,int(2.5*RATE)):
                b = min(a+int(2.5*RATE),end)
                # A short tail borrows preceding context for its embedding,
                # without adding duplicated time to the diarization output.
                context_start = max(start, min(a, b-int(2.5*RATE)))
                vector = self.embedder.embed(audio[context_start:b])
                label = f'{source}:{cluster.assign(vector)}'
                if turns and turns[-1][2] == label and abs(turns[-1][1]-a/RATE) < 0.05:
                    turns[-1] = (turns[-1][0], b/RATE, label)
                else: turns.append((a/RATE,b/RATE,label))
        return turns

def overlap(a,b,c,d): return max(0.0, min(b,d)-max(a,c))

def speaker_at(start,end,turns):
    scores = {}
    for a,b,s in turns: scores[s] = scores.get(s,0)+overlap(start,end,a,b)
    ranked = sorted(scores.items(),key=lambda p:p[1],reverse=True)
    if not ranked or ranked[0][1] <= 0: return 'unknown', False
    ambiguous = len(ranked)>1 and ranked[1][1] > 0.25*(end-start)
    return ranked[0][0], ambiguous
