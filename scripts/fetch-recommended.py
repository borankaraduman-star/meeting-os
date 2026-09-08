from pathlib import Path
import json
from meeting_os.models import fetch
root=Path(__file__).resolve().parents[1]
lock=json.loads((root/'docs/MODEL_LOCK.json').read_text())
for name in ('mlx-turbo','mlx-large','sherpa','analysis-qwen3'):
    print(fetch(name,root/'models',lock[name].get('revision','main')))
