import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import sys
from .progress import emit

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path.home()/'Library/Application Support/MeetingOS'

def output(value): print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))

def inference_options(parser):
    parser.add_argument('--engine',choices=['auto','mlx','whisper','cpp'],default='auto')
    parser.add_argument('--model',help='Custom local model; specify --engine as well')
    parser.add_argument('--language',default='tr',help='tr or auto for multilingual detection')
    parser.add_argument('--vocabulary',type=Path,default=ROOT/'vocabulary.txt')
    parser.add_argument('--embedding',choices=['resemblyzer','ecapa'],default='resemblyzer')
    parser.add_argument('--embedding-model')
    parser.add_argument('--diarization',choices=['cluster','pyannote','sherpa'],default='sherpa')
    parser.add_argument('--diarization-model')
    parser.add_argument('--identity-threshold',type=float,default=.80)
    parser.add_argument('--identity-margin',type=float,default=.08)
    parser.add_argument('--cluster-threshold',type=float,default=.9)
    parser.add_argument('--cpp-bin',default=str(ROOT/'build/whisper-cpp/bin/whisper-cli') if (ROOT/'build/whisper-cpp/bin/whisper-cli').exists() else 'whisper-cli')

def resolve_inference(args):
    from .resources import low_memory_mac
    if args.engine == 'auto':
        if args.model: raise ValueError('Custom model requires explicit --engine mlx, cpp or whisper')
        args.engine='cpp' if low_memory_mac() else 'mlx'
    if not args.model:
        names={'mlx':'mlx-turbo','cpp':'cpp-turbo/ggml-large-v3-turbo-q5_0.bin','whisper':'whisper-turbo/turbo.pt'}
        args.model=str(ROOT/'models'/names[args.engine])


def make_pipeline(args,store):
    from .resources import check_pressure
    check_pressure()
    resolve_inference(args)
    emit("loading_models")
    from .backends import ASR
    from .speakers import Embedder,Diarizer
    from .pipeline import Pipeline
    vocabulary=[s.strip() for s in args.vocabulary.read_text().splitlines() if s.strip() and not s.startswith('#')] if args.vocabulary.exists() else []
    with contextlib.redirect_stdout(sys.stderr):
        asr=ASR(args.engine,args.model,args.language,vocabulary,args.cpp_bin)
        from .resources import low_memory_mac
        if low_memory_mac() and getattr(args,'command',None) in ('retry','record') and args.engine=='cpp' and args.diarization=='sherpa' and args.embedding=='resemblyzer':
            from .final_identity import FinalEmbedder
            emb=FinalEmbedder(args.embedding_model)
        else:emb=Embedder(args.embedding,args.embedding_model)
        diar=Diarizer(emb,args.diarization,args.diarization_model,args.cluster_threshold,
            isolate_sherpa=args.diarization=='sherpa' and low_memory_mac())
    missing=[p['name'] for p in store.profiles() if p['model'] != emb.model_id]
    if missing: print('Active embedding model has different profile versions: '+', '.join(sorted(set(missing))),file=sys.stderr)
    return Pipeline(asr,diar,store,args.identity_threshold,args.identity_margin)

def run_transcribe(args,store,paths=None):
    import time, resource
    started=time.monotonic()
    pipe=make_pipeline(args,store)
    paths=paths or {args.source:str(args.audio)}
    from .recovery import current_job_metadata
    mid=store.create_meeting(args.title,{**current_job_metadata(),'paths':paths,'engine':args.engine,'model':args.model,'diarization':args.diarization})
    all_turns=[]; duration=0
    try:
        for source,path in paths.items():
            with contextlib.redirect_stdout(sys.stderr): rows,turns,seconds=pipe.process(path,source)
            duration=max(duration,seconds); all_turns.extend(turns)
            for row in rows: store.add_segment(mid,row)
        store.status(mid,'complete')
        emit('complete')
    except BaseException:
        store.status(mid,'failed'); raise
    result={'meeting':mid,'segments':store.segments(mid),'turns':all_turns,'duration':duration,
            'elapsed_seconds':time.monotonic()-started,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss + resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            'memory_note':'RSS only; not total unified-memory footprint or an upper bound for Metal/compressed memory',
            'engine':args.engine,'model':args.model,'embedding_model':pipe.diarizer.embedder.model_id,'diarization':args.diarization}
    if args.output: args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return result

def run_retry(args,store):
    from .retry import RetryStore
    from .retry_capture import retry_capture
    from .recovery import current_job_metadata
    def process(work):
        from .audio import assemble_capture
        emit('assembling')
        paths=assemble_capture(work)
        pipe=make_pipeline(args,store)
        if getattr(getattr(pipe,'asr',None),'engine',None)=='cpp':
            from .asr_checkpoints import CheckpointASR
            pipe.asr=CheckpointASR(pipe.asr,store,args.meeting)
        if getattr(getattr(pipe,'diarizer',None),'isolate_sherpa',False):
            from .diarization_checkpoints import CheckpointDiarizer
            pipe.diarizer=CheckpointDiarizer(pipe.diarizer,store,args.meeting)
        for source,path in sorted(paths.items()):
            with contextlib.redirect_stdout(sys.stderr):rows,_,_=pipe.process(path,source,bounded_final=True)
            yield from rows
    retry=RetryStore(store)
    from .retry_workspaces import cleanup_workspaces
    cleanup_workspaces(retry,meeting=args.meeting)
    return retry_capture(retry,args.meeting,current_job_metadata()['worker_identity'],process)

def parser():
    p=argparse.ArgumentParser(description='Meeting OS V1 — local Turkish meetings and memory')
    p.add_argument('--db',type=Path,default=DATA_DIR/'meeting-os.sqlite')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    diagnostic=sub.add_parser('diagnostics'); diagnostic.add_argument('--output',type=Path); diagnostic.add_argument('--progress',type=Path)
    models=sub.add_parser('models'); m=models.add_subparsers(dest='action',required=True)
    m.add_parser('list'); f=m.add_parser('fetch'); f.add_argument('name'); f.add_argument('--root',type=Path,default=ROOT/'models'); f.add_argument('--revision',default='main')
    i=sub.add_parser('import'); i.add_argument('audio',type=Path); i.add_argument('--title',default='Imported meeting'); i.add_argument('--output',type=Path); inference_options(i)
    t=sub.add_parser('transcribe'); t.add_argument('audio',type=Path); t.add_argument('--source',choices=['mic','system'],default='system'); t.add_argument('--title',default='Imported meeting'); t.add_argument('--output',type=Path); inference_options(t)
    f=sub.add_parser('finalize'); f.add_argument('directory',type=Path); f.add_argument('--title',default='Final meeting'); f.add_argument('--output',type=Path); inference_options(f)
    r=sub.add_parser('record'); r.add_argument('directory',type=Path); r.add_argument('--output',type=Path); r.add_argument('--seconds',type=float,default=3600); r.add_argument('--chunk-seconds',type=float,default=12); r.add_argument('--live',action='store_true'); r.add_argument('--title',default='Live meeting'); r.add_argument('--capture-bin',default=str(ROOT/'build/MeetingCapture.app/Contents/MacOS/MeetingCapture')); inference_options(r)
    retry=sub.add_parser('retry'); retry.add_argument('meeting'); inference_options(retry)
    sub.add_parser('cleanup-retries')
    sub.add_parser('meetings')
    recovery=sub.add_parser('recovery'); recovery.add_argument('--mark-interrupted',metavar='MEETING'); recovery.add_argument('--audio',action='store_true',help='Inspect finalized capture headers without loading audio or models')
    s=sub.add_parser('show'); s.add_argument('meeting'); s.add_argument('--json',action='store_true')
    c=sub.add_parser('label'); c.add_argument('meeting'); c.add_argument('speaker'); c.add_argument('name')
    c=sub.add_parser('label-segment'); c.add_argument('meeting'); c.add_argument('segment',type=int); c.add_argument('name')
    e=sub.add_parser('enroll'); e.add_argument('meeting'); e.add_argument('segment',type=int); e.add_argument('name'); e.add_argument('--confirmed-clean',action='store_true',required=True,help='Confirm listening to the segment: one speaker, no overlap/echo, >=3s speech')
    profiles=sub.add_parser('profiles'); profiles.add_argument('--delete')
    b=sub.add_parser('benchmark'); b.add_argument('manifest',type=Path); b.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('openrouter-import'); a.add_argument('audio',type=Path,nargs='?'); a.add_argument('--title',default='OpenRouter toplantısı'); a.add_argument('--resume'); a.add_argument('--model'); a.add_argument('--allow-upload',action='store_true'); a.add_argument('--no-local',action='store_true',help='Cloud-only: provider diarization, no local models'); a.add_argument('--output',type=Path)
    a=sub.add_parser('openrouter-finalize',help='Transcribe a finished recording through OpenRouter only; no local models'); a.add_argument('meeting'); a.add_argument('--model'); a.add_argument('--allow-upload',action='store_true'); a.add_argument('--output',type=Path)
    a=sub.add_parser('analyze'); a.add_argument('meeting'); a.add_argument('--force',action='store_true'); a.add_argument('--output',type=Path)
    a=sub.add_parser('actions'); a.add_argument('--owner'); a.add_argument('--meeting')
    a=sub.add_parser('action-update'); a.add_argument('task'); a.add_argument('--state',choices=['open','in_progress','done','dismissed']); a.add_argument('--title'); a.add_argument('--owner'); a.add_argument('--due-text')
    a=sub.add_parser('prepare'); a.add_argument('task'); a.add_argument('--force',action='store_true'); a.add_argument('--output',type=Path)
    a=sub.add_parser('handoff'); a.add_argument('task'); a.add_argument('path',type=Path)
    a=sub.add_parser('search'); a.add_argument('query'); a.add_argument('--speaker')
    a=sub.add_parser('ask'); a.add_argument('question'); a.add_argument('--output',type=Path)
    sub.add_parser('mcp')
    return p

def main(supervised=False):
    args=parser().parse_args()
    os.umask(0o077)
    try:
        if not supervised and args.command in ('import','transcribe','finalize','retry','analyze','prepare','ask','openrouter-import'):
            from .supervisor import run_guarded
            def interrupted(pid):
                from .store import Store
                db=Store(args.db)
                try:
                    from .recovery import mark_interrupted,metadata
                    for row in db.meetings():
                        if metadata(row).get('worker_pid')==pid:mark_interrupted(db,row['id'])
                finally:db.close()
            run_guarded([sys.executable,'-c','from meeting_os.cli import main; main(supervised=True)',*sys.argv[1:]],timeout=14400,isolated=True,passthrough=True,on_failure=interrupted)
            return
        if args.command=='models':
            from .models import CATALOG,fetch
            output(CATALOG if args.action=='list' else {'path':fetch(args.name,args.root,args.revision)})
            return
        if args.command=='diagnostics':
            from .diagnostics import collect,export_report
            report=collect(args.output.parent if args.output else ROOT,args.progress)
            if args.output:
                export_report(args.output,report);output({'diagnostics_saved':True})
            else:output(report)
            return
        if args.command=='doctor':
            import platform, importlib.util
            output({'python':sys.version.split()[0],'machine':platform.machine(),'macos':platform.mac_ver()[0],
                'capture_binary':(ROOT/'build/MeetingCapture.app/Contents/MacOS/MeetingCapture').exists(),
                'ffmpeg':shutil.which('ffmpeg'),'whisper_cpp':str(ROOT/'build/whisper-cpp/bin/whisper-cli') if (ROOT/'build/whisper-cpp/bin/whisper-cli').exists() else shutil.which('whisper-cli'),
                'offline':os.environ['HF_HUB_OFFLINE'],
                'packages':{name:importlib.util.find_spec(name) is not None for name in ['mlx_whisper','resemblyzer','silero_vad','sherpa_onnx','speechbrain','pyannote','whisper','mlx_lm','outlines']},
                'models':[str(x) for x in (ROOT/'models').glob('*/meeting-os-model.json')],
                'permissions':'Run record to request macOS microphone and screen/system-audio access. Never bypassed.'})
            return
        if args.command=='benchmark':
            from .benchmark import benchmark
            output(benchmark(args.manifest,args.output)); return
        from .store import Store
        store=Store(args.db)
        try:
            if args.command in ('analyze','prepare','ask','handoff','actions','action-update','search','mcp'):
                from . import assistant
                from .memory import Memory
                if args.command=='analyze':result=assistant.analyze(store,args.meeting,force=args.force)
                elif args.command=='prepare':result=assistant.prepare(store,args.task,force=args.force)
                elif args.command=='ask':result=assistant.ask(store,args.question)
                elif args.command=='handoff':result=assistant.handoff(store,args.task,args.path)
                elif args.command=='actions':result=Memory(store).actions(args.owner,args.meeting)
                elif args.command=='action-update':result=Memory(store).update_action(args.task,{k:getattr(args,k) for k in ('state','title','owner','due_text') if getattr(args,k) is not None})
                elif args.command=='search':result=Memory(store).search(args.query,speaker=args.speaker)
                else:
                    from .mcp import serve
                    serve(store);return
                if getattr(args,'output',None):args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
                output(result)
            elif args.command=='openrouter-import':
                if not args.resume and args.audio is None:raise ValueError('Ses dosyası seçin')
                if args.no_local or args.resume and json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(args.resume,)).fetchone()[0] if store.db.execute('SELECT 1 FROM meetings WHERE id=?',(args.resume,)).fetchone() else '{}').get('cloud_mode'):
                    from .cloud_finalize import finalize_capture,import_file_cloud_only
                    result=finalize_capture(store,args.resume,DATA_DIR,consent=args.allow_upload,model=args.model) if args.resume else import_file_cloud_only(store,args.audio,args.title,DATA_DIR,consent=args.allow_upload,model=args.model)
                else:
                    from .cloud_import import import_file
                    result=import_file(store,args.audio,args.title,DATA_DIR,consent=args.allow_upload,resume=args.resume,model=args.model)
                if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False))
                output(result)
            elif args.command=='openrouter-finalize':
                from .cloud_finalize import finalize_capture
                result=finalize_capture(store,args.meeting,DATA_DIR,consent=args.allow_upload,model=args.model)
                if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False))
                output(result)
            elif args.command=='import':
                import subprocess, uuid
                if not args.audio.is_file(): raise ValueError('Audio file not found')
                dest=DATA_DIR/'imports'/uuid.uuid4().hex
                dest.mkdir(parents=True,mode=0o700)
                target=dest/'audio.wav'
                ffmpeg=shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
                converted=subprocess.run([ffmpeg,'-nostdin','-v','error','-i',str(args.audio.resolve()),'-vn','-ar','16000','-ac','1',str(target)],capture_output=True,text=True)
                if converted.returncode: raise ValueError('Audio conversion failed: '+converted.stderr[-1500:])
                output(run_transcribe(args,store,{'system':str(target)}))
            elif args.command=='transcribe': output(run_transcribe(args,store))
            elif args.command=='finalize':
                from .audio import assemble_capture
                emit("assembling")
                output(run_transcribe(args,store,assemble_capture(args.directory)))
            elif args.command=='record':
                from .live import record
                from .live_worker import IsolatedLivePipeline
                factory=(lambda: IsolatedLivePipeline(args)) if args.live else None
                record(args.capture_bin,args.directory,args.seconds,args.chunk_seconds,None,store,args.title,pipeline_factory=factory,result_path=args.output)
            elif args.command=='cleanup-retries':
                from .retry import RetryStore
                from .retry_workspaces import cleanup_workspaces
                output(cleanup_workspaces(RetryStore(store)))
            elif args.command=='retry': output(run_retry(args,store))
            elif args.command=='meetings': output(store.meetings())
            elif args.command=='recovery':
                from .recovery import list_recovery,mark_interrupted
                if args.mark_interrupted:output({'marked_interrupted':mark_interrupted(store,args.mark_interrupted)})
                else:output(list_recovery(store,include_audio=args.audio))
            elif args.command=='show':
                rows=store.segments(args.meeting)
                if args.json: output(rows)
                else:
                    for r in rows: print(f"#{r['id']} {r['start']:.2f}–{r['end']:.2f} {r['speaker_name'] or r['speaker']}: {r['text']} [{', '.join(r['flags'])}]")
            elif args.command=='label': store.correct(args.meeting,args.speaker,args.name); output({'label_saved':True,'profile_trained':False})
            elif args.command=='label-segment': store.correct_segment(args.meeting,args.segment,args.name); output({'label_saved':True,'profile_trained':False})
            elif args.command=='enroll':
                rows=[r for r in store.segments(args.meeting) if r['id']==args.segment]
                if not rows: raise ValueError('Segment not found')
                r=rows[0]
                forbidden={'speaker_ambiguous','possible_non_speech','repetition','provisional','low_asr_confidence','short_context_diarization'}
                if not r['embedding'] or forbidden.intersection(r['flags']): raise ValueError('Segment is not suitable for voice enrollment; choose clean final speech')
                store.enroll(args.name,r['embedding'],r['embedding_model'],r['end']-r['start'],f'{args.meeting}:{r["id"]}')
                output({'profile_saved':args.name})
            elif args.command=='profiles':
                if args.delete: store.delete_profile(args.delete)
                output(store.profiles())
        finally: store.close()
    except (Exception,KeyboardInterrupt) as exc:
        from .supervisor import ChildFailure, JobMemoryLimitError
        from .resources import MemoryPressureError, ResourceProbeError
        if isinstance(exc,(MemoryPressureError,ResourceProbeError,JobMemoryLimitError)):
            print(f'Meeting OS: {exc}',file=sys.stderr); raise SystemExit(75)
        if isinstance(exc,ChildFailure):raise SystemExit(exc.code if exc.code>0 else 1)
        print(f'Meeting OS: {exc}',file=sys.stderr); raise SystemExit(1)
