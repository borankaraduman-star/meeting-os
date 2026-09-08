"""Opt-in ASR window experiment; diarizer labels are not verified identities."""
import math
from .audio import RATE


def group_regions(regions, turns):
    """Preserve contiguous source samples; reject uncertain merges.

    Policy bounds (not calibrated accuracy claims): <=12s window, <=750ms gap,
    <=250ms uncovered VAD padding at each edge, >=50% labeled coverage, and
    no unlabeled hole inside an individual speech region. Other/unknown turns
    anywhere in the full proposed window block merging.
    """
    regions=list(regions)
    previous=0
    for a,b in regions:
        if type(a) is not int or type(b) is not int or a<previous or b<=a:
            raise ValueError('Expected ordered nonoverlapping sample regions')
        previous=b
    if any(not isinstance(s,str) or not s or not all(math.isfinite(t) for t in (a,b)) or a<0 or b<=a for a,b,s in turns):
        return regions

    def label(begin,end):
        a,b=begin/RATE,end/RATE
        hits=[(max(a,x),min(b,y),s) for x,y,s in turns if x<b and y>a]
        names={s for _,_,s in hits}
        if len(names)!=1:return None
        name=next(iter(names))
        if name.split(':')[-1].lower()=='unknown':return None
        intervals=sorted((x,y) for x,y,_ in hits)
        left,right=intervals[0]
        for x,y in intervals[1:]:
            if x>right:return None
            right=max(right,y)
        if left-a>.25 or b-right>.25 or right-left < .5*(b-a):return None
        return name

    grouped=[];last_label=None
    for a,b in regions:
        current=label(a,b)
        if grouped and current is not None and current==last_label:
            begin,end=grouped[-1]
            others=any(x<b/RATE and y>begin/RATE and s!=current for x,y,s in turns)
            if a-end<=.75*RATE and b-begin<=12*RATE and not others:
                grouped[-1]=(begin,b)
                continue
        grouped.append((a,b));last_label=current
    return grouped
