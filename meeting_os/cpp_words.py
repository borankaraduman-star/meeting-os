"""Conservative word grouping from pinned whisper.cpp full JSON token offsets.

Token times are heuristic, not forced alignment. Invalid/incomplete alignment
falls back to the intact segment; never silently omit lexical text.
"""
import math,re

def words_for(segment):
    try:
        lo=segment['offsets']['from']/1000;hi=segment['offsets']['to']/1000
        if not (math.isfinite(lo) and math.isfinite(hi) and 0<=lo<hi):return []
        groups=[];previous=lo
        for token in segment.get('tokens',[]):
            text=token['text']
            if re.fullmatch(r'\[_[^\]]*\]',text):continue
            # A token with multiple lexical words cannot supply separate times.
            if not text.strip() or re.search(r'\s',text.lstrip()):return []
            a=token['offsets']['from']/1000;b=token['offsets']['to']/1000
            if not (math.isfinite(a) and math.isfinite(b) and previous<=a<=b<=hi):return []
            previous=b
            if not groups or text[0].isspace():groups.append({'word':text,'start':a,'end':b})
            else:groups[-1]['word']+=text;groups[-1]['end']=b
        if ''.join(g['word'] for g in groups).strip()!=segment['text'].strip():return []
        if any(g['end']<=g['start'] for g in groups):return []
        return groups
    except (KeyError,TypeError,ValueError,OverflowError):return []

def parse_transcription(data):
    if not isinstance(data,dict) or not isinstance(data.get('transcription'),list):
        raise ValueError('Invalid CPP transcription schema')
    result=[]
    for segment in data['transcription']:
        # Structural corruption fails the call atomically, as in the original
        # adapter. Do not silently skip text or manufacture segment timestamps.
        try:
            lo=segment['offsets']['from'];hi=segment['offsets']['to']
            if type(lo) not in (int,float) or type(hi) not in (int,float):raise ValueError()
            if not (math.isfinite(lo) and math.isfinite(hi) and 0<=lo<=hi):raise ValueError()
            if not isinstance(segment['text'],str):raise ValueError()
        except (KeyError,TypeError,ValueError,OverflowError):
            raise ValueError('Invalid CPP segment schema or timing') from None
        words=words_for(segment)
        row={'start':segment['offsets']['from']/1000,'end':segment['offsets']['to']/1000,
             'text':segment['text'],'words':words,'confidence_unavailable':True}
        if words:row['word_timing']='cpp_token_heuristic'
        result.append(row)
    return result
