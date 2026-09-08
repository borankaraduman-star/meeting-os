"""Explicit experiment: retry one meeting with per-fd uncached snapshot transfers.
Optional --uncached-assembly also bypasses cache for private assembly WAV I/O.
Does not change production defaults. A successful retry DOES finalize the given
meeting through the normal atomic path. Original sources are never modified.
"""
import argparse,fcntl,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def install_uncached_transfers():
 import meeting_os.retry_capture as capture
 original_open=capture._regular_fd;original_transfer=capture._transfer
 counts={'source_fds':0,'destination_fds':0}
 flag=getattr(fcntl,'F_NOCACHE',48)
 def counted(kind):
  counts[kind]+=1
  if counts[kind]==1:
   try:print(json.dumps({'uncached_transfer_applied':kind}),file=sys.stderr,flush=True)
   except OSError:pass
 def open_source(name,directory):
  fd=original_open(name,directory)
  try:fcntl.fcntl(fd,flag,1)  # F_NOCACHE, macOS SDK sys/fcntl.h
  except BaseException:os.close(fd);raise
  counted('source_fds');return fd
 def transfer(directory,name,limit,check,target=None):
  if target is not None:
   fcntl.fcntl(target.fileno(),flag,1);counted('destination_fds')
  return original_transfer(directory,name,limit,check,target)
 capture._regular_fd=open_source;capture._transfer=transfer
 return counts

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--meeting',required=True);p.add_argument('--db',type=Path,default=Path.home()/'Library/Application Support/MeetingOS/meeting-os.sqlite');p.add_argument('--worker',action='store_true');p.add_argument('--uncached-assembly',action='store_true');args=p.parse_args()
 if sys.platform!='darwin':raise SystemExit('macOS only')
 if args.worker:
  install_uncached_transfers()
  if args.uncached_assembly:
   from scripts.uncached_assembly import install_uncached_assembly
   install_uncached_assembly()
  from meeting_os.cli import main as cli
  sys.argv=['meeting_os','--db',str(args.db),'retry',args.meeting,'--engine','cpp'];cli(supervised=True);return
 from meeting_os.resources import check_pressure
 from meeting_os.supervisor import run_guarded
 check_pressure()
 listing=subprocess.check_output(['ps','-axo','comm=,args='],text=True)
 for line in listing.splitlines():
  if line.split() and line.split()[0].split('/')[-1]=='MeetingCapture':raise SystemExit('Active capture; deferred')
  if ('Python' in line or 'python' in line) and any(marker in line for marker in ('-m meeting_os record ','-m meeting_os retry ','-m meeting_os finalize ','-m meeting_os.live_worker ')):raise SystemExit('Active audio job; deferred')
 def interrupted(pid):
  from meeting_os.store import Store
  from meeting_os.recovery import mark_interrupted,metadata
  db=Store(args.db)
  try:
   for row in db.meetings():
    if row['id']==args.meeting and metadata(row).get('worker_pid')==pid:mark_interrupted(db,row['id'])
  finally:db.close()
 result=run_guarded([sys.executable,str(Path(__file__).resolve()),'--meeting',args.meeting,'--db',str(args.db),'--worker',*(['--uncached-assembly'] if args.uncached_assembly else [])],timeout=14400,isolated=True,passthrough=True,on_failure=interrupted)
 print(json.dumps({'experimental_retry_resources':result}),flush=True)
if __name__=='__main__':main()
