"""Bounded, read-only correlation evidence; never cancellation or speaker inference."""
import numpy as np
from scipy.signal import correlate, correlation_lags, resample_poly


def measure_echo(system, mic):
    """Inspect <=5s mono 16kHz PCM with a shared nominal timeline.

    Positive lag means mic follows system. Search +/-250ms at 2kHz.
    Thresholds are provisional fixture heuristics, not calibrated probabilities.
    Correlation cannot establish acoustic causality or identify double-talk.
    """
    inputs = []
    for value in (system, mic):
        value = np.asarray(value)
        if value.ndim != 1 or value.size > 80000:
            raise ValueError('Expected at most five seconds of mono 16kHz PCM')
        value = np.array(value, dtype=np.float64, copy=True)
        if not np.isfinite(value).all() or np.any(np.abs(value) > 1):
            raise ValueError('Expected finite normalized PCM')
        inputs.append(value)
    result = dict(status='insufficient_signal', lag_seconds=None,
                  correlation=None, gain=None, residual_energy_ratio=None)
    if min(map(len, inputs)) < 8000:
        return result
    x, y = [resample_poly(v, 1, 8) for v in inputs]
    x -= x.mean()
    y -= y.mean()
    if min(np.mean(x*x), np.mean(y*y)) < 1e-10:
        return result
    cross = correlate(y, x, mode='full', method='fft')
    lags = correlation_lags(len(y), len(x))
    candidates = []
    for index in np.flatnonzero(np.abs(lags) <= 500):
        lag = int(lags[index])
        left, right = max(0, -lag), max(0, lag)
        count = min(len(x)-left, len(y)-right)
        if count < 500:
            continue
        a, b = x[left:left+count], y[right:right+count]
        ea = max(0., float(np.dot(a, a) - a.sum()**2/count))
        eb = max(0., float(np.dot(b, b) - b.sum()**2/count))
        if min(ea, eb)/count >= 1e-10:
            centered_cross = float(cross[index]) - a.sum()*b.sum()/count
            candidates.append((abs(centered_cross) / np.sqrt(ea*eb), lag))
    if not candidates:
        return result
    score, lag = max(candidates, key=lambda row: (row[0], -abs(row[1])))
    # Repeated peaks >10ms apart make tonal/repetitive alignment ambiguous.
    runner_up = max((s for s, other in candidates if abs(other-lag) > 20), default=0.)
    result['status'] = 'inconclusive'
    result['correlation'] = float(min(score, 1.))
    if score < .75 or score-runner_up < .1 or abs(lag) == 500:
        return result
    left, right = max(0, -lag), max(0, lag)
    count = min(len(x)-left, len(y)-right)
    a, b = x[left:left+count], y[right:right+count]
    a = a - a.mean()
    b = b - b.mean()
    gain = float(np.dot(a, b) / np.dot(a, a))
    residual = b - gain*a
    result.update(status='correlated_copy', lag_seconds=lag/2000,
                  gain=gain, residual_energy_ratio=float(np.dot(residual, residual)/np.dot(b, b)))
    return result
