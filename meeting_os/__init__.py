"""Meeting OS: no hosted inference or outbound actions."""
import os
# Use ordinary HTTP downloads by default: Xet CAS failed on the other Mac.
# Set these before importing Hub, whose constants are cached at import time.
os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', '120')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('PYANNOTE_METRICS_ENABLED', '0')
os.environ.setdefault('DO_NOT_TRACK', '1')
__version__ = '1.2.78'
