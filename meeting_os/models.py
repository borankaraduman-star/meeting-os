"""The explicit, download-only network boundary."""
from pathlib import Path
import os
import json
CATALOG = {
    'analysis-qwen3': ('llm', 'mlx-community/Qwen3-4B-Instruct-2507-4bit'),
    'sherpa': ('onnx', 'k2-fsa/sherpa-onnx official releases'),
    'whisper-turbo': ('whisper', 'turbo'),
    'mlx-turbo': ('mlx', 'mlx-community/whisper-large-v3-turbo'),
    'mlx-large': ('mlx', 'mlx-community/whisper-large-v3-mlx'),
    'ecapa': ('ecapa', 'speechbrain/spkrec-ecapa-voxceleb'),
    'pyannote': ('pyannote', 'pyannote/speaker-diarization-community-1'),
    'cpp-turbo': ('cpp', 'ggerganov/whisper.cpp'),
    'cpp-large': ('cpp', 'ggerganov/whisper.cpp'),
}
def fetch(name, root, revision='main'):
    if name not in CATALOG: raise ValueError('Unknown model')
    target = Path(root).resolve()/name
    target.mkdir(parents=True,exist_ok=True)
    if name == 'sherpa':
        import urllib.request, hashlib, tarfile
        assets = ASSETS_SHERPA
        for item in assets:
            dest=target/item['file']
            if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest()!=item['sha256']:
                temporary=dest.with_suffix(dest.suffix+'.partial')
                urllib.request.urlretrieve(item['url'],temporary)
                if hashlib.sha256(temporary.read_bytes()).hexdigest()!=item['sha256']: raise ValueError('Model checksum mismatch')
                temporary.replace(dest)
        with tarfile.open(target/'segmentation.tar.bz2') as archive:
            archive.extractall(target,filter='data')
        metadata={'name':name,'engine':'onnx','assets':assets}
        path=target
    elif name == 'whisper-turbo':
        import whisper
        url = whisper._MODELS['turbo']
        path = whisper._download(url, str(target), False)
        metadata = {'name':name,'engine':'whisper','url':url,'sha256':url.split('/')[-2],'path':str(path)}
    else:
        os.environ['HF_HUB_OFFLINE'] = '0'
        from huggingface_hub import HfApi, snapshot_download, hf_hub_download
        engine, repo = CATALOG[name]
        sha = HfApi().model_info(repo, revision=revision).sha
        if engine == 'cpp':
            filename = 'ggml-large-v3-turbo-q5_0.bin' if name == 'cpp-turbo' else 'ggml-large-v3-q5_0.bin'
            path = hf_hub_download(repo, filename, revision=sha, local_dir=target)
        else:
            path = snapshot_download(repo, revision=sha, local_dir=target,
                ignore_patterns=['*.md','.gitattributes','*.png','*.jpg'])
        metadata = {'name':name,'engine':engine,'repo':repo,'revision':sha,'path':str(path)}
    (target/'meeting-os-model.json').write_text(json.dumps(metadata,indent=2))
    return str(path)

ASSETS_SHERPA = [{'file': 'segmentation.tar.bz2', 'url': 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2', 'sha256': '24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488'}, {'file': 'titanet-small.onnx', 'url': 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/nemo_en_titanet_small.onnx', 'sha256': 'ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e'}]
