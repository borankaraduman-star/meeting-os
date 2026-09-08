"""Package tracked source only; exclude runtime, models and private meeting data."""
import hashlib,json,subprocess,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
files=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0');files=[f for f in files if f and (root/f).is_file()]
for f in files:
 if f.endswith(('.sqlite','.sqlite-wal','.sqlite-shm')) or f.startswith(('models/','.venv/','data/','benchmarks/private/')):raise ValueError('Private/runtime path unexpectedly tracked: '+f)
version=json.loads(subprocess.check_output([str(root/'.venv/bin/python'),'-c','import json,meeting_os;print(json.dumps(meeting_os.__version__))'],cwd=root))
archive=root/'build'/f'MeetingOS-source-v{version}.zip';archive.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for f in files:z.write(root/f,'MeetingOS/'+f)
with zipfile.ZipFile(archive) as z:
 if z.testzip() is not None:raise ValueError('Archive integrity check failed')
report={'source_archive':archive.name,'files':len(files),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'archive_integrity':'passed'}
(root/'build/DELIVERY.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
