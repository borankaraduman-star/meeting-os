from pathlib import Path
import json
from meeting_os.models import fetch
from meeting_os.resources import low_memory_mac
root=Path(__file__).resolve().parents[1]
lock=json.loads((root/'docs/MODEL_LOCK.json').read_text())
for name in ('cpp-turbo' if low_memory_mac() else 'mlx-turbo','sherpa','analysis-qwen3'):
    print(fetch(name,root/'models',lock[name].get('revision','main')))
