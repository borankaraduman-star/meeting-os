"""Guarded, local-only snapshot-copy experiment; never runs models or edits DB.
F_NOCACHE is per descriptor on macOS (SDK sys/fcntl.h), not a global setting.
Run once with --mode normal or uncached. Resource failure stops the probe;
there is no automatic retry. Temporary destination belongs to the controller.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def worker(args):
 import fcntl
 from meeting_os.retry_capture import _transfer,MAX_COPY_BYTES
 from meeting_os.recovery_audio import MAX_CHUNK_BYTES,MAX_JOURNAL_BYTES
 from meeting_os.resources import check_pressure
 import meeting_os.retry_capture as capture
 root=args.capture.resolve(strict=True);journal=root/'capture-native.jsonl'
 if not journal.exists():journal=root/'events.jsonl'
 with journal.open('rb') as f:raw=f.read(MAX_JOURNAL_BYTES+1)
 if len(raw)>MAX_JOURNAL_BYTES:raise ValueError('Journal size limit')
 names=[]
 for line in raw.splitlines():
  e=json.loads(line)
  if e.get('event')=='chunk':
   p=Path(e['path'])
   if p.resolve().parent!=root:raise ValueError('Unexpected source path')
   if p.name not in names:names.append(p.name)
 if not 0<len(names)<=10000:raise ValueError('Invalid source count')
 original=capture._regular_fd
 def open_source(name,directory):
  fd=original(name,directory)
  if args.mode=='uncached':
   try:fcntl.fcntl(fd,48,1)
   except BaseException:os.close(fd);raise
  return fd
 capture._regular_fd=open_source
 root_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);copied=0;start=time.monotonic()
 try:
  for i,name in enumerate(names):
   check_pressure();target=args.destination/f'{i:06d}.wav'
   if shutil.disk_usage(args.destination).free<(root/name).stat().st_size+1024**3:raise OSError('Insufficient probe disk reserve')
   with target.open('xb') as out:
    if args.mode=='uncached':fcntl.fcntl(out.fileno(),48,1)
    signature,digest=_transfer(root_fd,name,min(MAX_CHUNK_BYTES,MAX_COPY_BYTES-copied),lambda:None,out)
    out.flush();os.fsync(out.fileno())
   copied+=signature[2]
   h=hashlib.sha256()
   with target.open('rb') as copied_file:
    if args.mode=='uncached':fcntl.fcntl(copied_file.fileno(),48,1)
    while block:=copied_file.read(65536):h.update(block)
   if h.hexdigest()!=digest:raise ValueError('Snapshot hash mismatch')
   args.output.write_text(json.dumps({'mode':args.mode,'completed_chunks':i+1,'total_chunks':len(names),'copied_bytes':copied,'elapsed_seconds':time.monotonic()-start,'all_completed_hashes_match':True,'complete':i+1==len(names)}))
 finally:os.close(root_fd)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['normal','uncached'],required=True);p.add_argument('--destination',type=Path);args=p.parse_args()
 if args.destination:worker(args);return
 if sys.platform!='darwin':raise SystemExit('macOS only')
 from meeting_os.supervisor import run_guarded
 from meeting_os.resources import check_pressure
 check_pressure()
 listing=subprocess.check_output(['ps','-axo','comm=,args='],text=True)
 for line in listing.splitlines():
  if line.split() and line.split()[0].endswith('/MeetingCapture'):raise SystemExit('Active capture; deferred')
  if ('Python' in line or 'python' in line) and any(marker in line for marker in ('-m meeting_os record ','-m meeting_os retry ','-m meeting_os finalize ','-m meeting_os.live_worker ')):raise SystemExit('Active audio job; deferred')
 with tempfile.TemporaryDirectory(prefix='meeting-os-cache-probe-') as d:
  command=[sys.executable,str(Path(__file__).resolve()),'--capture',str(args.capture),'--output',str(args.output),'--mode',args.mode,'--destination',d]
  try:result=run_guarded(command,timeout=180,isolated=True,passthrough=True)
  except Exception as exc:
   print(json.dumps({'failure_type':type(exc).__name__,'temporary_destination_removed_on_exit':True}),flush=True);raise
  print(json.dumps(result),flush=True)
if __name__=='__main__':main()
