"""Allowlisted local snapshot. Never read transcripts, databases or error logs."""
import json,os,platform,re,shutil,stat,subprocess,sys,tempfile,time
from pathlib import Path
from . import __version__

STAGES={'loading_models','assembling','reading_audio','vad','diarizing','transcribing','identifying','stopping_capture','complete'}
ERRORS={'pressure_unavailable','memory_pressure','footprint_unavailable','disk_unavailable'}

def _object(value):return value if isinstance(value,dict) else {}
def _number(value,maximum=1048576):return value if type(value)==int and 0<=value<=maximum else None
def _choice(value,allowed,fallback='unknown'):return value if isinstance(value,str) and value in allowed else fallback
def _version(value):return value if isinstance(value,str) and re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,3}){1,3}',value) else None

def sanitize(value):
    value=_object(value);memory=_object(value.get('memory'));disk=_object(value.get('disk'));progress=_object(value.get('progress'))
    errors=value.get('error_codes');errors=errors[:16] if isinstance(errors,list) else []
    return {'schema_version':1,'app_version':_version(value.get('app_version')),
            'python_version':_version(value.get('python_version')),'macos_version':_version(value.get('macos_version')),
            'architecture':_choice(value.get('architecture'),{'arm64','x86_64'}),
            'memory':{'physical_gib':_number(memory.get('physical_gib')),
                      'pressure':_choice(memory.get('pressure'),{'normal','warning','critical'}),
                      'collector_footprint_mib':_number(memory.get('collector_footprint_mib'))},
            'disk':{'free_gib':_number(disk.get('free_gib'))},
            'progress':{'stage':_choice(progress.get('stage'),STAGES),'source':_choice(progress.get('source'),{'mic','system'},None),
                        'freshness':_choice(progress.get('freshness'),{'recent','stale'}),'current':_number(progress.get('current'),1000000),'total':_number(progress.get('total'),1000000)},
            'error_codes':sorted({_choice(e,ERRORS) for e in errors}-{ 'unknown' }),
            'scope':'current_snapshot_not_job_history'}

def read_progress(path):
    fd=None
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>16384:return {}
        raw=os.read(fd,16385)
        if len(raw)>16384:return {}
        result=_object(json.loads(raw));age=time.time()-info.st_mtime
        result['freshness']='recent' if 0<=age<=60 else 'stale' if age>60 else 'unknown'
        return result
    except (OSError,ValueError,TypeError,RecursionError):return {}
    finally:
        if fd is not None:os.close(fd)

def collect(disk_root,progress_path=None):
    from .resources import physical_memory,GIB
    from .supervisor import footprint
    errors=[];pressure='unknown';owned=None;free=None
    if sys.platform=='darwin':
        try:
            level=int(subprocess.check_output(['/usr/sbin/sysctl','-n','kern.memorystatus_vm_pressure_level'],text=True,stderr=subprocess.DEVNULL,timeout=2))
            pressure={1:'normal',2:'warning',4:'critical'}.get(level,'unknown')
        except (OSError,ValueError,subprocess.SubprocessError):pass
        try:owned=footprint(os.getpid())//(1024**2)
        except (OSError,RuntimeError):pass
    if pressure=='unknown':errors.append('pressure_unavailable')
    elif pressure!='normal':errors.append('memory_pressure')
    if owned is None:errors.append('footprint_unavailable')
    try:free=shutil.disk_usage(disk_root).free//GIB
    except OSError:errors.append('disk_unavailable')
    physical=physical_memory()
    return sanitize({'app_version':__version__,'python_version':platform.python_version(),'macos_version':platform.mac_ver()[0],
                     'architecture':platform.machine(),'memory':{'physical_gib':physical//GIB if physical else None,'pressure':pressure,'collector_footprint_mib':owned},
                     'disk':{'free_gib':free},'progress':read_progress(progress_path) if progress_path is not None else {},'error_codes':errors})

def export_report(path,report):
    """Publish complete mode0600 JSON without replacing any existing destination."""
    path=Path(path);temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.meeting-os-diagnostics-',delete=False) as out:
            temporary=Path(out.name);os.fchmod(out.fileno(),0o600)
            json.dump(sanitize(report),out,ensure_ascii=False,indent=2,allow_nan=False)
            out.flush();os.fsync(out.fileno())
        os.link(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
