"""One live chunk per isolated worker; the recorder never loads model weights."""
import argparse,json,sys,tempfile
from pathlib import Path
from .supervisor import run_guarded
from .types import Segment

class IsolatedLivePipeline:
    def __init__(self,args):
        self.options={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()}
        self.cancel_requested=lambda:False
    def process(self,path,source,offset,provisional):
        with tempfile.TemporaryDirectory(prefix='meeting-os-live-') as temp:
            root=Path(temp);request=root/'request.json';result=root/'result.json'
            request.write_text(json.dumps({'options':self.options,'path':str(path),'source':source,'offset':offset,'provisional':provisional}))
            run_guarded([sys.executable,'-m','meeting_os.live_worker',str(request),str(result)],timeout=120,isolated=True,handle_signals=False,cancel_requested=self.cancel_requested)
            data=json.loads(result.read_text())
            return [Segment(**row) for row in data['segments']],data['turns'],data['duration']

def main():
    data=json.loads(Path(sys.argv[1]).read_text())
    from .audio_probe import digital_silence_duration
    duration=digital_silence_duration(data['path'])
    if duration is not None:
        Path(sys.argv[2]).write_text(json.dumps({'segments':[], 'turns':[], 'duration':duration}))
        return
    from .cli import make_pipeline
    from .store import Store
    args=argparse.Namespace(**data['options']);args.vocabulary=Path(args.vocabulary)
    store=Store(args.db)
    try:
        pipeline=make_pipeline(args,store)
        rows,turns,duration=pipeline.process(data['path'],data['source'],data['offset'],data['provisional'])
        Path(sys.argv[2]).write_text(json.dumps({'segments':[r.to_dict() for r in rows],'turns':turns,'duration':duration}))
    finally:store.close()

if __name__=='__main__':main()
