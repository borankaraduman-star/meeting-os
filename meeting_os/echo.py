"""Bounded, read-only correlation evidence; never cancellation or speaker inference."""
import numpy as np
from scipy.signal import correlate, correlation_lags, resample_poly


def measure_echo(system, mic):
    """Inspect <=5s mono 16kHz PCM with a shared nominal timeline.

    Positive lag means mic follows system. Search +/-250ms at 2kHz.
    Thresholds are provisional fixture heuristics, not calibrated probabilities.
    Correlation cannot establish acoustic causality or identify double-talk.
    """
    inputs = [_pcm(system), _pcm(mic)]
    result = dict(status='insufficient_signal', lag_seconds=None,
                  correlation=None, gain=None, residual_energy_ratio=None)
    if min(map(len, inputs)) < 8000:
        return result
    x, y = [resample_poly(v, 1, 8) for v in inputs]
    x -= x.mean()
    y -= y.mean()
    if min(np.mean(x*x), np.mean(y*y)) < 1e-10:
        return result
    # Refuse evidence concentrated into a click/impulse (<32ms effective support).
    if any(float(np.dot(v, v))**2 / float(np.dot(v*v, v*v)) < 64 for v in (x, y)):
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


def _pcm(value):
    value = np.asarray(value)
    if value.ndim != 1 or value.size > 80000 or np.iscomplexobj(value):
        raise ValueError('Expected at most five seconds of real mono 16kHz PCM')
    value = np.array(value, dtype=np.float64, copy=True)
    if not np.isfinite(value).all() or np.any(np.abs(value) > 1):
        raise ValueError('Expected finite normalized PCM')
    return value


def _time(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError('Expected numeric timeline seconds')
    if not np.isfinite(value) or not 0 <= value <= 14400:
        raise ValueError('Timeline must be within four hours')
    return float(value)


def measure_timed_echo(system, mic, *, system_start=0., mic_start=0.):
    """Align nominal timestamps then inspect their common interval without edits.

    Each input remains bounded to five seconds. Offsets round to the closest
    16kHz sample (<=31.25us error per channel); lag resolution is 0.5ms.
    No inference is made from disjoint or <0.5s common intervals.
    """
    system_start, mic_start = _time(system_start), _time(mic_start)
    system, mic = _pcm(system), _pcm(mic)
    start = max(system_start, mic_start)
    end = min(system_start+len(system)/16000, mic_start+len(mic)/16000)
    if max(system_start+len(system)/16000, mic_start+len(mic)/16000) > 14400:
        raise ValueError('Audio exceeds four-hour timeline')
    count = max(0, int(round((end-start)*16000)))
    a = int(round((start-system_start)*16000))
    b = int(round((start-mic_start)*16000))
    count = max(0, min(count, len(system)-a, len(mic)-b))
    return dict(start=start, end=max(start, end),
                measurement=measure_echo(system[a:a+count], mic[b:b+count]))


def summarize_echo_windows(windows):
    """Summarize <=256 nonoverlapping windows, never establish clock causality.

    At least three accepted windows spanning >=10s are required. Least-squares
    lag trend is withheld if any residual exceeds 2ms. Sparse sampling cannot
    detect device changes between windows or prove constant hardware drift.
    """
    rows = []
    for row in windows:
        if len(rows) >= 256:
            raise ValueError('At most 256 windows are supported')
        if not isinstance(row, dict):
            raise ValueError('Expected a measurement row')
        start, end = _time(row.get('start')), _time(row.get('end'))
        if not 0 <= end-start <= 5.000001:
            raise ValueError('Invalid window duration')
        measurement = row.get('measurement')
        if not isinstance(measurement, dict) or measurement.get('status') not in ('correlated_copy', 'inconclusive', 'insufficient_signal'):
            raise ValueError('Invalid measurement status')
        lag = None
        if measurement['status'] == 'correlated_copy':
            lag = measurement.get('lag_seconds')
            if isinstance(lag, bool) or not isinstance(lag, (float, int)) or not np.isfinite(lag) or abs(lag) >= .25 or end-start < .5:
                raise ValueError('Invalid accepted measurement')
        rows.append((start, end, lag))
    rows.sort(key=lambda row: row[0])
    for previous, current in zip(rows, rows[1:]):
        if current[0] < previous[1]-1e-9 or current[0] == previous[0]:
            raise ValueError('Windows must be distinct and nonoverlapping')
    accepted = [((a+b)/2, lag) for a,b,lag in rows if lag is not None]
    result = dict(status='inconclusive', windows=len(rows), accepted_windows=len(accepted),
                  lag_trend_ppm=None, reference_seconds=None, lag_at_reference_seconds=None,
                  max_fit_error_seconds=None, clock_drift_proven=False)
    if len(accepted) < 3 or accepted[-1][0]-accepted[0][0] < 10:
        return result
    t, lags = np.array(accepted, dtype=float).T
    reference = float(t.mean())
    centered = t-reference
    slope = float(np.dot(centered, lags-lags.mean()) / np.dot(centered, centered))
    error = float(np.max(np.abs(lags-(lags.mean()+slope*centered))))
    result['max_fit_error_seconds'] = error
    if error > .002:
        return result
    result.update(status='consistent_lag_trend', lag_trend_ppm=slope*1e6,
                  reference_seconds=reference, lag_at_reference_seconds=float(lags.mean()))
    return result
