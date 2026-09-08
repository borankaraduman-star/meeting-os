"""Conservative, bounded checks before loading live inference models."""
from pathlib import Path


def digital_silence_duration(path):
    """Return pipeline duration only for a nonempty WAV of exact digital zeros.

    Check all channels without resampling/downmixing or an amplitude threshold.
    Unknown, changing, malformed, oversized and nonzero audio stays on the normal
    processing/error path. The raw recording is never modified.
    """
    import numpy as np
    import soundfile as sf

    path = Path(path)
    try:
        before = path.stat()
        if not 0 < before.st_size <= 64 * 1024 * 1024:
            return None
        with sf.SoundFile(path) as audio:
            if audio.format not in ('WAV', 'WAVEX') or not 0 < audio.channels <= 8:
                return None
            if not 0 < audio.samplerate <= 192000 or not 0 < audio.frames <= audio.samplerate * 65:
                return None
            frames = 0
            for block in audio.blocks(blocksize=32768, dtype='float64', always_2d=True):
                # NaN and infinity compare nonzero and therefore never skip.
                if np.any(block != 0):
                    return None
                frames += len(block)
            if frames != audio.frames:
                return None
            # Match read_audio resample_poly output length without importing scipy.
            duration = ((frames * 16000 + audio.samplerate - 1) // audio.samplerate) / 16000
        after = path.stat()
        identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        return duration if identity(before) == identity(after) else None
    except (OSError, RuntimeError, ValueError):
        return None
