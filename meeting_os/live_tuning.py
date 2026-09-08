"""Expiring recording-scoped CPU experiment. No GPU/model/quality changes."""
import json,time,math
from pathlib import Path

def cpp_threads(data, path=None):
    path=Path(path) if path is not None else Path(__file__).resolve().parents[1]/'build/live-tuning.json'
    try:
        if path.stat().st_size>4096:return 2
        config=json.loads(path.read_text())
        expires=config['expires_at'];threads=config['cpp_threads']
        if not isinstance(expires,(int,float)) or not math.isfinite(expires):return 2
        if not 0<expires-time.time()<=900:return 2
        if type(threads) is not int or threads not in (2,4):return 2
        if Path(config['capture_dir']).resolve()!=Path(data['path']).resolve().parent:return 2
        return threads
    except (OSError,ValueError,TypeError,KeyError):return 2
