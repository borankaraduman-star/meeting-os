#!/usr/bin/env python3
"""Matched local serial/batch benchmark. Refuses active recording/inference."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def competing_job():
    listing=subprocess.check_output(['ps','-axo','command='],text=True,timeout=3)
    return any(any(marker in line for marker in ('-m meeting_os record ', '-m meeting_os finalize ', '-m meeting_os retry ', '-m meeting_os import ', '-m meeting_os analyze ', '-m meeting_os.live_worker ')) for line in listing.splitlines())

def compare(asr,clips):
    """ABBA order reduces warm-cache bias; outputs remain separate clip-local rows."""
    results=[]
    for mode in ('serial','batch','batch','serial'):
        started=time.monotonic()
        rows=[asr.transcribe(clip) for clip in clips] if mode=='serial' else asr.transcribe_batch(clips)
        results.append((mode,time.monotonic()-started,rows))
    return {'runs':[{'mode':mode,'seconds':elapsed} for mode,elapsed,_ in results],
            'exact_output_match':all(rows==results[0][2] for _,_,rows in results),
            'reference_outputs_distinct':len({json.dumps(x,sort_keys=True) for x in results[0][2]})==len(clips),
            'clips':len(clips),'audio_seconds':sum(len(x) for x in clips)/16000,
            'quality_limit':'Output equality is not WER/DER validation against human reference.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio',type=Path,nargs='+');parser.add_argument('--model',type=Path,default=ROOT/'models/cpp-turbo/ggml-large-v3-turbo-q5_0.bin')
    parser.add_argument('--vocabulary',type=Path,default=ROOT/'vocabulary.txt')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if competing_job():raise SystemExit('Active Meeting OS audio job: benchmark deferred; no model loaded.')
    from meeting_os.resources import check_pressure
    check_pressure()
    if not args.worker:
        from meeting_os.supervisor import run_guarded
        run_guarded([sys.executable,str(Path(__file__).resolve()),*sys.argv[1:],'--worker'],timeout=180,isolated=True,passthrough=True,cancel_requested=competing_job)
        return
    import soundfile as sf
    if not 2<=len(args.audio)<=4:raise ValueError('Provide 2–4 separate speech clips')
    for path in args.audio:
        if path.stat().st_size>16*1024*1024:raise ValueError('Clip file too large')
        info=sf.info(path)
        if not 0<info.duration<=12 or info.channels>8:raise ValueError('Clips must be nonempty and at most 12 seconds')
    from meeting_os.audio import read_audio
    from meeting_os.backends import ASR
    clips=[read_audio(path) for path in args.audio]
    if sum(len(x) for x in clips)>16000*12:raise ValueError('Total test audio must not exceed 12 seconds')
    vocabulary=[s.strip() for s in args.vocabulary.read_text().splitlines() if s.strip() and not s.startswith('#')] if args.vocabulary.exists() else []
    asr=ASR('cpp',args.model,language='tr',vocabulary=vocabulary,cpp_bin=str(ROOT/'build/whisper-cpp/bin/whisper-cli'))
    report=compare(asr,clips)
    report["binary_sha256"]=hashlib.sha256(Path(asr.cpp_bin).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temp=args.output.with_name(args.output.name+f'.{os.getpid()}.tmp');temp.write_text(json.dumps(report,indent=2));temp.replace(args.output)
    print(json.dumps(report))

if __name__=='__main__':main()
