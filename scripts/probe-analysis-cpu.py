"""Qualify pinned candidate tooling without loading a model or opening sockets."""
import argparse,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meeting_os.schemas import analysis_schema
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument('--runtime',type=Path,required=True)
p.add_argument('--converter',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
lock=json.loads((root/'docs/candidates/analysis-cpu-qwen4b.json').read_text())
if hashlib.sha256(a.converter.read_bytes()).hexdigest()!=lock['converter']['sha256']:
    raise ValueError('Pinned converter checksum mismatch')
def run(command):
    return subprocess.run([str(x) for x in command],capture_output=True,text=True,check=True,timeout=30)
completion=a.runtime/'llama-completion';tokenize=a.runtime/'llama-tokenize'
help_text=run([completion,'--help']).stdout
if not help_text:help_text=run([completion,'--help']).stderr
required=['--json-schema-file','--system-prompt-file','--file','--no-display-prompt','--single-turn','--gpu-layers','--threads','--batch-size','--ubatch-size','--seed','--temp','--offline']
missing=[flag for flag in required if flag not in help_text]
if missing:raise ValueError('Required completion capabilities missing: '+str(missing))
t=run([tokenize,'--help']);token_help=t.stdout+t.stderr
if not all(flag in token_help for flag in ('--stdin','--show-count','--offline')):
    raise ValueError('Private token-count path unavailable')
version=run([completion,'--version']);version_text=(version.stdout+version.stderr).strip()
if '10853' not in version_text or '9dcf84e5a' not in version_text:
    raise ValueError('Unexpected runtime revision')
with tempfile.TemporaryDirectory(prefix='meeting-os-schema-') as temp:
    schema=Path(temp)/'analysis.json';schema.write_text(json.dumps(analysis_schema([1,2,3])))
    converted=run([sys.executable,a.converter,schema])
    if 'root ::=' not in converted.stdout or not converted.stdout.strip():
        raise ValueError('Analysis schema did not convert to grammar')
    report={'version':version_text,'completion_flags':required,'token_count_flags':['--stdin','--show-count','--offline'],
        'analysis_schema_conversion':'passed','grammar_sha256':hashlib.sha256(converted.stdout.encode()).hexdigest(),
        'model_loaded':False,'inference_quality':'not evaluated','limitation':'Conversion only; generated output compliance still requires actual model tests.'}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
