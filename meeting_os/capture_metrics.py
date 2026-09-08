"""Bounded metadata-only timeline metrics. No audio quality or queue inference."""
import math


def timeline_metrics(events):
    sources = {'mic': [], 'system': []}
    for count, event in enumerate(events):
        if count >= 10000:
            raise ValueError('At most10000 chunks are supported')
        source = event.get('source')
        start, duration = event.get('start'), event.get('duration')
        if source not in sources or any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, duration)):
            raise ValueError('Invalid chunk metadata')
        if start < 0 or not 0 < duration <= 60.1 or start+duration > 14400:
            raise ValueError('Chunk outside supported timeline')
        sources[source].append((float(start), float(start+duration)))
    result = {'scope': 'metadata_only', 'sources': {}}
    for source, intervals in sources.items():
        high = -1.
        out_of_order = 0
        for start, end in intervals:
            if start < high: out_of_order += 1
            high = max(high, start)
        ordered = sorted(intervals)
        covered = gaps = overlap = 0.
        last = None
        for start, end in ordered:
            if last is None:
                covered += end-start
            elif start > last:
                gaps += start-last
                covered += end-start
            else:
                overlap += max(0., min(last, end)-start)
                covered += max(0., end-last)
            last = end if last is None else max(last, end)
        result['sources'][source] = dict(chunks=len(intervals),
            first_start=ordered[0][0] if ordered else None, last_end=last,
            covered_seconds=covered, gap_seconds=gaps, overlap_seconds=overlap,
            out_of_order_chunks=out_of_order)
    return result
