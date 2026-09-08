"""Expiring recording-scoped CPU experiment. No GPU/model/quality changes."""
import json,time,math
from pathlib import Path

def _config(data, path=None):
    path=Path(path) if path is not None else Path(__file__).resolve().parents[1]/'build/live-tuning.json'
    try:
        if path.stat().st_size>4096:return {}
        config=json.loads(path.read_text())
        expires=config['expires_at'];threads=config['cpp_threads']
        if not isinstance(expires,(int,float)) or not math.isfinite(expires):return {}
        if not 0<expires-time.time()<=900:return {}
        if type(threads) is not int or threads not in (2,4):return {}
        if Path(config['capture_dir']).resolve()!=Path(data['path']).resolve().parent:return {}
        return config
    except (OSError,ValueError,TypeError,KeyError,RuntimeError):return {}

def cpp_threads(data,path=None):
    return _config(data,path).get("cpp_threads",2)

def batch_regions(data,path=None):
    config=_config(data,path)
    return config.get("batch_regions") is True and not config.get("no_flash_attention") and not config.get("cpp_gpu")

def no_flash_attention(data,path=None):
    config=_config(data,path)
    return config.get("no_flash_attention") is True and not config.get("batch_regions") and config.get("cpp_threads")==2 and not config.get("cpp_gpu")

def cpp_gpu(data,path=None):
    # Failed the live memory-pressure trial on this16GiB Mac. No live opt-in.
    # GPU comparisons must use the separate supervised idle benchmark.
    return False


def revision(data,path=None):
    import hashlib
    target=Path(path) if path is not None else Path(__file__).resolve().parents[1]/'build/live-tuning.json'
    if not _config(data,target):return None
    try:
        with target.open('rb') as f:raw=f.read(4097)
        return hashlib.sha256(raw).hexdigest() if len(raw)<=4096 else None
    except OSError:return None


def disable_trial(data,path=None):
    """Best-effort rollback of the same recording/profile revision on failure."""
    target=Path(path) if path is not None else Path(__file__).resolve().parents[1]/'build/live-tuning.json'
    expected=data.get('_tuning_revision')
    if expected is None or revision(data,target)!=expected:return False
    try:target.unlink();return True
    except OSError:return False
