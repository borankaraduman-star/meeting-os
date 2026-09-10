import contextlib
import json
import os
from pathlib import Path
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

def which(name):
    """shutil costs a tenth of a second to import and only the doctor and the audio converter need it."""
    import shutil
    return shutil.which(name)

def parser():
    import argparse   # the bridge imports this module for DATA_DIR and never builds a command line
    p=argparse.ArgumentParser(description='Meeting OS V1 — local Turkish meetings and memory')
    p.add_argument('--db',type=Path,default=DATA_DIR/'meeting-os.sqlite')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    pr=sub.add_parser('probe',help='Self-test: can this Mac record, transcribe and keep its data'); pr.add_argument('--network',action='store_true'); pr.add_argument('--json',action='store_true')
    diagnostic=sub.add_parser('diagnostics'); diagnostic.add_argument('--output',type=Path); diagnostic.add_argument('--progress',type=Path)
    models=sub.add_parser('models'); m=models.add_subparsers(dest='action',required=True)
    m.add_parser('list'); f=m.add_parser('fetch'); f.add_argument('name'); f.add_argument('--root',type=Path,default=ROOT/'models'); f.add_argument('--revision',default='main')
    i=sub.add_parser('import'); i.add_argument('audio',type=Path); i.add_argument('--title',default=os.environ.get('MEETING_OS_TITLE') or 'Imported meeting'); i.add_argument('--output',type=Path); inference_options(i)
    t=sub.add_parser('transcribe'); t.add_argument('audio',type=Path); t.add_argument('--source',choices=['mic','system'],default='system'); t.add_argument('--title',default=os.environ.get('MEETING_OS_TITLE') or 'Imported meeting'); t.add_argument('--output',type=Path); inference_options(t)
    f=sub.add_parser('finalize'); f.add_argument('directory',type=Path); f.add_argument('--title',default=os.environ.get('MEETING_OS_TITLE') or 'Final meeting'); f.add_argument('--output',type=Path); inference_options(f)
    r=sub.add_parser('record'); r.add_argument('directory',type=Path); r.add_argument('--output',type=Path); r.add_argument('--seconds',type=float,default=3600); r.add_argument('--chunk-seconds',type=float,default=12); r.add_argument('--live',action='store_true'); r.add_argument('--cloud',action='store_true',help='Bu kayıt buluta gönderilmek üzere alındı; yalnızca niyeti işaretler, hiçbir şey yüklemez'); r.add_argument('--title',default=os.environ.get('MEETING_OS_TITLE') or 'Live meeting'); r.add_argument('--capture-bin',default=str(ROOT/'build/MeetingCapture.app/Contents/MacOS/MeetingCapture')); inference_options(r)
    retry=sub.add_parser('retry'); retry.add_argument('meeting'); inference_options(retry)
    sub.add_parser('cleanup-retries')
    sub.add_parser('meetings')
    recovery=sub.add_parser('recovery'); recovery.add_argument('--mark-interrupted',metavar='MEETING'); recovery.add_argument('--audio',action='store_true',help='Inspect finalized capture headers without loading audio or models')
    s=sub.add_parser('show'); s.add_argument('meeting'); s.add_argument('--json',action='store_true')
    c=sub.add_parser('label'); c.add_argument('meeting'); c.add_argument('speaker'); c.add_argument('name')
    c=sub.add_parser('label-segment'); c.add_argument('meeting'); c.add_argument('segment',type=int); c.add_argument('name')
    e=sub.add_parser('enroll'); e.add_argument('meeting'); e.add_argument('segment',type=int); e.add_argument('name'); e.add_argument('--confirmed-clean',action='store_true',required=True,help='Confirm listening to the segment: one speaker, no overlap/echo, >=6s speech (the app asks for 6; the store accepts 3)')
    profiles=sub.add_parser('profiles'); profiles.add_argument('--delete')
    b=sub.add_parser('benchmark'); b.add_argument('manifest',type=Path); b.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('openrouter-import'); a.add_argument('audio',type=Path,nargs='?',default=os.environ.get('MEETING_OS_AUDIO_PATH')); a.add_argument('--title',default=os.environ.get('MEETING_OS_TITLE') or 'OpenRouter toplantısı'); a.add_argument('--resume'); a.add_argument('--model'); a.add_argument('--allow-upload',action='store_true'); a.add_argument('--no-local',action='store_true',help='Cloud-only: provider diarization, no local models'); a.add_argument('--output',type=Path)
    a=sub.add_parser('openrouter-finalize',help='Transcribe a finished recording through OpenRouter only; no local models'); a.add_argument('meeting'); a.add_argument('--model'); a.add_argument('--allow-upload',action='store_true'); a.add_argument('--output',type=Path)
    a=sub.add_parser('analyze'); a.add_argument('meeting'); a.add_argument('--force',action='store_true'); a.add_argument('--output',type=Path); a.add_argument('--openrouter-model',help='Cloud analysis via OpenRouter; no local model is loaded')
    a=sub.add_parser('actions'); a.add_argument('--owner'); a.add_argument('--meeting')
    a=sub.add_parser('action-update'); a.add_argument('task'); a.add_argument('--state',choices=['open','in_progress','done','dismissed']); a.add_argument('--title'); a.add_argument('--owner'); a.add_argument('--due-text')
    a=sub.add_parser('prepare'); a.add_argument('task'); a.add_argument('--force',action='store_true'); a.add_argument('--output',type=Path); a.add_argument('--openrouter-model')
    a=sub.add_parser('handoff'); a.add_argument('task'); a.add_argument('path',type=Path)
    a=sub.add_parser('search'); a.add_argument('query'); a.add_argument('--speaker')
    # The app passes the question in the environment: a question typed into the sidebar can start with '-' or
    # carry a newline, and argv is visible to every process on the Mac.
    a=sub.add_parser('ask'); a.add_argument('question',nargs='?',default=os.environ.get('MEETING_OS_QUESTION')); a.add_argument('--output',type=Path); a.add_argument('--openrouter-model')
    q=sub.add_parser('quality',help='Personal quality set from your corrections'); q.add_argument('action',choices=['report','compare','replay']); q.add_argument('--model',action='append',default=[]); q.add_argument('--limit',type=int,default=20); q.add_argument('--allow-upload',action='store_true'); q.add_argument('--identity',action='store_true',help='replay: voice matching only'); q.add_argument('--text',action='store_true',help='replay: text corrections only'); q.add_argument('--json',action='store_true',help='replay: print the full result, not the summary')
    g=sub.add_parser('agenda',help='Draft the next meeting agenda from recent meetings'); g.add_argument('--limit',type=int,default=5); g.add_argument('--output',type=Path)
    dg=sub.add_parser('digest',help='End-of-day digest, or a stakeholder report over a date range with --from/--to'); dg.add_argument('--day',help='YYYY-MM-DD (local day; default today)'); dg.add_argument('--from',dest='date_from',help='YYYY-MM-DD (period start)'); dg.add_argument('--to',dest='date_to',help='YYYY-MM-DD (period end)'); dg.add_argument('--mask-names',action='store_true'); dg.add_argument('--owner',help='Öntanımlı: ayarlardaki adınız'); dg.add_argument('--output',type=Path)
    wt=sub.add_parser('waiting',help='Beklediklerim: open tasks owned by other people, per person, with a reminder draft'); wt.add_argument('--owner',help='Öntanımlı: ayarlardaki adınız'); wt.add_argument('--output',type=Path)
    dl=sub.add_parser('decisions',help='Decision log across every meeting, newest first, with earlier similar decisions'); dl.add_argument('--query'); dl.add_argument('--limit',type=int,default=200); dl.add_argument('--mask-names',action='store_true'); dl.add_argument('--output',type=Path)
    qr=sub.add_parser('questions',help='Soru radarı: tekrar eden açık sorular, en çok toplantıda sorulan üstte'); qr.add_argument('--query'); qr.add_argument('--limit',type=int,default=100); qr.add_argument('--mask-names',action='store_true'); qr.add_argument('--output',type=Path)
    sc=sub.add_parser('scorecard',help='Toplantı karnesi: süre, konuşma payı, karar/görev sayısı, maliyet ve dönem toplamı'); sc.add_argument('--from',dest='date_from',help='YYYY-MM-DD (dönem başı; öntanımlı son 7 gün)'); sc.add_argument('--to',dest='date_to',help='YYYY-MM-DD (dönem sonu)')
    rd=sub.add_parser('review-debt',help='Review queue of every meeting recorded in the last N days, worst first'); rd.add_argument('--days',type=int,default=7)
    sh=sub.add_parser('share',help='Share preview of one meeting as Markdown; names can be masked, decisions-only mode'); sh.add_argument('--meeting',required=True); sh.add_argument('--mask-names',action='store_true'); sh.add_argument('--only-decisions',action='store_true'); sh.add_argument('--no-transcript',action='store_true'); sh.add_argument('--no-summary',action='store_true'); sh.add_argument('--include-segments',help='Comma-separated segment ids'); sh.add_argument('--exclude-segments',help='Comma-separated segment ids'); sh.add_argument('--output',type=Path)
    gl=sub.add_parser('glossary',help='Project glossary (glossary.jsonl): import, show, suggest corrections'); gl.add_argument('action',choices=['import','show','suggest','hint']); gl.add_argument('path',type=Path,nargs='?'); gl.add_argument('--meeting'); gl.add_argument('--openrouter-model'); gl.add_argument('--apply',action='store_true',help='Apply LLM-accepted suggestions immediately (text edits are recorded and reversible)')
    wd=sub.add_parser('words',help='Öğretilen kelimeler: bir kez düzelt, benzer yazımlar da düzelsin'); wd.add_argument('action',choices=['teach','forget','list']); wd.add_argument('original',nargs='?'); wd.add_argument('replacement',nargs='?'); wd.add_argument('--meeting')
    rp=sub.add_parser('reports',help='Shared diagnostic reports between Macs'); rp.add_argument('action',choices=['summarize','write','settings','heartbeat']); rp.add_argument('--meeting'); rp.add_argument('--set',action='append',default=[],help='key=value: share_reports, share_text, auto_update, report_dir, user_name, team_dir, team_url, share_glossary, share_words, share_profiles, audio_retention_days')
    tm=sub.add_parser('team',help='Ekip bulutu: ortak bilgi tabanının durumu, elle eşitleme, davet bağlantısı, başka bir ekibe katılma'); tm.add_argument('action',choices=['status','sync','invite','join']); tm.add_argument('token',nargs='?',help='join: davet bağlantısı, davet dosyasının yolu ya da 32–128 onaltılık karakterlik ekip belirteci'); tm.add_argument('--with-key',action='store_true',help='invite: OpenRouter anahtarını da davete koyar (ekip arkadaşı anahtar girmez)')
    up=sub.add_parser('update',help='Check or start the one-click updater'); up.add_argument('action',choices=['check','start','status'])
    er=sub.add_parser('errors',help='Bu Mac’in yerel hata günlüğü: hatalar ve çökmeler'); er.add_argument('action',choices=['list','clear']); er.add_argument('--limit',type=int,default=20)
    dc=sub.add_parser('document',help='Meeting → PRD / bug report / customer request / Claude Code prompt'); dc.add_argument('--meeting',required=True); dc.add_argument('--kind',choices=['prd','bug','customer','claude'],default='prd'); dc.add_argument('--output',type=Path); dc.add_argument('--openrouter-model',default='openai/gpt-4.1-mini')
    sub.add_parser('mcp')
    return p

def main(supervised=False):
    if os.environ.get('MEETING_OS_LOW_PRIORITY'):   # a Zoom meeting is on screen: never compete with it
        with contextlib.suppress(OSError): os.nice(10)
    args=parser().parse_args()
    os.umask(0o077)
    try:
        cloud_llm=getattr(args,'openrouter_model',None) or args.command in ('glossary','reports','update','document','digest','share')
        if not supervised and args.command in ('import','transcribe','finalize','retry','analyze','prepare','ask','openrouter-import') and not cloud_llm:
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
            report=collect(args.output.parent if args.output else ROOT,args.progress,Path(args.db).parent)
            if args.output:
                export_report(args.output,report);output({'diagnostics_saved':True})
            else:output(report)
            return
        if args.command=='probe':
            from .probe import main as probe_main
            raise SystemExit(probe_main(['--network'] if args.network else []) if not args.json else probe_main(['--json']+(['--network'] if args.network else [])))
        if args.command=='doctor':
            import platform, importlib.util
            from .probe import signing_partition_item
            signing=signing_partition_item(ROOT)
            # stderr, so `doctor` keeps printing one parseable JSON document on stdout.
            if not signing['ok']: print(signing['detail'],file=sys.stderr)
            output({'python':sys.version.split()[0],'machine':platform.machine(),'macos':platform.mac_ver()[0],
                'signing_partition':signing['ok'],
                'capture_binary':(ROOT/'build/MeetingCapture.app/Contents/MacOS/MeetingCapture').exists(),
                'ffmpeg':which('ffmpeg'),'whisper_cpp':str(ROOT/'build/whisper-cpp/bin/whisper-cli') if (ROOT/'build/whisper-cpp/bin/whisper-cli').exists() else which('whisper-cli'),
                'offline':os.environ['HF_HUB_OFFLINE'],
                'packages':{name:importlib.util.find_spec(name) is not None for name in ['mlx_whisper','resemblyzer','silero_vad','sherpa_onnx','speechbrain','pyannote','whisper','mlx_lm','outlines']},
                'models':[str(x) for x in (ROOT/'models').glob('*/meeting-os-model.json')],
                'permissions':'Run record to request macOS microphone and screen/system-audio access. Never bypassed.'})
            return
        if args.command=='benchmark':
            from .benchmark import benchmark
            output(benchmark(args.manifest,args.output)); return
        if args.command=='team':
            # No database: the team cloud is files in the data folder, and `join` has to work on a Mac that has
            # never recorded anything.
            from . import team_cloud as TC
            from .reports import load_settings
            base=Path(args.db).parent
            if args.action=='status': output(TC.status(base,load_settings(base)))
            elif args.action=='sync': output(TC.sync(base))
            elif args.action=='invite':
                payload=TC.invite_payload(base,include_key=args.with_key)
                if payload.get('error'): output(payload)
                else: output({**TC.invite_line(base),'url':TC.invite_url(base,include_key=args.with_key),
                              'file':TC.invite_file_text(base,include_key=args.with_key),'with_key':'key' in payload})
            else:
                # A link, a saved invite file, or a bare token: whatever the person was sent. The app never needs
                # this — it is the "Gelişmiş" way in — so it has to accept all three without asking which is which.
                if not args.token: raise ValueError('meeting_os team join <davet bağlantısı | davet dosyası | belirteç>')
                text=args.token
                try:
                    path=Path(text).expanduser()
                    if path.is_file(): text=path.read_text(encoding='utf-8')
                except (OSError, ValueError): pass
                result=TC.accept_invite(base,text)
                if result.get('error'): raise ValueError(result['error'])
                output({**result,**TC.status(base)})
            return
        from .store import Store
        store=Store(args.db)
        try:
            if args.command in ('analyze','prepare','ask','handoff','actions','action-update','search','mcp'):
                from . import assistant
                from .memory import Memory
                llm=None
                if cloud_llm:
                    from .openrouter import OpenRouterClient,validate_analysis_model
                    llm=OpenRouterClient().analysis(validate_analysis_model(cloud_llm),consent=True)
                if args.command=='analyze':result=assistant.analyze(store,args.meeting,llm=llm,force=args.force)
                elif args.command=='prepare':result=assistant.prepare(store,args.task,llm=llm,force=args.force)
                elif args.command=='ask':
                    if not (args.question or '').strip():raise ValueError('Soru boş olamaz')
                    result=assistant.ask(store,args.question,llm=llm)
                elif args.command=='handoff':result=assistant.handoff(store,args.task,args.path)
                elif args.command=='actions':result=Memory(store).actions(args.owner,args.meeting)
                elif args.command=='action-update':result=Memory(store).update_action(args.task,{k:getattr(args,k) for k in ('state','title','owner','due_text') if getattr(args,k) is not None})
                elif args.command=='search':result=Memory(store).search(args.query,speaker=args.speaker)
                else:
                    from .mcp import serve
                    serve(store);return
                if getattr(args,'output',None):args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
                if os.environ.get('MEETING_OS_PROGRESS_PATH') and args.command in ('analyze','ask','prepare','search'):
                    # Launched by the app: stdout lands in last-job.log, which the teammate guide asks people to send along.
                    # Print a receipt, never the analysis text, quotes or answers.
                    counts={k:len(v) for k,v in ((result or {}).get('payload') or {}).items() if isinstance(v,list)} if isinstance(result,dict) else {}
                    output({'command':args.command,'meeting':getattr(args,'meeting',None),'counts':counts,'ok':True})
                else: output(result)
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
                from .correction_memory import apply_rules   # learned and taught fixes land before the summary reads the text
                try: result['auto_corrections']=apply_rules(store,args.meeting,data_dir=DATA_DIR)
                except Exception as exc: result['auto_corrections']={'error':str(exc)}
                if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False))
                output(result)
            elif args.command=='import':
                import subprocess, uuid
                if not args.audio.is_file(): raise ValueError('Audio file not found')
                dest=DATA_DIR/'imports'/uuid.uuid4().hex
                dest.mkdir(parents=True,mode=0o700)
                target=dest/'audio.wav'
                ffmpeg=which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
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
                record(args.capture_bin,args.directory,args.seconds,args.chunk_seconds,None,store,args.title,pipeline_factory=factory,result_path=args.output,data_dir=DATA_DIR,cloud=args.cloud)
            elif args.command=='cleanup-retries':
                from .retry import RetryStore
                from .retry_workspaces import cleanup_workspaces
                output(cleanup_workspaces(RetryStore(store)))
            elif args.command=='retry': output(run_retry(args,store))
            elif args.command=='reports':
                from . import reports
                if args.action=='summarize':
                    summary=reports.summarize(reports.report_root(reports.load_settings(DATA_DIR)))
                    for a in summary.get('alerts') or []: print(('✘ ' if a['level']=='error' else '! ' if a['level']=='warning' else '· ')+a['line'],file=sys.stderr)
                    for host,h in sorted((summary.get('hosts') or {}).items()):
                        journal=(h.get('heartbeat') or {}).get('error_journal')
                        journal=journal if isinstance(journal,dict) else {}
                        counts=journal.get('last_24h') if isinstance(journal.get('last_24h'),dict) else {}
                        if not counts and not journal.get('crashes_24h'): continue
                        kinds=', '.join(f'{k} {v}' for k,v in sorted(counts.items()))
                        last=next((e.get('message') for e in (journal.get('last') or []) if isinstance(e,dict) and e.get('message')),'')
                        print(f'  {host} · hata günlüğü (24s): {kinds or "yok"} · çökme {journal.get("crashes_24h") or 0}'+(f' · en son: {last}' if last else ''),file=sys.stderr)
                    output(summary)
                elif args.action=='heartbeat':
                    from . import __version__
                    output({'path':reports.write_heartbeat(store,DATA_DIR,app={'version':__version__,'commit':None})})
                elif args.action=='settings':
                    changes={}
                    for kv in args.set:
                        k,_,v=kv.partition('=')
                        if k in ('report_dir','user_name','team_dir','team_url'): changes[k]=v   # free text; save_settings validates it
                        elif k=='audio_retention_days': changes[k]=int(v) if v.strip().isdigit() else v
                        else: changes[k]=v.lower() in ('1','true','evet','on')
                    if not changes: output(reports.load_settings(DATA_DIR))
                    else: output(reports.save_settings_with_rename(store,DATA_DIR,changes))
                else:
                    if not args.meeting: raise ValueError('--meeting gerekli')
                    from . import __version__
                    output({'path':reports.write_meeting_report(store,args.meeting,DATA_DIR,version=__version__)})
            elif args.command=='errors':
                from . import errors as E
                base=Path(args.db).parent
                if args.action=='clear': output({'cleared':E.clear(base)})
                else:
                    E.sweep(base)   # crash reports and the updater's last verdict before the list is printed
                    output({'errors':E.entries(base,limit=args.limit)[::-1],'summary':E.summary(base)})
            elif args.command=='update':
                from . import updater
                output(updater.check(ROOT) if args.action=='check' else (updater.start(ROOT,DATA_DIR) if args.action=='start' else updater.status(DATA_DIR)))
            elif args.command=='glossary':
                # The glossary is read from the folder --db points at, not the real data folder: `glossary.load`
                # seeds vocabulary.txt on first read, and with DATA_DIR a test run wrote into the user's own data.
                from . import glossary as G
                if args.action=='import':
                    if not args.path: raise ValueError('glossary.jsonl yolu gerekli')
                    output(G.import_file(args.path,DATA_DIR,shared=True))
                elif args.action=='show': output({'count':len(G.load(args.db.parent,ROOT)),'entries':G.load(args.db.parent,ROOT)[:50]})
                elif args.action=='hint': output({'hint':G.stt_hint(G.load(args.db.parent,ROOT))})
                else:
                    if not args.meeting: raise ValueError('--meeting gerekli')
                    llm=None
                    if args.openrouter_model:
                        from .openrouter import OpenRouterClient,validate_analysis_model
                        llm=OpenRouterClient().analysis(validate_analysis_model(args.openrouter_model),consent=True)
                    entries=G.load(args.db.parent,ROOT);suggestions=G.suggest_for_meeting(store,args.meeting,entries,llm)
                    applied=0
                    if args.apply and llm is not None:
                        for sg in list(suggestions):
                            try: G.apply_suggestion(store,args.meeting,sg['segment_id'],sg['original'],sg['replacement']);applied+=1
                            except ValueError: pass
                    output({'suggestions':suggestions,'applied':applied})
            elif args.command=='words':
                from . import correction_memory as CM
                if args.action=='list': output({'rules':CM.word_rules(store)})
                elif args.action=='teach':
                    if not (args.meeting and args.original and args.replacement): raise ValueError('words teach --meeting <toplantı> <yanlış> <doğru>')
                    output(CM.teach(store,args.meeting,args.original,args.replacement,DATA_DIR))
                else:
                    if not args.original: raise ValueError('words forget <kelime>')
                    output(CM.forget(store,args.original,DATA_DIR))
            elif args.command=='document':
                from .documents import build_document
                from .openrouter import OpenRouterClient,validate_analysis_model
                from .glossary import load as load_glossary, analysis_context
                llm=OpenRouterClient().analysis(validate_analysis_model(args.openrouter_model),consent=True)
                doc=build_document(store,args.meeting,args.kind,llm,glossary=analysis_context(load_glossary(args.db.parent,ROOT)))
                if args.output: args.output.write_text(doc['text'],encoding='utf-8');output({'path':str(args.output),'sections':doc['sections'],'sources':doc['sources']})
                else: print(doc['text'])
            elif args.command=='agenda':
                from .agenda import build_agenda,render_agenda
                text=render_agenda(build_agenda(store,args.limit))
                if args.output: args.output.write_text(text,encoding='utf-8');output({'path':str(args.output)})
                else: print(text)
            elif args.command=='digest':
                from .digest import build_digest,render_digest
                from . import glossary as G
                from .reports import settings_owner
                digest=build_digest(store,args.day,args.owner or settings_owner(args.db.parent),start=args.date_from,end=args.date_to,mask_names=args.mask_names,glossary=G.load(args.db.parent,ROOT) if args.mask_names else None)
                text=render_digest(digest)
                if args.output: args.output.write_text(text,encoding='utf-8');output({'path':str(args.output),'day':digest['day'],'from':digest['from'],'to':digest['to'],'masked_names':digest['masked_names'],'tasks':len(digest['tasks']),'questions':len(digest['questions']),'decisions':len(digest['decisions']),'risks':len(digest['risks']),'meetings':len(digest['meetings'])})
                else: print(text)
            elif args.command=='waiting':
                from .waiting import build_waiting,render_waiting
                from .reports import settings_owner
                board=build_waiting(store,args.owner or settings_owner(args.db.parent))
                if args.output: args.output.write_text(render_waiting(board),encoding='utf-8');output({'path':str(args.output),'people':len(board['people']),'total':board['total']})
                else: output(board)
            elif args.command=='decisions':
                from .decisions import decision_log,export_decision_log
                from . import glossary as G
                if args.output: output(export_decision_log(store,args.output,query=args.query,limit=args.limit,mask_names=args.mask_names,glossary=G.load(args.db.parent,ROOT) if args.mask_names else None))
                else: output(decision_log(store,args.query,args.limit))
            elif args.command=='questions':
                from .questions import question_radar,export_question_radar
                from . import glossary as G
                if args.output: output(export_question_radar(store,args.output,query=args.query,limit=args.limit,mask_names=args.mask_names,glossary=G.load(args.db.parent,ROOT) if args.mask_names else None))
                else: output(question_radar(store,args.query,args.limit))
            elif args.command=='scorecard':
                from .scorecard import build_scorecard
                output(build_scorecard(store,start=args.date_from,end=args.date_to))
            elif args.command=='review-debt':
                from .review import review_debt
                output(review_debt(store,args.days,DATA_DIR))
            elif args.command=='share':
                from .share import prepare_share
                from . import glossary as G
                ids=lambda s:[int(x) for x in s.split(',') if x.strip()] if s else None
                kinds=[k for k,off in (('transcript',args.no_transcript),('summary',args.no_summary)) if not off]
                result=prepare_share(store,args.meeting,include_segments=ids(args.include_segments),exclude_segments=ids(args.exclude_segments),mask_names=args.mask_names,only_decisions=args.only_decisions,kinds=kinds,glossary=G.load(args.db.parent,ROOT))
                if args.output: args.output.write_text(result['text'],encoding='utf-8');output({'path':str(args.output),'masked_names':result['masked_names'],'segments':result['segments']})
                else: print(result['text'])
            elif args.command=='quality':
                from . import quality
                if args.action=='report': output(quality.report(store))
                elif args.action=='replay':
                    summary,full=quality.replay(store,args.db.parent,identity=args.identity or not args.text,text=args.text or not args.identity)
                    output(full if args.json else summary)
                else:
                    from .openrouter import OpenRouterClient
                    from . import glossary as G
                    entries=G.load(args.db.parent,ROOT)
                    output(quality.compare(store,args.model or ['microsoft/mai-transcribe-2'],OpenRouterClient(max_audio_bytes=24*1024*1024),consent=args.allow_upload,limit=args.limit,hint=G.stt_hint(entries) if entries else None))
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
        # A job that dies here leaves a line in last-job.log the next job overwrites. The journal keeps it.
        # A user cancel is not a fault, and a ChildFailure was already recorded by the child that raised it.
        if not isinstance(exc,(KeyboardInterrupt,ChildFailure)):
            try:
                from .errors import record
                record('job',f'{type(exc).__name__}: {exc}',data_dir=Path(args.db).parent,
                       context={'command':getattr(args,'command',None),'supervised':bool(supervised)})
            except Exception: pass
        if isinstance(exc,(MemoryPressureError,ResourceProbeError,JobMemoryLimitError)):
            print(f'Meeting OS: {exc}',file=sys.stderr); raise SystemExit(75)
        if isinstance(exc,ChildFailure):raise SystemExit(exc.code if exc.code>0 else 1)
        print(f'Meeting OS: {exc}',file=sys.stderr); raise SystemExit(1)
