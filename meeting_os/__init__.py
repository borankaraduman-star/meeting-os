"""Meeting OS: no hosted inference or outbound actions."""
import os
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('PYANNOTE_METRICS_ENABLED', '0')
os.environ.setdefault('DO_NOT_TRACK', '1')
__version__ = '1.0.1'
