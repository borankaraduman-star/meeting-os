#!/usr/bin/env python3
"""Matched local serial/batch benchmark. Refuses active recording/inference."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def competing_job():
    listing=subprocess.check_output(['ps','-axo','command='],text=True,timeout=3,start_new_session=True)
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

def compare_attention(asr,clips):
    original=asr.flash_attention;results=[]
    try:
        for flash in (True,False,False,True):
            asr.flash_attention=flash;started=time.monotonic()
            rows=[asr.transcribe(clip) for clip in clips]
            results.append(('flash' if flash else 'non_flash',time.monotonic()-started,rows))
    finally:asr.flash_attention=original
    return {'runs':[{'mode':mode,'seconds':elapsed} for mode,elapsed,_ in results],
            'exact_output_match':all(rows==results[0][2] for _,_,rows in results),
            'reference_outputs_distinct':len({json.dumps(x,sort_keys=True) for x in results[0][2]})==len(clips),
            'clips':len(clips),'audio_seconds':sum(len(x) for x in clips)/16000,
            'quality_limit':'Output equality is not WER/DER validation against human reference.'}

def normalized_words(text):
    import re
    return re.findall(r"\w+",text.replace("İ","i").replace("I","ı").lower())

def word_error(reference,hypothesis):
    previous=list(range(len(hypothesis)+1))
    for i,word in enumerate(reference,1):
        current=[i]
        for j,other in enumerate(hypothesis,1):
            current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(word!=other)))
        previous=current
    return previous[-1]/len(reference) if reference else None

def compare_window(asr,clips,references=None):
    """Benchmark only: preserve 200ms gaps; never alter the live pipeline."""
    import numpy as np,math
    if not 2<=len(clips)<=4:raise ValueError('Provide 2–4 clips')
    gap=np.zeros(3200,dtype=np.float32);parts=[];starts=[];cursor=0
    for clip in clips:
        if clip.ndim!=1 or not len(clip) or not np.isfinite(clip).all():raise ValueError('Expected nonempty finite mono 16kHz PCM from read_audio')
        if parts:parts.append(gap);cursor+=len(gap)
        starts.append(cursor/16000);parts.append(clip);cursor+=len(clip)
    if cursor>12*16000:raise ValueError('Window plus gaps must not exceed 12 seconds')
    if references is not None and len(references)!=len(clips):raise ValueError('Reference count mismatch')
    window=np.concatenate(parts);reference=normalized_words(' '.join(references)) if references is not None else None
    runs=[];texts=[]
    for mode in ('serial','window','window','serial'):
        started=time.monotonic()
        groups=[(0,asr.transcribe(window))] if mode=='window' else [(offset,asr.transcribe(clip)) for offset,clip in zip(starts,clips)]
        elapsed=time.monotonic()-started
        words=normalized_words(' '.join(row['text'] for _,rows in groups for row in rows));texts.append(words)
        invalid=0;timed=0;in_gap=0
        for offset,rows in groups:
            for row in rows:
                for word in row.get('words',[]):
                    timed+=1
                    try:a=float(word['start'])+offset;b=float(word['end'])+offset
                    except (KeyError,TypeError,ValueError):invalid+=1;continue
                    if not (math.isfinite(a) and math.isfinite(b) and 0<=a<b<=cursor/16000):invalid+=1;continue
                    mid=(a+b)/2
                    if not any(start<=mid<=start+len(clip)/16000 for start,clip in zip(starts,clips)):in_gap+=1
        runs.append({'mode':mode,'seconds':elapsed,'wer':word_error(reference,words) if reference is not None else None,
                     'timed_words':timed,'word_time_bounds_violations':invalid,'words_in_inserted_gaps':in_gap})
    return {'runs':runs,'normalized_text_match':all(t==texts[0] for t in texts),
            'clips':len(clips),'audio_seconds':sum(len(c) for c in clips)/16000,'window_seconds':cursor/16000,
            'quality_limit':'Synthetic script WER only when supplied; timing bounds/gap checks are not aligned-reference timestamp accuracy or speaker DER.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio',type=Path,nargs='+');parser.add_argument('--model',type=Path,default=ROOT/'models/cpp-turbo/ggml-large-v3-turbo-q5_0.bin')
    parser.add_argument('--comparison',choices=['batch','attention','window'],default='batch')
    parser.add_argument('--reference-manifest',type=Path,help='Optional fixture scripts for window WER; all clips must match')
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
    if args.comparison=='window':
        references=None
        if args.reference_manifest:
            manifest=json.loads(args.reference_manifest.read_text())
            scripts={(args.reference_manifest.parent/c['audio']).resolve():c['script'] for c in manifest['cases']}
            references=[scripts[p.resolve()] for p in args.audio]
        report=compare_window(asr,clips,references)
    else:report=(compare_attention if args.comparison=='attention' else compare)(asr,clips)
    report["binary_sha256"]=hashlib.sha256(Path(asr.cpp_bin).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temp=args.output.with_name(args.output.name+f'.{os.getpid()}.tmp');temp.write_text(json.dumps(report,indent=2));temp.replace(args.output)
    print(json.dumps(report))

if __name__=='__main__':main()
