"""Conservative admission checks for local inference on a shared Mac."""
import json,subprocess,sys
from pathlib import Path
GIB=1024**3

def physical_memory():
    if sys.platform!='darwin':return 0
    try:return int(subprocess.check_output(['/usr/sbin/sysctl','-n','hw.memsize'],timeout=2))
    except (OSError,ValueError,subprocess.SubprocessError):return 0

def check_pressure():
    if sys.platform!='darwin':return
    try:level=int(subprocess.check_output(['/usr/sbin/sysctl','-n','kern.memorystatus_vm_pressure_level'],timeout=2))
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Bellek durumu okunamadı ({type(exc).__name__}); güvenlik için yerel model başlatılmadı.") from exc
    if level!=1:raise RuntimeError('Mac bellek baskısı altında. Ağır uygulamaları kapatıp yeniden deneyin; ses dosyaları korunuyor.')

def check_asr_model(path):
    cfg=Path(path)/'config.json'
    if cfg.exists() and json.loads(cfg.read_text()).get('n_text_layer',0)>4:
        if physical_memory()<32*GIB:
            raise RuntimeError('Bu büyük Whisper modeli en az 32 GB RAM gerektiriyor. 16 GB Mac için mlx-turbo kullanın.')

def configure_mlx():
    check_pressure()
    import mlx.core as mx
    # MLX memory_limit is advisory, not a hard process limit. The native UI also
    # monitors physical footprint and OS pressure and terminates its own job.
    mx.set_cache_limit(64*1024**2)
    mx.set_memory_limit(min(4*GIB,max(GIB,physical_memory()//4)))

def low_memory_mac():
    return sys.platform=='darwin' and physical_memory()<=16*GIB
