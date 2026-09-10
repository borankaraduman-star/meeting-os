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
    def process(self, path, source='system', offset=0, provisional=False, bounded_final=False):
        if bounded_final and provisional:raise ValueError('Bounded final reader is not a live experiment')
        if provisional and getattr(getattr(self.diarizer,"embedder",None),"isolated_final",False) is True:
            import tempfile
            from pathlib import Path
            import soundfile as sf
            # Live capture chunks are bounded; retain the original mono/resample
            # operation, then let sequential workers share a private FLOAT WAV.
            info=sf.info(path)
            if info.frames/info.samplerate>60:raise ValueError('Live chunk exceeds 60 seconds')
            audio=read_audio(path)
            if not len(audio):return [],[],0
            with tempfile.TemporaryDirectory(prefix='meeting-os-live-pcm-') as tmp:
                pcm=Path(tmp)/'audio.wav';sf.write(pcm,audio,RATE,subtype='FLOAT');del audio
                with sf.SoundFile(pcm) as reader:
                    return self._process(pcm,source,offset,provisional,reader)
        if not bounded_final:return self._process(path,source,offset,provisional)
        if provisional:raise ValueError('Bounded final reader is not a live experiment')
        import soundfile as sf
        # Retry owns this immutable assembled PCM snapshot; no resampling here.
        with sf.SoundFile(path) as reader:
            if reader.samplerate!=RATE or reader.channels!=1:
                raise ValueError('Bounded final reader requires mono 16kHz audio')
            if not reader.frames:return [],[],0
            return self._process(path,source,offset,provisional,reader)

    def _process(self,path,source,offset,provisional,reader=None):
        emit("reading_audio",source=source)
        deferred = reader is not None and getattr(getattr(self.diarizer,"embedder",None),"isolated_final",False) is True
        if deferred:audio=None
        elif reader is None:audio=read_audio(path)
        else:
            import mmap
            # The ndarray owns the mapping via .base. Let reference ownership
            # close it: explicit close would invalidate retained/native views.
            audio=np.ndarray((reader.frames,),dtype=np.float32,buffer=mmap.mmap(-1,reader.frames*4))
            if len(reader.read(out=audio))!=len(audio):raise ValueError('Final audio became truncated')
            for start in range(0,len(audio),65536):
                if not np.isfinite(audio[start:start+65536]).all():raise ValueError('Audio contains non-finite samples')
        duration=(reader.frames if reader is not None else len(audio))/RATE
        emit("vad",source=source)
        if deferred:
            from .final_vad import isolated_regions
            regions=isolated_regions(path,reader.frames)
        else:regions = speech_regions(audio)
        if not regions: return [], [], duration
        emit("diarizing",source=source)
        if reader is not None and getattr(self.diarizer,'isolate_sherpa',False) is True:
            audio=None  # Retry owns the file; avoid keeping a second full recording.
            turns = self.diarizer.turns_file(path,source,reader.frames)
        else:
            turns = self.diarizer.turns(audio,source)
        if reader is not None:
            audio=None  # Unreferenced mmap pages return to OS, not NumPy's cache.
        window_counts = {}
        if provisional and getattr(self.asr,'engine',None)=='cpp' and getattr(self.asr,'same_speaker_windows',False) is True and not getattr(self.asr,'batch_regions',False):
            from .speaker_windows import group_regions
            original_regions = regions
            regions = group_regions(regions, turns)
            window_counts = {(a,b):sum(a<=x and y<=b for x,y in original_regions) for a,b in regions}
        result = []
        pending_identity = []
        batch_rows = None
        if provisional and getattr(self.asr,'engine',None)=='cpp' and getattr(self.asr,'batch_regions',False) is True and len(regions)>1:
            emit('transcribing',current=0,total=len(regions),source=source)
            self.asr.batch_used=True
            self.asr.batch_clip_count=len(regions)
            if reader is None:clips=[audio[a:b] for a,b in regions]
            else:
                clips=[]
                for a,b in regions:
                    reader.seek(a);clip=reader.read(b-a,dtype='float32')
                    if len(clip)!=b-a:raise ValueError('Live audio became truncated')
                    clips.append(clip)
            batch_rows=self.asr.transcribe_batch(clips)
            del clips
            if len(batch_rows)!=len(regions):raise ValueError('ASR batch result count mismatch')
        for index,(begin,end) in enumerate(regions):
            emit("transcribing",current=index,total=len(regions),source=source)
            if reader is None:clip=audio[begin:end]
            else:
                reader.seek(begin);clip=reader.read(end-begin,dtype='float32')
                if len(clip)!=end-begin:raise ValueError('Final audio became truncated')
            raw_rows = batch_rows[index] if batch_rows is not None else self.asr.transcribe(clip)
            rows = [part for row in raw_rows for part in split_by_speaker(row, begin/RATE, turns)]
            if not deferred:emit("identifying",current=index,total=len(regions),source=source)
            for row in rows:
                a = max(begin/RATE, begin/RATE+float(row['start']))
                b = min(end/RATE, begin/RATE+float(row['end']))
                text = row['text'].strip()
                if b <= a or not text: continue
                metrics = {k:row[k] for k in ('avg_logprob','no_speech_prob','compression_ratio','temperature') if k in row}
                if row.get('word_timing'):metrics['word_timing']=row['word_timing']
                flags = ['provisional'] if provisional else []
                if window_counts.get((begin,end),1)>1:
                    metrics['asr_window_regions']=window_counts[(begin,end)]
                    flags.append('experimental_asr_window')
                if metrics.get('avg_logprob',0) < -0.8: flags.append('low_asr_confidence')
                if metrics.get('no_speech_prob',0) > 0.5: flags.append('possible_non_speech')
                if metrics.get('compression_ratio',0) > 2.4: flags.append('repetition')
                if row.get('confidence_unavailable') or any(k not in metrics for k in ('avg_logprob','no_speech_prob')): flags.append('confidence_unavailable')
                if self.diarizer.mode == 'cluster': flags.append('baseline_diarization')
                speaker, ambiguous = speaker_at(a,b,turns)
                if provisional and self.diarizer.mode == 'sherpa': speaker = f'{source}:live{offset:.3f}:'+speaker.split(':')[-1]
                if speaker == 'unknown': speaker = source+':unknown'
                if self.diarizer.mode == 'sherpa' and (provisional or duration < 15):
                    flags.append('short_context_diarization')
                if ambiguous: flags.append('speaker_ambiguous')
                # Never enroll an ASR segment that crosses speaker boundaries.
                vector = None if ambiguous or deferred else self.diarizer.embedder.embed(clip[max(0,round(a*RATE)-begin):round(b*RATE)-begin])
                identity = self.store.identify(vector,self.diarizer.embedder.model_id,self.identity_threshold,self.identity_margin) if vector is not None else {'name':None,'similarity':None,'margin':None}
                metrics['identity'] = identity
                words = [{**w,'start':float(w['start'])+begin/RATE+offset,'end':float(w['end'])+begin/RATE+offset} for w in row.get('words',[])]
                result.append(Segment(a+offset,b+offset,text,source,speaker,identity['name'],metrics,flags,words,vector,self.diarizer.embedder.model_id))
                if deferred and not ambiguous:
                    pending_identity.append((result[-1],(begin+max(0,round(a*RATE)-begin),min(end,round(b*RATE)))))
        if deferred and pending_identity:
            emit('identifying',current=0,total=len(pending_identity),source=source)
            vectors=self.diarizer.embedder.embed_file(path,[span for _,span in pending_identity])
            if len(vectors)!=len(pending_identity):raise ValueError('Incomplete final identity batch')
            for (segment,_),vector in zip(pending_identity,vectors):
                identity=self.store.identify(vector,self.diarizer.embedder.model_id,self.identity_threshold,self.identity_margin) if vector is not None else {'name':None,'similarity':None,'margin':None}
                segment.embedding=vector;segment.speaker_name=identity['name'];segment.metrics['identity']=identity
        emit("transcribing",current=len(regions),total=len(regions),source=source)
        return result, [(a+offset,b+offset,s) for a,b,s in turns],duration
