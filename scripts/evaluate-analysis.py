import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meeting_os.evaluation import score_analysis
p=argparse.ArgumentParser();p.add_argument('analysis',type=Path);p.add_argument('reference',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
result=score_analysis(json.loads(args.analysis.read_text()),json.loads(args.reference.read_text()));args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
