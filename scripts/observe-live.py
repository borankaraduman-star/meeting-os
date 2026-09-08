#!/usr/bin/env python3
"""Read-only bounded live snapshot; no capture/inference, transcript or embeddings."""
import argparse,json,sqlite3,time
from pathlib import Path
import numpy as np
import soundfile as sf

def observe(db_path):
    with sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute("SELECT id,status,metadata FROM meetings WHERE status IN ('processing','provisional') ORDER BY created DESC LIMIT 1").fetchone()
        if row is None:return {'active_candidate':False}
        mid,status,raw=row;metadata=json.loads(raw)
        directory=metadata.get('capture_dir')
        if not directory:return {'active_candidate':False,'status':status}
        root=Path(directory);journal=root/'capture-native.jsonl'
        latest={};state='unknown'
        if journal.exists():
            with journal.open('rb') as f:
                f.seek(max(0,journal.stat().st_size-65536));tail=f.read().decode(errors='replace')
            for line in tail.splitlines():
                try:e=json.loads(line)
                except json.JSONDecodeError:continue
                if e.get('event')=='chunk':latest[e['source']]=e;state='capturing'
                elif e.get('event') in ('stopped','error'):state=e['event']
        sources={}
        for source,e in latest.items():
            path=Path(e['path'])
            if source not in ('mic','system') or path.resolve().parent!=root.resolve():continue
            sample={'captured_until':e['start']+e['duration']}
            if 0<path.stat().st_size<=16*1024*1024:
                with sf.SoundFile(path) as f:
                    if f.frames<=f.samplerate*15 and f.channels<=8:
                        audio=f.read(dtype='float64',always_2d=True)
                        if audio.size:
                            sample.update(rms=float(np.sqrt(np.mean(audio*audio))),peak=float(np.max(np.abs(audio))),digital_silence=bool(np.all(audio==0)))
            timing=root/f'live-{source}-timing.json'
            if timing.exists():sample['last_worker']=json.loads(timing.read_text())
            sources[source]=sample
        result=db.execute('SELECT MAX(end),COUNT(*) FROM segments WHERE meeting=?',(mid,)).fetchone()
        return {'observed_at':time.time(),'meeting':mid,'persisted_status':status,'native_state':state,'sources':sources,'transcript_until':result[0],'segments':result[1], 'unprocessed_span_seconds':max(0,max((x['captured_until'] for x in sources.values()),default=0)-(result[0] or 0))}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,default=Path.home()/'Library/Application Support/MeetingOS/meeting-os.sqlite');args=p.parse_args()
    print(json.dumps(observe(args.db),indent=2,allow_nan=False))
