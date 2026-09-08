"""Bounded native inference child execution; never signal unrelated processes."""
import ctypes
import os
import subprocess
import sys
import signal
import tempfile
import time
from .resources import check_pressure, physical_memory, GIB


class ChildFailure(RuntimeError):
    def __init__(self,code):
        self.code=code
        super().__init__(f'Yerel model başarısız (exit={code})')


def footprint(pid):
    if sys.platform != 'darwin': return 0
    # Darwin rusage_info_v2: UUID followed by 18 uint64 fields. Physical
    # footprint is field 8; includes compressed/Metal accounting unlike RSS.
    class Usage(ctypes.Structure):
        _fields_ = [('uuid',ctypes.c_uint8*16),('values',ctypes.c_uint64*18)]
    info=Usage()
    lib=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
    lib.proc_pid_rusage.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
    lib.proc_pid_rusage.restype=ctypes.c_int
    if lib.proc_pid_rusage(pid,2,ctypes.byref(info)) != 0:
        raise RuntimeError('İşlem bellek ölçümü okunamadı')
    return int(info.values[7])


def open_lifeline(process):
    """Stop an owned session if its supervising Python process dies."""
    read_fd,write_fd=os.pipe()
    try:
        code="import os,signal; data=os.read("+str(read_fd)+",1);\nif not data:\n try: os.killpg("+str(process.pid)+",signal.SIGKILL)\n except ProcessLookupError: pass"
        guardian=subprocess.Popen([sys.executable,'-c',code],pass_fds=(read_fd,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return guardian,write_fd
    except BaseException:
        os.close(write_fd)
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait();raise
    finally:os.close(read_fd)


def close_lifeline(guardian,write_fd):
    if write_fd is not None:
        try:os.write(write_fd,b'd')
        except BrokenPipeError:pass
        os.close(write_fd)
    if guardian is not None:
        try:guardian.wait(timeout=2)
        except subprocess.TimeoutExpired:guardian.kill();guardian.wait()


def run_guarded(command, timeout=600, isolated=False, passthrough=False, on_failure=None, handle_signals=True, cancel_requested=None, output_stream=None, failure_details=True):
    """Run a direct native child (which must not daemonize/spawn workers).

    The caller remains outside the native call. Temporary logs avoid pipe
    deadlocks and unbounded RAM capture. Limit includes this Python caller.
    """
    check_pressure()
    budget=min(int(3.5*GIB),max(GIB,physical_memory()//4))
    with tempfile.TemporaryFile() as log:
        process=subprocess.Popen(command,stdout=output_stream if output_stream is not None else (None if passthrough else log),stderr=None if passthrough else log,start_new_session=isolated)
        guardian,lifeline=open_lifeline(process) if isolated else (None,None)
        old_handlers={}
        if isolated and handle_signals:
            def canceled(sig,frame):raise RuntimeError('İşlem iptal edildi; ses korunuyor')
            for sig in (signal.SIGINT,signal.SIGTERM):
                old_handlers[sig]=signal.signal(sig,canceled)
        start=time.monotonic()
        try:
            while process.poll() is None:
                if cancel_requested and cancel_requested():raise RuntimeError("Canlı metin işlemi durduruldu; ses korunuyor")
                if time.monotonic()-start > timeout:
                    raise RuntimeError('Yerel model süre sınırını aştı; ses korunuyor')
                check_pressure()
                try:
                    if isolated:
                        listing=subprocess.check_output(['/bin/ps','-axo','pid=,pgid='],text=True,timeout=2)
                        pids=[int(parts[0]) for line in listing.splitlines() if len(parts:=line.split())==2 and int(parts[1])==process.pid]
                        usage=footprint(os.getpid())
                        for pid in pids:
                            try:usage+=footprint(pid)
                            except RuntimeError:
                                # A descendant may finish between ps and rusage.
                                try:os.kill(pid,0)
                                except ProcessLookupError:continue
                                raise
                    else:usage=footprint(os.getpid())+footprint(process.pid)
                except RuntimeError:
                    if process.poll() is not None:break
                    raise
                if usage>budget:
                    raise RuntimeError('Yerel model bellek sınırını aştı; ses korunuyor')
                time.sleep(.1)
            if process.returncode:
                if passthrough or not failure_details:raise ChildFailure(process.returncode)
                log.seek(0,2);size=log.tell();log.seek(max(0,size-2000))
                detail=log.read().decode('utf-8',errors='replace')
                raise RuntimeError(f'Yerel model başarısız (exit={process.returncode}): {detail}')
        except BaseException:
            for sig in old_handlers:signal.signal(sig,signal.SIG_IGN)
            if isolated:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            elif process.poll() is None:process.kill()
            process.wait()
            if on_failure:on_failure(process.pid)
            raise
        finally:
            if process.poll() is None:process.kill()
            process.wait()
            close_lifeline(guardian,lifeline)
            for sig,handler in old_handlers.items():signal.signal(sig,handler)
