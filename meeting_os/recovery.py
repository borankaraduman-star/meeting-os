"""Conservative job recovery. Never signal processes or alter audio/transcripts."""
import ctypes
import errno
import json
import os
import subprocess
import sys
from functools import lru_cache

@lru_cache(maxsize=1)
def boot_identity():
    if sys.platform != 'darwin':return None
    try:
        value=subprocess.check_output(['/usr/sbin/sysctl','-n','kern.bootsessionuuid'],timeout=2,text=True).strip()
        return value or None
    except (OSError,subprocess.SubprocessError):return None

def process_identity(pid):
    if type(pid)!=int or pid<=0 or sys.platform!='darwin':return None
    boot=boot_identity()
    if not boot:return None
    # SDK sys/proc_info.h: PROC_PIDTBSDINFO=3; proc_bsdinfo, 136 bytes.
    class BSDInfo(ctypes.Structure):
        _fields_=[('head',ctypes.c_uint32*12),('comm',ctypes.c_char*16),
                  ('name',ctypes.c_char*32),('tail',ctypes.c_uint32*6),
                  ('start_sec',ctypes.c_uint64),('start_usec',ctypes.c_uint64)]
    info=BSDInfo();lib=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
    lib.proc_pidinfo.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_int]
    lib.proc_pidinfo.restype=ctypes.c_int
    size=lib.proc_pidinfo(pid,3,0,ctypes.byref(info),ctypes.sizeof(info))
    if size!=ctypes.sizeof(info):
        if size==0 and ctypes.get_errno()==errno.ESRCH:raise ProcessLookupError(pid)
        return None
    if info.head[3]!=pid or not info.start_sec or info.start_usec>=1000000:return None
    return {'pid':pid,'started_us':int(info.start_sec)*1000000+int(info.start_usec),'boot':boot}

def current_job_metadata():
    try:identity=process_identity(os.getpid())
    except OSError:identity=None
    return {'worker_pid':os.getpid(),'worker_identity':identity}

def valid_identity(value):
    return (isinstance(value,dict) and type(value.get('pid'))==int and value['pid']>0
            and type(value.get('started_us'))==int and value['started_us']>0
            and isinstance(value.get('boot'),str) and bool(value['boot']))

def classify(identity,inspect=process_identity):
    if not valid_identity(identity):return 'unknown'
    try:observed=inspect(identity['pid'])
    except ProcessLookupError:return 'interrupted'
    except OSError:return 'unknown'
    if not valid_identity(observed):return 'unknown'
    return 'active' if all(identity[k]==observed[k] for k in ('pid','started_us','boot')) else 'interrupted'

def metadata(row):
    try:value=json.loads(row['metadata'])
    except (TypeError,ValueError):return {}
    return value if isinstance(value,dict) else {}

def list_recovery(store,inspect=process_identity,include_audio=False):
    result=[]
    for row in store.meetings():
        if row['status']!='processing' and not (include_audio and row['status'] in ('incomplete','provisional','failed')):continue
        meta=metadata(row)
        state=classify(meta.get('worker_identity'),inspect) if row['status']=='processing' else row['status']
        item={'meeting':row['id'],'status':row['status'],'recovery_state':state}
        if include_audio:
            from .recovery_audio import inspect_capture
            if state in ('active','unknown'):item['audio']={'status':'not_checked_owner_uncertain'}
            elif isinstance(meta.get('capture_dir'),str):item['audio']=inspect_capture(meta['capture_dir'])
            else:item['audio']={'status':'not_supported_import'}
        result.append(item)
    return result

def mark_interrupted(store,mid,inspect=process_identity):
    # Lock before reading identity: no concurrent metadata/status change may
    # turn this transition into a change to a new job using the same meeting.
    store.db.execute('BEGIN IMMEDIATE')
    try:
        row=store.db.execute('SELECT * FROM meetings WHERE id=?',(mid,)).fetchone()
        if row is None or row['status']!='processing' or classify(metadata(row).get('worker_identity'),inspect)!='interrupted':
            store.db.rollback();return False
        store.db.execute("UPDATE meetings SET status='incomplete' WHERE id=? AND status='processing'",(mid,))
        store.db.commit();return True
    except BaseException:
        store.db.rollback();raise
