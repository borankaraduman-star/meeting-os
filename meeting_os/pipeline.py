import time
import numpy as np
from .audio import RATE, read_audio, speech_regions
from .types import Segment
from .speakers import speaker_at
from .progress import emit

def split_by_speaker(row, offset, turns):
    words = row.get('words', [])
    if not words: return [row]
    groups = []
    for word in words:
        speaker, ambiguous = speaker_at(word['start']+offset, word['end']+offset, turns)
        key = (speaker, ambiguous)
        if not groups or groups[-1][0] != key: groups.append((key, []))
        groups[-1][1].append(word)
    if len(groups) == 1: return [row]
    return [{**row, 'start':ws[0]['start'], 'end':ws[-1]['end'],
             'text':''.join(w.get('word','') for w in ws).strip(), 'words':ws,
             'raw_asr_text':row['text']} for _,ws in groups]

class Pipeline:
    def __init__(self, asr, diarizer, store, identity_threshold=0.80, identity_margin=0.08):
        self.asr, self.diarizer, self.store = asr, diarizer, store
        self.identity_threshold, self.identity_margin = identity_threshold, identity_margin
    def process(self, path, source='system', offset=0, provisional=False):
        emit("reading_audio",source=source)
        audio = read_audio(path)
        emit("vad",source=source)
        regions = speech_regions(audio)
        if not regions: return [], [], len(audio)/RATE
        emit("diarizing",source=source)
        turns = self.diarizer.turns(audio,source)
        result = []
        batch_rows = None
        if provisional and getattr(self.asr,'engine',None)=='cpp' and getattr(self.asr,'batch_regions',False) is True and len(regions)>1:
            emit('transcribing',current=0,total=len(regions),source=source)
            self.asr.batch_used=True
            self.asr.batch_clip_count=len(regions)
            batch_rows=self.asr.transcribe_batch([audio[a:b] for a,b in regions])
            if len(batch_rows)!=len(regions):raise ValueError('ASR batch result count mismatch')
        for index,(begin,end) in enumerate(regions):
            emit("transcribing",current=index,total=len(regions),source=source)
            raw_rows = batch_rows[index] if batch_rows is not None else self.asr.transcribe(audio[begin:end])
            rows = [part for row in raw_rows for part in split_by_speaker(row, begin/RATE, turns)]
            emit("identifying",current=index,total=len(regions),source=source)
            for row in rows:
                a = max(begin/RATE, begin/RATE+float(row['start']))
                b = min(end/RATE, begin/RATE+float(row['end']))
                text = row['text'].strip()
                if b <= a or not text: continue
                metrics = {k:row[k] for k in ('avg_logprob','no_speech_prob','compression_ratio','temperature') if k in row}
                flags = ['provisional'] if provisional else []
                if metrics.get('avg_logprob',0) < -0.8: flags.append('low_asr_confidence')
                if metrics.get('no_speech_prob',0) > 0.5: flags.append('possible_non_speech')
                if metrics.get('compression_ratio',0) > 2.4: flags.append('repetition')
                if row.get('confidence_unavailable') or any(k not in metrics for k in ('avg_logprob','no_speech_prob')): flags.append('confidence_unavailable')
                if self.diarizer.mode == 'cluster': flags.append('baseline_diarization')
                speaker, ambiguous = speaker_at(a,b,turns)
                if provisional and self.diarizer.mode == 'sherpa': speaker = f'{source}:live{offset:.3f}:'+speaker.split(':')[-1]
                if speaker == 'unknown': speaker = source+':unknown'
                if self.diarizer.mode == 'sherpa' and (provisional or len(audio)/RATE < 15):
                    flags.append('short_context_diarization')
                if ambiguous: flags.append('speaker_ambiguous')
                # Never enroll an ASR segment that crosses speaker boundaries.
                vector = None if ambiguous else self.diarizer.embedder.embed(audio[round(a*RATE):round(b*RATE)])
                identity = self.store.identify(vector,self.diarizer.embedder.model_id,self.identity_threshold,self.identity_margin) if vector is not None else {'name':None,'similarity':None,'margin':None}
                metrics['identity'] = identity
                words = [{**w,'start':float(w['start'])+begin/RATE+offset,'end':float(w['end'])+begin/RATE+offset} for w in row.get('words',[])]
                result.append(Segment(a+offset,b+offset,text,source,speaker,identity['name'],metrics,flags,words,vector,self.diarizer.embedder.model_id))
        emit("transcribing",current=len(regions),total=len(regions),source=source)
        return result, [(a+offset,b+offset,s) for a,b,s in turns],len(audio)/RATE
