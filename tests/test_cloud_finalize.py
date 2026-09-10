import json,tempfile,unittest
from pathlib import Path
import numpy as np
import soundfile as sf
from meeting_os.store import Store
from meeting_os.cloud_finalize import finalize_capture, import_file_cloud_only, pieces, speaker_label, is_silent, merge_segments, flag_echo, assign_identities
from meeting_os.openrouter import OpenRouterError

def capture_dir(root,seconds=4):
    """Two-source capture journal: mic is digital silence, system carries a tone."""
    d=Path(root)/'rec';d.mkdir();events=[]
    t=np.arange(16000*seconds)/16000
    for source,signal in (('mic',np.zeros(len(t),dtype='float32')),('system',(0.3*np.sin(2*np.pi*440*t)).astype('float32'))):
        path=d/f'{source}-000000.wav';sf.write(path,signal,16000,subtype='FLOAT')
        events.append({'event':'chunk','source':source,'start':0,'duration':seconds,'path':str(path),'sample_rate':16000,'index':0})
    (d/'capture-native.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
    return d

class FakeClient:
    def __init__(self,fail_at=None):self.calls=[];self.fail_at=fail_at
    def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90,**kw):
        self.calls.append({'bytes':len(audio),'format':fmt,'model':model,'diarize':diarize,'timeout':timeout})
        if self.fail_at==len(self.calls):raise OpenRouterError('network')
        if diarize:return {'text':'Merhaba. Selam.','usage':{'seconds':4,'cost':.0003},'segments':[{'start':0.0,'end':1.5,'text':'Merhaba.','speaker':'0'},{'start':1.6,'end':3.0,'text':'Selam.','speaker':'1'}]}
        return {'text':'Tek parça metin.','usage':{'seconds':4,'cost':.0003}}

class CloudFinalizeTests(unittest.TestCase):
    def test_pieces_and_labels(self):
        self.assertEqual(pieces(2500,1200),[(0,1200),(1200,2400),(2400,2500)])
        self.assertEqual(speaker_label('mic','3',0,False),'Ben');   # nobody's name until Settings has oneself.assertEqual(speaker_label('system','0',0,False),'Konuşmacı 1')
        self.assertEqual(speaker_label('system','1',2,True),'Konuşmacı 3-2');self.assertEqual(speaker_label('system',None,0,False),'Karşı taraf')
    def test_diarized_finalize_skips_silent_mic_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp);store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Kayıt',{'capture_dir':str(d),'provisional':True});store.status(mid,'incomplete')
            from meeting_os.types import Segment;store.add_segment(mid,Segment(0,1,'canlı geçici','system','S0',flags=['provisional']))
            client=FakeClient(fail_at=1)
            with self.assertRaises(OpenRouterError):finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=client)
            row=store.db.execute('SELECT status,metadata FROM meetings WHERE id=?',(mid,)).fetchone()
            self.assertEqual(row['status'],'incomplete');meta=json.loads(row['metadata'])
            self.assertEqual(meta['cloud_mode'],'capture');self.assertEqual(meta['model'],'deepgram/nova-3');self.assertEqual(store.segments(mid),[])
            with self.assertRaises(ValueError):finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=client)
            result=finalize_capture(store,mid,tmp,consent=True,client=client)
            self.assertEqual(result['model'],'deepgram/nova-3');self.assertEqual(len(client.calls),2)  # silent mic never uploaded
            self.assertTrue(all(c['diarize'] and c['format']=='ogg' and c['timeout']>=600 for c in client.calls))
            rows=store.segments(mid)
            self.assertEqual([(r['speaker'],r['text'],r['source']) for r in rows],[('Konuşmacı 1','Merhaba.','system'),('Konuşmacı 2','Selam.','system')])
            self.assertIn('cloud_diarization',rows[0]['flags']);self.assertEqual(rows[1]['start'],1.6)
            self.assertEqual(store.db.execute('SELECT status FROM meetings WHERE id=?',(mid,)).fetchone()[0],'complete')
            again=finalize_capture(store,mid,tmp,consent=True,client=client);self.assertEqual(len(client.calls),2);self.assertEqual(again['segments'],2)
            store.close()
    def test_non_diarization_model_uses_short_windows_and_source_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=65);store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Kayıt',{'capture_dir':str(d)});store.status(mid,'incomplete');client=FakeClient()
            finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=client)
            self.assertEqual(len(client.calls),3);self.assertFalse(any(c['diarize'] for c in client.calls))
            rows=store.segments(mid);self.assertEqual({r['speaker'] for r in rows},{'Karşı taraf'});self.assertEqual([r['start'] for r in rows],[0,30,60])
            self.assertIn('coarse_timing',rows[0]['flags']);store.close()
    def test_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite');mid=store.create_meeting('Yok',{})
            with self.assertRaises(OpenRouterError):finalize_capture(store,mid,tmp,consent=False,client=FakeClient())
            with self.assertRaises(ValueError):finalize_capture(store,mid,tmp,consent=True,client=FakeClient())  # no capture dir
            from meeting_os.recovery import current_job_metadata
            live=store.create_meeting('Canlı',{'capture_dir':tmp,**current_job_metadata()})
            with self.assertRaises(ValueError):finalize_capture(store,live,tmp,consent=True,client=FakeClient())
            self.assertTrue(is_silent(str(capture_dir(tmp)/'mic-000000.wav'),0,4));store.close()

    def test_file_import_cloud_only_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'toplanti.wav';t=np.arange(16000*3)/16000;sf.write(src,(0.2*np.sin(2*np.pi*300*t)).astype('float32'),16000,subtype='FLOAT')
            store=Store(Path(tmp)/'db.sqlite');client=FakeClient(fail_at=1)
            with self.assertRaises(OpenRouterError):import_file_cloud_only(store,src,'Dosya',tmp,consent=True,model='deepgram/nova-3',client=client)
            mid=store.meetings()[0]['id'];meta=json.loads(store.meetings()[0]['metadata'])
            self.assertEqual(meta['cloud_mode'],'file');self.assertTrue(Path(meta['paths']['system']).is_file());self.assertEqual(store.meetings()[0]['status'],'incomplete')
            result=finalize_capture(store,mid,tmp,consent=True,client=client)
            self.assertEqual(result['segments'],2);self.assertEqual(len(client.calls),2)
            self.assertEqual([r['speaker'] for r in store.segments(mid)],['Konuşmacı 1','Konuşmacı 2']);store.close()

class FakeEmbedder:
    model_id='resemblyzer:test'
    def __init__(self):self.spans=[]
    def embed_file(self,path,spans):
        self.spans+=spans
        # speaker 0 segment (0-1.5s) is short -> not requested; both requested spans get distinct vectors by start time
        return [[1.0,0.0] if a<16000*2 else [0.0,1.0] for a,b in spans]

class LongFakeClient(FakeClient):
    def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90,**kw):
        self.calls.append({'diarize':diarize})
        return {'text':'x','usage':{'seconds':8},'segments':[{'start':0.0,'end':3.5,'text':'Ayşe konuşuyor.','speaker':'0'},{'start':4.0,'end':7.5,'text':'Mehmet cevap veriyor.','speaker':'1'}]}

class IdentityTests(unittest.TestCase):
    def test_cluster_identity_names_known_voice_and_speaker_naming_saves_profile(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=8);db=Path(tmp)/'db.sqlite';store=Store(db)
            store.enroll('Ayşe',[1.0,0.0],'resemblyzer:test',4.0,'earlier')
            mid=store.create_meeting('Kayıt',{'capture_dir':str(d)});store.status(mid,'incomplete')
            emb=FakeEmbedder();finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=LongFakeClient(),embedder=emb)
            rows=store.segments(mid)
            self.assertEqual([(r['speaker'],r['speaker_name']) for r in rows],[('Konuşmacı 1','Ayşe'),('Konuşmacı 2',None)])
            self.assertTrue(all(r['embedding'] for r in rows));self.assertEqual(rows[0]['metrics']['identity']['name'],'Ayşe')
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0]);self.assertEqual(meta['identity'],{'embedded':2,'named':1,'suggested':0,'fed':0})
            store.close()
            result=dispatch({'action':'label_speaker','meeting':mid,'speaker':'Konuşmacı 2','name':'Mehmet','enroll':True},db)
            self.assertEqual(result,{'labeled':1,'profile_saved':True,'seconds':3.5,'renamed':0,'suggested':0})   # Q9: the only other cluster is already named
            snap=dispatch({'action':'snapshot','meeting':mid},db)
            self.assertEqual([s['speaker_name'] for s in snap['segments']],['Ayşe','Mehmet']);self.assertEqual({p['name'] for p in snap['profiles']},{'Ayşe','Mehmet'})
            dispatch({'action':'label_speaker','meeting':mid,'speaker':'Konuşmacı 2','name':'Mehmet','enroll':True},db)  # idempotent
            self.assertEqual(len(dispatch({'action':'snapshot'},db)['profiles']),2)
            with self.assertRaises(ValueError):dispatch({'action':'label_speaker','meeting':mid,'speaker':'Yok','name':'X','enroll':True},db)
    def test_identity_failure_keeps_transcript_complete(self):
        class Broken:
            model_id='resemblyzer:test'
            def embed_file(self,path,spans):raise RuntimeError('worker died')
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=8);store=Store(Path(tmp)/'db.sqlite');mid=store.create_meeting('K',{'capture_dir':str(d)});store.status(mid,'incomplete')
            finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=LongFakeClient(),embedder=Broken())
            row=store.db.execute('SELECT status,metadata FROM meetings WHERE id=?',(mid,)).fetchone()
            self.assertEqual(row[0],'complete');self.assertIn('identity_error',json.loads(row[1]));self.assertEqual(len(store.segments(mid)),2);store.close()
    def test_light_guard_admits_warning_but_not_critical(self):
        from unittest.mock import patch
        from meeting_os.resources import check_pressure, MemoryPressureError
        from meeting_os.final_identity import FinalEmbedder
        with patch('subprocess.check_output',return_value=b'2'):
            with self.assertRaises(MemoryPressureError):check_pressure()
            check_pressure(allow_warning=True)
        with patch('subprocess.check_output',return_value=b'4'):
            with self.assertRaises(MemoryPressureError):check_pressure(allow_warning=True)
        with patch('meeting_os.final_identity.run_guarded') as rg, patch('meeting_os.final_identity._signature',return_value='s'), patch('meeting_os.final_identity._hash_file',return_value=('s','d'*16)), patch('meeting_os.final_identity.sf.info') as info, patch('meeting_os.final_identity.validate_vectors',return_value=[[0.0,1.0]]):
            info.return_value.samplerate=16000;info.return_value.channels=1;info.return_value.subtype='FLOAT';info.return_value.frames=16000*5
            import tempfile as tf
            with tf.TemporaryDirectory() as t:
                wav=Path(t)/'a.wav';sf.write(wav,np.zeros(16000*5,dtype='float32'),16000,subtype='FLOAT')
                def fake_run(cmd,timeout,light=False):Path(cmd[-1]).write_text('[[0.0,1.0]]')
                rg.side_effect=fake_run
                FinalEmbedder(model=str(wav),light=True).embed_file(wav,[(0,16000*4)])
                self.assertTrue(rg.call_args.kwargs['light'])

class MergeEchoTests(unittest.TestCase):
    def test_merge_joins_same_speaker_phrases_within_gap(self):
        segs=[{'start':0,'end':1.2,'text':'Selamlar,','speaker':'0'},{'start':1.3,'end':3.2,'text':'saygılar.','speaker':'0'},{'start':4.0,'end':4.9,'text':'','speaker':'0'},
              {'start':5.0,'end':6.0,'text':'Merhaba.','speaker':'1'},{'start':8.0,'end':9.0,'text':'Evet.','speaker':'1'}]
        self.assertEqual(merge_segments(segs),[{'start':0,'end':3.2,'text':'Selamlar, saygılar.','speaker':'0'},{'start':5.0,'end':6.0,'text':'Merhaba.','speaker':'1'},{'start':8.0,'end':9.0,'text':'Evet.','speaker':'1'}])
        long=[{'start':i*10,'end':i*10+9.5,'text':'x y','speaker':'0'} for i in range(5)]
        self.assertEqual([round(m['end']-m['start'],1) for m in merge_segments(long)],[29.5,19.5])
    def test_mic_bleed_is_flagged_but_real_mic_speech_is_not(self):
        from meeting_os.types import Segment
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite');mid=store.create_meeting('E',{})
            store.add_segment(mid,Segment(0,10,'Bakalım kimler var, neler konuşalım. Berna Hanım merhaba.','system','Konuşmacı 1'))
            echo=store.add_segment(mid,Segment(0,10,'Bakalım kimler var neler konuşalım Berna Hanım merhaba','mic','Boran'))
            real=store.add_segment(mid,Segment(12,20,'Ben bu konuda farklı düşünüyorum, rapor yarın hazır olur.','mic','Boran'))
            self.assertEqual(flag_echo(store,mid),1)
            rows={r['id']:r for r in store.segments(mid)}
            self.assertIn('possible_echo',rows[echo]['flags']);self.assertNotIn('possible_echo',rows[real]['flags'])
            self.assertEqual(flag_echo(store,mid),0);store.close()
    def test_hash_file_light_mode_tolerates_warning(self):
        from unittest.mock import patch
        from meeting_os.asr_checkpoints import _hash_file
        from meeting_os.resources import MemoryPressureError
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'w.pt';f.write_bytes(b'x'*10)
            with patch('meeting_os.resources.subprocess.check_output',return_value=b'2'):
                with self.assertRaises(MemoryPressureError):_hash_file(f)
                self.assertEqual(len(_hash_file(f,allow_warning=True)[1]),64)

class AssignmentTests(unittest.TestCase):
    def test_one_profile_names_only_its_best_cluster(self):
        a,b,c=[{'id':1}],[{'id':2}],[{'id':3}]
        scored=[(a,{'name':'Gözlük','similarity':0.837}),(b,{'name':'Gözlük','similarity':0.853}),(c,{'name':'Gözlük','similarity':0.954})]
        out=assign_identities(scored)
        self.assertEqual(out,{id(c):'Gözlük'})
        split=[(a,{'name':'Ayşe','similarity':0.95}),(b,{'name':'Ayşe','similarity':0.94}),(c,{'name':None,'similarity':0.5})]
        self.assertEqual(assign_identities(split),{id(a):'Ayşe',id(b):'Ayşe'})
        self.assertEqual(assign_identities([(a,{'name':None,'similarity':None})]),{})

class ReidentifyTests(unittest.TestCase):
    def test_already_embedded_clusters_are_still_matched(self):
        from meeting_os.cloud_finalize import identify_clusters
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=8);store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('K',{'capture_dir':str(d)});store.status(mid,'incomplete')
            finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=LongFakeClient(),embedder=FakeEmbedder())
            self.assertEqual([r['speaker_name'] for r in store.segments(mid)],[None,None])
            store.enroll('Ayşe',[1.0,0.0],'resemblyzer:test',4.0,'later')  # profile saved after the meeting was processed
            paths=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])['paths']
            self.assertEqual(identify_clusters(store,mid,paths,FakeEmbedder()),{'embedded':0,'named':1,'suggested':0,'fed':0})
            self.assertEqual([r['speaker_name'] for r in store.segments(mid)],['Ayşe',None]);store.close()

class WindowTests(unittest.TestCase):
    def test_long_turns_are_split_into_bounded_windows_and_clamped(self):
        from meeting_os.cloud_finalize import embedding_windows
        R=16000
        self.assertEqual(embedding_windows(0,76.1,R*141),[(0,30*R),(30*R,60*R),(60*R,round(76.1*R))])
        self.assertEqual(embedding_windows(0,31,R*141),[(0,31*R)])             # short tail folded in
        self.assertEqual(embedding_windows(139,141.4,R*141),[])                 # < 3 s after clamping → skipped
        self.assertEqual(embedding_windows(100,141.4,R*141),[(100*R,130*R),(130*R,141*R)])  # clamped to file length
        self.assertTrue(all(b-a<=60*R for a,b in embedding_windows(0,600,R*700)))

class EchoAnalysisTests(unittest.TestCase):
    def test_echo_rows_are_excluded_from_analysis_input(self):
        from unittest.mock import patch
        from meeting_os import assistant
        from meeting_os.types import Segment
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite');mid=store.create_meeting('E',{})
            store.add_segment(mid,Segment(0,10,'Karar: yarın rapor çıkacak.','system','Konuşmacı 1'))
            store.add_segment(mid,Segment(0,10,'Karar yarın rapor çıkacak','mic','Boran',flags=['possible_echo']))
            store.status(mid,'complete')
            seen={}
            def fake_analyze(rows,*a,**k):
                seen['rows']=rows
                raise RuntimeError('stop here')
            class Llm: model_id='fixture'
            with patch.object(assistant,'analyze_rows',fake_analyze):
                with self.assertRaises(RuntimeError): assistant.analyze(store,mid,Llm())
            self.assertEqual([r['source'] for r in seen['rows']],['system'])   # the echoed mic row never reaches the model
            self.assertNotIn('possible_echo',[f for r in seen['rows'] for f in r['flags']])
            store.close()

class BackchannelClient(FakeClient):
    def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90,**kw):
        self.calls.append({'diarize':diarize})
        return {'text':'x','usage':{'seconds':8},'segments':[{'start':0.0,'end':4.0,'text':'Uzun konuşma.','speaker':'0'},{'start':4.0,'end':5.5,'text':'Hı hı.','speaker':'1'},
                {'start':5.5,'end':6.0,'text':'Devam.','speaker':'0'},{'start':6.0,'end':8.0,'text':'Aynen öyle.','speaker':'1'}]}

class SnapshotEmbedder:
    model_id='resemblyzer:test'
    def __init__(self):self.calls=[]
    def embed_file(self,path,spans):
        self.calls.append((str(path),spans))
        return [[0.0,1.0] if 'cluster' in str(path) else [1.0,0.0] for _ in spans]

class ShortClusterTests(unittest.TestCase):
    def test_backchannel_cluster_is_embedded_from_concatenated_pieces_and_enrollable(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=8);db=Path(tmp)/'db.sqlite';store=Store(db)
            store.enroll('Sağ üst',[0.0,1.0],'resemblyzer:test',10.0,'earlier')
            mid=store.create_meeting('K',{'capture_dir':str(d)});store.status(mid,'incomplete')
            emb=SnapshotEmbedder();finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=BackchannelClient(),embedder=emb)
            rows=store.segments(mid)
            short=[r for r in rows if r['speaker']=='Konuşmacı 2']
            self.assertEqual(len(short),2);self.assertTrue(all(r['embedding']==[0.0,1.0] for r in short))
            self.assertEqual([r['speaker_name'] for r in short],['Sağ üst','Sağ üst'])
            self.assertEqual(short[0]['metrics']['cluster_embedding'],3.5)
            self.assertTrue(any('cluster.wav' in c[0] for c in emb.calls))
            store.close()
            result=dispatch({'action':'label_speaker','meeting':mid,'speaker':'Konuşmacı 2','name':'Sağ üst','enroll':True},db)
            self.assertTrue(result['profile_saved']);self.assertAlmostEqual(result['seconds'],3.5)

class TwoBackchannelClient(FakeClient):
    """Two clusters that never reach 3 s in one turn, so both need the concatenated path."""
    def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90,**kw):
        self.calls.append({'diarize':diarize})
        return {'text':'x','usage':{'seconds':8},'segments':[{'start':0.0,'end':1.2,'text':'Hı hı.','speaker':'0'},{'start':1.2,'end':2.4,'text':'Aynen.','speaker':'0'},
                {'start':4.0,'end':5.2,'text':'Tamam.','speaker':'1'},{'start':5.2,'end':6.4,'text':'Olur.','speaker':'1'}]}

class BatchedShortClusterTests(unittest.TestCase):
    def test_every_short_cluster_is_embedded_in_one_child_with_one_span_each(self):
        from meeting_os.cloud_finalize import embed_short_clusters
        class Batching:
            model_id='resemblyzer:test'
            def __init__(self):self.calls=[]
            def embed_file(self,path,spans):
                self.calls.append((str(path),list(spans)))
                return [[1.0,0.0] if a==0 else [0.0,1.0] for a,b in spans]
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=8);store=Store(Path(tmp)/'db.sqlite')
            store.enroll('Sağ üst',[0.0,1.0],'resemblyzer:test',10.0,'earlier')
            mid=store.create_meeting('K',{'capture_dir':str(d)});store.status(mid,'incomplete')
            emb=Batching();finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=TwoBackchannelClient(),embedder=emb)
            self.assertEqual(len(emb.calls),1)                     # one guarded child, not one per cluster
            path,spans=emb.calls[0]
            self.assertIn('cluster.wav',path);self.assertEqual(len(spans),2)
            self.assertEqual(spans[0][0],0);self.assertEqual(spans[1][0],spans[0][1])   # clusters appended back to back
            rows=store.segments(mid);by={}
            for r in rows: by.setdefault(r['speaker'],[]).append(r)
            self.assertTrue(by['Konuşmacı 1'] and all(r['embedding']==[1.0,0.0] for r in by['Konuşmacı 1']))
            self.assertTrue(by['Konuşmacı 2'] and all(r['embedding']==[0.0,1.0] for r in by['Konuşmacı 2']))
            self.assertTrue(all(r['speaker_name']=='Sağ üst' for r in by['Konuşmacı 2']))
            self.assertEqual(by['Konuşmacı 1'][0]['metrics']['cluster_embedding'],2.4)
            self.assertEqual(by['Konuşmacı 2'][0]['metrics']['cluster_embedding'],2.4)
            paths={'system':str(d/'system-000000.wav'),'mic':str(d/'mic-000000.wav')}
            self.assertEqual(embed_short_clusters(store,mid,paths,emb),0)   # already embedded: no further child
            self.assertEqual(len(emb.calls),1)
            store.close()
    def test_no_short_cluster_never_starts_a_child(self):
        from meeting_os.cloud_finalize import embed_short_clusters
        class Never:
            model_id='resemblyzer:test'
            def embed_file(self,path,spans):raise AssertionError('no short cluster to embed')
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=8);store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('K',{'capture_dir':str(d)});store.status(mid,'incomplete')
            self.assertEqual(embed_short_clusters(store,mid,{'system':str(d/'system-000000.wav')},Never()),0)
            store.close()

class SuggestionAndFeedingTests(unittest.TestCase):
    def test_identify_blends_centroid_and_nearest_sample_and_reports_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'db');s.enroll('Ayşe',[1.0,0.0],'m',5,'a');s.enroll('Ayşe',[0.6,0.8],'m',5,'b');s.enroll('Mehmet',[0.0,1.0],'m',5,'c')
            r=s.identify([1.0,0.0],'m',0.87,0.05)
            self.assertEqual(r['candidate'],'Ayşe');self.assertAlmostEqual(r['similarity'],(0.8944+1.0)/2,places=3)
            self.assertIsNone(s.identify([0.7,0.71],'m',0.99,0.05)['name']);self.assertIsNotNone(s.identify([0.7,0.71],'m',0.99,0.05)['candidate'])
            self.assertTrue(s.add_sample_if_new('Ayşe',[1,0],'m',12,'auto:x',cap=3));self.assertFalse(s.add_sample_if_new('Ayşe',[1,0],'m',12,'auto:x',cap=3))
            self.assertFalse(s.add_sample_if_new('Ayşe',[1,0],'m',12,'auto:y',cap=3));s.close()
    def test_borderline_match_becomes_suggestion_and_strong_match_feeds_profile(self):
        from meeting_os.cloud_finalize import identify_clusters
        class Emb:
            model_id='resemblyzer:test'
            def embed_file(self,path,spans):return [[0.95,0.3122] if a<16000*2 else [1.0,0.0] for a,b in spans]  # cluster0 ≈0.95 sim, cluster1 exact
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=40);store=Store(Path(tmp)/'db.sqlite')
            store.enroll('Ayşe',[1.0,0.0],'resemblyzer:test',10,'earlier')
            mid=store.create_meeting('K',{'capture_dir':str(d)});store.status(mid,'incomplete')
            class C(FakeClient):
                def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90,**kw):
                    return {'text':'x','usage':{},'segments':[{'start':0.0,'end':1.5,'text':'a b c','speaker':'0'},{'start':1.5,'end':3.6,'text':'d e f','speaker':'0'},{'start':4.0,'end':20.0,'text':'uzun','speaker':'1'}]}
            finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=C(),embedder=Emb())
            rows=store.segments(mid);by={r['speaker']:r for r in rows}
            k1=by['Konuşmacı 2'];self.assertEqual(k1['speaker_name'],'Ayşe');self.assertEqual(k1['metrics']['identity']['suggested'],None)
            self.assertEqual(len(store.db.execute("select * from samples where name='Ayşe'").fetchall()),2)  # fed automatically (16 s, exact match)
            disp={r['speaker']:r for r in store.display_segments(mid)}
            self.assertIn('suggested',disp['Konuşmacı 2']);store.close()
    def test_backchannels_skipped_for_analysis(self):
        from meeting_os.assistant import is_backchannel
        self.assertTrue(is_backchannel({'text':'Hı hı.','start':26.4,'end':27.2}))
        self.assertFalse(is_backchannel({'text':'Evet, ben.','start':0,'end':2.0}))
        self.assertTrue(is_backchannel({'text':'Tamam yarın.','start':0,'end':1.0}))
        self.assertFalse(is_backchannel({'text':'Yarın rapor hazır olur.','start':0,'end':1.0}))

class EchoSkipTests(unittest.TestCase):
    def make(self,tmp,mic_is_echo):
        d=Path(tmp)/'rec';d.mkdir();t=np.arange(16000*8)/16000;rng=np.random.default_rng(1)
        speech=(0.3*np.sin(2*np.pi*220*t)*(rng.random(len(t))>0.5)).astype('float32')   # bursty like speech
        for i in range(8):  # loudness pattern: on/off per second
            if i%2: speech[i*16000:(i+1)*16000]*=0.05
        system=speech
        mic=(0.4*np.roll(system,80)+0.02*rng.standard_normal(len(t))).astype('float32') if mic_is_echo else (0.3*np.sin(2*np.pi*330*t)*np.concatenate([np.ones(16000*4),np.zeros(16000*4)])).astype('float32')
        events=[]
        for source,signal in (('mic',mic),('system',system)):
            path=d/f'{source}-000000.wav';sf.write(path,signal,16000,subtype='FLOAT')
            events.append({'event':'chunk','source':source,'start':0,'duration':8,'path':str(path),'sample_rate':16000,'index':0})
        (d/'capture-native.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n');return d
    def test_echo_windows_are_not_uploaded_but_real_mic_speech_is(self):
        from meeting_os.cloud_finalize import envelope_correlation
        for echo in (True,False):
            with tempfile.TemporaryDirectory() as tmp:
                d=self.make(tmp,echo);store=Store(Path(tmp)/'db.sqlite');mid=store.create_meeting('E',{'capture_dir':str(d)});store.status(mid,'incomplete')
                client=FakeClient();finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=client)
                usage=[json.loads(u[0]) for u in store.db.execute('SELECT usage FROM cloud_chunks WHERE meeting=? ORDER BY position',(mid,))]
                mic_rows=[r for r in store.segments(mid) if r['source']=='mic']
                meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
                if echo:
                    self.assertEqual(usage[0],{'skipped':'echo'});self.assertEqual(mic_rows,[]);self.assertEqual(meta['echo_windows_skipped'],1);self.assertEqual(len(client.calls),1)
                else:
                    self.assertNotIn('skipped',usage[0]);self.assertEqual(len(mic_rows),1);self.assertEqual(meta['echo_windows_skipped'],0);self.assertEqual(len(client.calls),2)
                store.close()
        self.assertEqual(envelope_correlation(np.zeros(16000*4,dtype='float32'),np.ones(16000*4,dtype='float32')),0.0)

class CloudAnalysisWiringTests(unittest.TestCase):
    def test_models_and_token_estimate(self):
        from meeting_os.openrouter import validate_analysis_model, OpenRouterError, OpenRouterClient, ANALYSIS_DEFAULT_MODEL
        self.assertEqual(validate_analysis_model(ANALYSIS_DEFAULT_MODEL),'openai/gpt-4.1-mini')
        with self.assertRaises(OpenRouterError):validate_analysis_model('openai/gpt-4o')
        llm=OpenRouterClient(api_key='k',transport=lambda r,timeout:None).analysis('openai/gpt-4.1-mini',consent=True)
        self.assertEqual(llm.count('a'*300),100);self.assertEqual(llm.model_id,'openai/gpt-4.1-mini')
    def test_cli_cloud_analysis_skips_local_guard(self):
        import sys
        from unittest.mock import patch
        from meeting_os import cli
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'db.sqlite';Store(db).close()
            fake_llm=type('L',(),{'model_id':'openai/gpt-4.1-mini','count':lambda s,t:1,'complete':lambda s,*a,**k:'{}'})()
            with patch.object(sys,'argv',['meeting_os','--db',str(db),'analyze','nope','--openrouter-model','openai/gpt-4.1-mini']), patch('meeting_os.supervisor.run_guarded') as rg, patch('meeting_os.openrouter.OpenRouterClient') as oc:
                oc.return_value.analysis.return_value=fake_llm
                with self.assertRaises(SystemExit) as ex: cli.main()
                self.assertEqual(ex.exception.code,1)   # meeting not found -> plain error, but…
                rg.assert_not_called()                  # …no local-model guard and no supervised child were involved
                oc.return_value.analysis.assert_called_once_with('openai/gpt-4.1-mini',consent=True)

class QuoteLocateTests(unittest.TestCase):
    def test_model_quotes_map_back_to_exact_source_text(self):
        from meeting_os.intelligence import locate_quote
        text='Eee o onunla hiçbir ilgim yok. Sadece bu işte hangi servis hesabında, “Deep Work” diye bir kitap önerisinde bulunmuştum.'
        self.assertEqual(locate_quote('Sadece bu işte',text),'Sadece bu işte')
        self.assertEqual(locate_quote('sadece bu işte hangi servis hesabında',text),'Sadece bu işte hangi servis hesabında')
        self.assertEqual(locate_quote('Deep Work diye bir kitap önerisinde bulunmuştum',text),'Deep Work” diye bir kitap önerisinde bulunmuştum')  # exact source span, opening quote mark not required
        self.assertEqual(locate_quote('o onunla hiç ilgim yok',text),'o onunla hiçbir ilgim yok.')  # one dropped syllable, fuzzy
        self.assertIsNone(locate_quote('yarın rapor hazır olacak',text));self.assertIsNone(locate_quote('   ',text))

class QualitySetTests(unittest.TestCase):
    def test_wer_and_reference_set_and_identity_scorecard(self):
        from meeting_os.quality import wer, reference_set, identity_report, report, compare
        from meeting_os.types import Segment
        self.assertEqual(wer('Yarın rapor hazır olur.','yarın rapor hazır olur'),0.0);self.assertAlmostEqual(wer('a b c d','a x c'),0.5);self.assertEqual(wer('','x'),1.0)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');wav=Path(tmp)/'sys.wav';sf.write(wav,np.zeros(16000*5,dtype='float32'),16000,subtype='FLOAT')
            mid=store.create_meeting('Q',{'model':'microsoft/mai-transcribe-2','paths':{'system':str(wav)}})
            flags=['cloud_transcript','cloud_diarization']
            a=store.add_segment(mid,Segment(0,2,'yarın rapor hazır olsun','system','Konuşmacı 1',metrics={'cluster':'0:0','model':'microsoft/mai-transcribe-2','identity':{'name':'Ayşe'}},flags=flags))
            b=store.add_segment(mid,Segment(2,4,'tamam','system','Konuşmacı 2',metrics={'cluster':'0:1','identity':{'name':None,'suggested':'Mehmet'}},flags=flags))
            store.status(mid,'complete')
            store.correct_text(mid,a,'Yarın rapor hazır olur.')
            store.correct(mid,'Konuşmacı 1','Ali')          # auto name overridden -> wrong
            store.enroll_speaker(mid,'Konuşmacı 2','Mehmet') # suggestion confirmed
            refs=reference_set(store);self.assertEqual(len(refs),1);self.assertEqual(refs[0]['reference'],'Yarın rapor hazır olur.');self.assertAlmostEqual(refs[0]['wer'],0.25)
            rep=report(store);self.assertEqual(rep['text_edits'],1);self.assertEqual(rep['mean_wer_by_model'],{'microsoft/mai-transcribe-2':0.25})
            self.assertEqual((rep['wer'],rep['wer_no_filler'],rep['transcript_words'],rep['edits_per_1000_words']),(0.25,0.25,5,200.0))
            ident=rep['identity'];self.assertEqual((ident['auto_wrong'],ident['suggestion_confirmed'],ident['auto_precision']),(1,1,0.0))
            class C:
                hints=[]
                def transcribe(self,audio,fmt,*,model,consent,hint=None,**k):
                    self.hints.append(hint);return {'text':'Eee yarın rapor hazır olur' if 'mai' in model else 'yarin rapor','usage':{'cost':0.001}}
            out=compare(store,['microsoft/mai-transcribe-2','openai/whisper-large-v3'],C(),consent=True,encode=lambda p,a,b:b'OggS',hint='PMD, Trendyol')
            self.assertEqual(C.hints,['PMD, Trendyol']*2);self.assertTrue(out['hint'])
            self.assertEqual(out['segments'],1);self.assertEqual(out['models']['microsoft/mai-transcribe-2']['mean_wer'],0.25);self.assertEqual(out['models']['microsoft/mai-transcribe-2']['mean_wer_no_filler'],0.0)
            self.assertEqual(out['models']['openai/whisper-large-v3']['mean_wer'],0.75);self.assertEqual(out['stored_model_mean_wer_no_filler'],0.25)
            with self.assertRaises(Exception):compare(store,['x/y'],C(),consent=True)
            store.close()

class ReplayTests(unittest.TestCase):
    """Three people, four meetings, tiny 3-d voiceprints: a meeting must never vouch for itself."""
    def build(self,tmp):
        from meeting_os.types import Segment
        store=Store(Path(tmp)/'meeting-os.sqlite');flags=['cloud_transcript','cloud_diarization']
        def meeting(title,clusters):
            mid=store.create_meeting(title,{'model':'microsoft/mai-transcribe-2'});t=0
            for speaker,vec in clusters:
                store.add_segment(mid,Segment(t,t+10,'konuşma','system',speaker,metrics={'cluster':f'0:{t//10}'},flags=flags,embedding=vec,embedding_model='m'));t+=10
            store.status(mid,'complete');return mid
        m1=meeting('M1',[('Konuşmacı 1',[1.0,0.0,0.0]),('Konuşmacı 2',[0.0,1.0,0.0])]);store.enroll_speaker(m1,'Konuşmacı 1','Ayşe');store.enroll_speaker(m1,'Konuşmacı 2','Burak')
        m2=meeting('M2',[('Konuşmacı 1',[0.98,0.2,0.0]),('Konuşmacı 2',[0.0,0.0,1.0])]);store.enroll_speaker(m2,'Konuşmacı 1','Ayşe');store.enroll_speaker(m2,'Konuşmacı 2','Ceren')
        m3=meeting('M3',[('Konuşmacı 1',[0.0,0.97,0.24]),('Konuşmacı 2',[0.1,0.0,1.0])]);store.enroll_speaker(m3,'Konuşmacı 1','Burak');store.enroll_speaker(m3,'Konuşmacı 2','Ceren')
        # M4: Ayşe sounds like Burak here (the only sample that would rescue her comes from this very meeting); Ceren's cluster is Burak's exact voice
        m4=meeting('M4',[('Konuşmacı 1',[0.6,0.8,0.0]),('Konuşmacı 2',[0.0,1.0,0.0])]);store.enroll_speaker(m4,'Konuşmacı 1','Ayşe');store.correct(m4,'Konuşmacı 2','Ceren')
        store.add_sample_if_new('Ayşe',[0.6,0.8,0.0],'m',10,f'auto:{m4}:0:0')
        return store,(m1,m2,m3,m4)
    def test_identity_replay_excludes_own_meeting_samples(self):
        from meeting_os.quality import replay_identity, replay
        with tempfile.TemporaryDirectory() as tmp:
            store,(m1,m2,m3,m4)=self.build(tmp)
            self.assertEqual(store.identify([0.6,0.8,0.0],'m',0.87,0.05)['name'],'Ayşe')             # with its own samples the meeting names itself
            self.assertIsNone(store.identify([0.6,0.8,0.0],'m',0.87,0.05,exclude=m4)['name'])       # without them it is an honest miss
            out=replay_identity(store)
            self.assertEqual((out['clusters'],out['ok'],out['wrong'],out['missed'],out['abstained'],out['no_profile']),(8,6,1,1,0,0))
            self.assertEqual(out['people']['Ayşe'],{'ok':2,'wrong':0,'missed':1,'abstained':0,'no_profile':0});self.assertEqual(out['people']['Ceren']['wrong'],1)
            miss=[c for c in out['misses'] if c['outcome']=='missed'][0];self.assertEqual((miss['meeting'],miss['name'],miss['nearest'][0]['name']),(m4,'Ayşe','Burak'));self.assertLess(miss['score'],0.87)
            wrong=[c for c in out['misses'] if c['outcome']=='wrong'][0];self.assertEqual((wrong['name'],wrong['named']),('Ceren','Burak'))
            self.assertEqual(replay_identity(store,threshold=0.99)['ok'],2)   # tighter threshold: only exact voices survive
            summary,full=replay(store,tmp);self.assertEqual(summary['identity']['ok'],6);self.assertTrue(Path(summary['path']).is_file())
            self.assertEqual(json.loads(Path(summary['path']).read_text())['identity']['clusters'],8);store.close()
    def test_text_replay_drops_noop_pairs_and_ignores_fillers(self):
        from meeting_os.quality import replay_text, strip_fillers, wer_no_filler
        from meeting_os.types import Segment
        self.assertEqual(strip_fillers('Şimdi çok şey, eee az önce hoşuma giden de oydu.'),'Şimdi çok şey, az önce hoşuma giden de oydu.')
        self.assertEqual(strip_fillers('Eee uğraşmasak bile zaten hani kişi sayısından ııı dolayı.'),'uğraşmasak bile zaten hani kişi sayısından dolayı.')
        self.assertEqual(strip_fillers('Ee-commerce ve e-posta iyi.'),'Ee-commerce ve e-posta iyi.');self.assertEqual(strip_fillers('Bi- mesela ben.'),'mesela ben.')
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');mid=store.create_meeting('T',{'model':'microsoft/mai-transcribe-2'})
            a=store.add_segment(mid,Segment(0,2,'Yarın rapor hazır olur.','system','K1'));b=store.add_segment(mid,Segment(2,4,'Eee bugün ııı rapor hazır, bi- değil mi?','system','K1'));store.status(mid,'complete')
            store.correct_text(mid,a,'Yarın rapor hazır olsun.');store.correct_text(mid,a,'Yarın rapor hazır olur.')   # edited, then reverted: not a correction
            self.assertEqual(replay_text(store)['edits'],0)
            store.correct_text(mid,b,'Bugün rapor hazır, değil mi?')
            out=replay_text(store);self.assertEqual(out['edits'],1);self.assertGreater(out['mean_wer'],0);self.assertEqual(out['mean_wer_no_filler'],0.0)
            self.assertEqual(out['by_model']['microsoft/mai-transcribe-2']['mean_wer_no_filler'],0.0);self.assertEqual(wer_no_filler('Hı hı, tamam.','tamam'),0.0);store.close()

class PlanChangeTests(unittest.TestCase):
    def test_plan_change_is_adopted_when_only_skipped_chunks_exist(self):
        from meeting_os import cloud_finalize as cf
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=8);store=Store(Path(tmp)/'db.sqlite');mid=store.create_meeting('P',{'capture_dir':str(d)});store.status(mid,'incomplete')
            client=FakeClient(fail_at=1)
            with self.assertRaises(OpenRouterError):finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=client)
            self.assertEqual([json.loads(u[0]) for u in store.db.execute('SELECT usage FROM cloud_chunks WHERE meeting=?',(mid,))],[{'skipped':'silent'}])  # silent mic skipped, system failed
            original=cf.FINE_PIECE_SECONDS;cf.FINE_PIECE_SECONDS=4   # mic plan changes → different plan JSON
            try: finalize_capture(store,mid,tmp,consent=True,client=FakeClient())
            finally: cf.FINE_PIECE_SECONDS=original
            self.assertEqual(store.db.execute('SELECT status FROM meetings WHERE id=?',(mid,)).fetchone()[0],'complete');store.close()

class LinkClustersTests(unittest.TestCase):
    def test_same_voice_in_two_pieces_gets_one_label(self):
        from meeting_os.cloud_finalize import link_clusters
        from meeting_os.types import Segment
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');mid=store.create_meeting('L',{});flags=['cloud_transcript','cloud_diarization']
            def seg(a,b,sp,cl,vec):return Segment(a,b,'x','system',sp,metrics={'cluster':cl},flags=flags,embedding=vec,embedding_model='m')
            store.add_segment(mid,seg(0,10,'Konuşmacı 1-1','0:0',[1.0,0.0]))
            store.add_segment(mid,seg(10,20,'Konuşmacı 1-2','0:1',[0.0,1.0]))
            store.add_segment(mid,seg(300,310,'Konuşmacı 2-1','1:0',[0.05,1.0]))   # ≈ 0.998 to 0:1 → same person
            store.add_segment(mid,seg(310,320,'Konuşmacı 2-2','1:1',[0.7,0.7]))    # ≈ 0.7 to both → new person
            self.assertEqual(link_clusters(store,mid,'m'),4)
            labels={r['metrics']['cluster']:r['speaker'] for r in store.segments(mid)}
            self.assertEqual(labels,{'0:0':'Konuşmacı 1','0:1':'Konuşmacı 2','1:0':'Konuşmacı 2','1:1':'Konuşmacı 3'})
            self.assertEqual(link_clusters(store,mid,'m'),0);store.close()   # idempotent

class LinkedIdentityTests(unittest.TestCase):
    def test_linked_speaker_is_scored_and_named_as_one_cluster(self):
        """Three 5-minute pieces, one colleague: the provider restarts speaker numbers per piece, link_clusters joins them,
        and the identity must land on the whole linked speaker (and feed the profile with the linked duration), not on
        the single sub-cluster that happens to score best."""
        from meeting_os.cloud_finalize import identify_clusters
        from meeting_os.types import Segment
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');wav=Path(tmp)/'sys.wav';sf.write(wav,np.zeros(16000*2,dtype='float32'),16000,subtype='FLOAT')
            store.enroll('Ayşe',[1.0,0.0],'resemblyzer:test',10,'earlier')
            mid=store.create_meeting('L',{'paths':{'system':str(wav)}});flags=['cloud_transcript','cloud_diarization']
            def seg(a,b,sp,cl,vec):return Segment(a,b,'x','system',sp,metrics={'cluster':cl},flags=flags,embedding=vec,embedding_model='resemblyzer:test')
            store.add_segment(mid,seg(0,4,'Konuşmacı 1-1','0:0',[1.0,0.0]))          # exact
            store.add_segment(mid,seg(300,304,'Konuşmacı 2-1','1:0',[0.92,0.392]))   # 0.92 to the profile: linked (≥0.90) but alone not ≥0.93
            store.add_segment(mid,seg(600,604,'Konuşmacı 3-1','2:0',[0.95,0.312]))   # 0.95: linked, alone would not share the name (1.0-0.95>0.03)
            store.add_segment(mid,seg(605,609,'Konuşmacı 3-2','2:1',[0.0,1.0]))      # someone else
            out=identify_clusters(store,mid,{'system':str(wav)},FakeEmbedder())
            rows=store.segments(mid);named={r['metrics']['cluster']:r['speaker_name'] for r in rows}
            self.assertEqual({r['speaker'] for r in rows},{'Konuşmacı 1','Konuşmacı 2'})
            self.assertEqual(named,{'0:0':'Ayşe','1:0':'Ayşe','2:0':'Ayşe','2:1':None})
            self.assertEqual((out['named'],out['fed']),(3,1))   # 12 s linked ≥ FEED_MIN_SECONDS although every sub-cluster is 4 s
            ident={r['metrics']['identity']['similarity'] for r in rows if r['speaker']=='Konuşmacı 1'};self.assertEqual(len(ident),1)   # one score for the linked speaker
            self.assertEqual([s['provenance'] for s in store.db.execute("SELECT provenance FROM samples WHERE name='Ayşe'")],['earlier',f'auto:{mid}:0:0']);store.close()
    def test_conflicting_linked_speaker_still_abstains(self):
        from meeting_os.cloud_finalize import identify_clusters
        from meeting_os.types import Segment
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');wav=Path(tmp)/'sys.wav';sf.write(wav,np.zeros(16000*2,dtype='float32'),16000,subtype='FLOAT')
            store.enroll('Ayşe',[1.0,0.0],'resemblyzer:test',10,'a');store.enroll('Mehmet',[0.95,0.312],'resemblyzer:test',10,'b')   # two profiles 0.95 apart
            mid=store.create_meeting('C',{'paths':{'system':str(wav)}});flags=['cloud_transcript','cloud_diarization']
            store.add_segment(mid,Segment(0,20,'x','system','Konuşmacı 1',metrics={'cluster':'0:0'},flags=flags,embedding=[0.99,0.16],embedding_model='resemblyzer:test'))
            out=identify_clusters(store,mid,{'system':str(wav)},FakeEmbedder())
            r=store.segments(mid)[0];self.assertIsNone(r['speaker_name']);self.assertIsNone(r['metrics']['identity']['suggested']);self.assertLess(r['metrics']['identity']['margin'],0.05)
            self.assertEqual(out,{'embedded':0,'named':0,'suggested':0,'fed':0});store.close()

class UncertaintyFlagTests(unittest.TestCase):
    def test_cloud_information_flags_do_not_mark_items_for_review(self):
        from meeting_os.intelligence import uncertain
        self.assertFalse(uncertain({'flags':['cloud_transcript','cloud_diarization','confidence_unavailable','speaker_unverified','coarse_timing']}))
        self.assertTrue(uncertain({'flags':['cloud_transcript','speaker_ambiguous']}));self.assertFalse(uncertain({}))

class ParallelUploadTests(unittest.TestCase):
    def test_sibling_success_is_checkpointed_when_one_piece_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=95);store=Store(Path(tmp)/'db.sqlite');mid=store.create_meeting('P',{'capture_dir':str(d)});store.status(mid,'incomplete')
            calls=[]
            class C:
                def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90,**kw):
                    calls.append(len(audio))
                    if len(calls)==3: raise OpenRouterError('network')   # first upload of the last batch fails; its sibling must still be checkpointed
                    return {'text':'metin','usage':{'seconds':30,'cost':0.001}}
            with self.assertRaises(OpenRouterError):finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=C())
            paid=[json.loads(u[0]) for u in store.db.execute('SELECT usage FROM cloud_chunks WHERE meeting=? ORDER BY position',(mid,)) if 'cost' in u[0]]
            self.assertGreaterEqual(len(paid),2)   # pieces 1 and 3 of the batch survived the failure of piece 2
            before=len(calls);finalize_capture(store,mid,tmp,consent=True,client=C())
            self.assertEqual(store.db.execute('SELECT status FROM meetings WHERE id=?',(mid,)).fetchone()[0],'complete')
            self.assertLess(len(calls)-before,4)   # only the missing pieces were re-sent
            store.close()

class MarkerTests(unittest.TestCase):
    def test_markers_written_during_recording_land_in_metadata_and_review_queue(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=8);(d/'markers.jsonl').write_text('{"seconds":3.2,"kind":"decision","created":"x"}\n{"seconds":-1,"kind":"decision"}\n{"seconds":5,"kind":"nope"}\nbozuk\n')
            db=Path(tmp)/'db.sqlite';store=Store(db);mid=store.create_meeting('M',{'capture_dir':str(d)});store.status(mid,'incomplete')
            finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=LongFakeClient(),embedder=FakeEmbedder())
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0]);store.close()
            self.assertEqual(meta['markers'],[{'seconds':3.2,'kind':'decision','created':'x'}])
            q=dispatch({'action':'review_queue','meeting':mid},db)
            self.assertEqual(q['items'][0]['kind'],'marker');self.assertIn('Karar anı',q['items'][0]['reason']);self.assertEqual(q['items'][0]['start'],3.2)

class MarkerDriftTests(unittest.TestCase):
    """⌘M is stamped on the wall clock; the transcript runs on elapsed audio. Sleep and helper relaunches pull the
    two apart, and the journal's wall stamps are what puts a marker back on the sentence it was meant for."""
    ORIGIN=1_700_000_000.0
    def journal(self,root,chunks,*,stamped=True,name='rec'):
        d=Path(root)/name;d.mkdir()
        started={'event':'started','clock':'hostTime','sources':['mic','system']}
        if stamped: started['wall']=self.ORIGIN
        lines=[json.dumps(started)]
        for wall,start,duration in chunks:
            e={'event':'chunk','source':'system','index':0,'path':str(d/'x.wav'),'sample_rate':48000,'start':start,'duration':duration}
            if stamped: e['wall']=self.ORIGIN+wall
            lines.append(json.dumps(e))
        (d/'capture-native.jsonl').write_text('\n'.join(lines)+'\n')
        return d
    def markers(self,d,*wall_elapsed):
        (d/'markers.jsonl').write_text(''.join(json.dumps({'seconds':round(w,1),'kind':'decision','created':'x','wall':self.ORIGIN+w})+'\n' for w in wall_elapsed))
        from meeting_os.cloud_finalize import read_markers
        return read_markers(d)
    def steady(self,seconds):
        """Wall and audio in lockstep: a 12 s chunk every 12 s."""
        return [(t,t-12,12) for t in range(12,seconds+1,12)]
    def test_no_gap_leaves_the_marker_where_the_user_pressed_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self.journal(tmp,self.steady(120))
            self.assertEqual(self.markers(d,100.0),[{'seconds':100.0,'kind':'decision','created':'x'}])
    def test_five_minute_sleep_before_the_marker_moves_it_back_by_the_sleep(self):
        # 96 s of audio, a 300 s lid-close the audio clock never counted, then the recording carries on.
        chunks=self.steady(96)+[(396+12*k,96+12*(k-1),12) for k in range(1,10)]
        with tempfile.TemporaryDirectory() as tmp:
            d=self.journal(tmp,chunks)
            self.assertEqual(self.markers(d,500.0),[{'seconds':200.0,'kind':'decision','created':'x','wall_seconds':500.0}])
    def test_a_gap_after_the_marker_does_not_touch_it(self):
        chunks=self.steady(96)+[(396+12*k,96+12*(k-1),12) for k in range(1,10)]
        with tempfile.TemporaryDirectory() as tmp:
            d=self.journal(tmp,chunks)
            self.assertEqual(self.markers(d,50.0),[{'seconds':50.0,'kind':'decision','created':'x'}])
    def test_relaunch_splice_is_subtracted_like_a_sleep(self):
        # The helper dies at 60 s; the replacement is handed --start-offset 60 twenty seconds later, so those
        # twenty wall seconds are spliced out of the audio timeline exactly as sleep is.
        chunks=self.steady(60)+[(80+12*k,60+12*(k-1),12) for k in range(1,6)]
        with tempfile.TemporaryDirectory() as tmp:
            d=self.journal(tmp,chunks)
            self.assertEqual(self.markers(d,120.0),[{'seconds':100.0,'kind':'decision','created':'x','wall_seconds':120.0}])
    def test_write_latency_is_not_mistaken_for_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self.journal(tmp,[(t+0.4,t-12,12) for t in range(12,121,12)])
            self.assertEqual(self.markers(d,100.0)[0]['seconds'],100.0)
    def test_a_journal_without_wall_stamps_leaves_every_marker_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self.journal(tmp,self.steady(120),stamped=False)
            from meeting_os.cloud_finalize import wall_audio_drift
            self.assertEqual(wall_audio_drift(d),(None,[]))
            self.assertEqual(self.markers(d,100.0),[{'seconds':100.0,'kind':'decision','created':'x'}])
    def test_an_old_marker_without_its_own_wall_stamp_still_gets_corrected(self):
        chunks=self.steady(96)+[(396+12*k,96+12*(k-1),12) for k in range(1,10)]
        with tempfile.TemporaryDirectory() as tmp:
            d=self.journal(tmp,chunks)
            (d/'markers.jsonl').write_text(json.dumps({'seconds':500.0,'kind':'task','created':'x'})+'\n')
            from meeting_os.cloud_finalize import read_markers
            self.assertEqual(read_markers(d),[{'seconds':200.0,'kind':'task','created':'x','wall_seconds':500.0}])

class EvidenceDropTests(unittest.TestCase):
    def test_unlocatable_quote_drops_the_evidence_not_the_analysis(self):
        from meeting_os.intelligence import validate_record
        rows=[{'id':1,'start':0,'end':5,'text':'Yarın raporu ben çıkaracağım.','source':'system','speaker':'A','speaker_name':'Ayşe','flags':[]},
              {'id':2,'start':5,'end':9,'text':'iOS önce gidecek.','source':'system','speaker':'B','speaker_name':None,'flags':[]}]
        record={'summary':[{'text':'Rapor yarın.','evidence':[{'segment_id':1,'quote':'yarın raporu ben çıkaracağım'},{'segment_id':2,'quote':'tamamen uydurma bir cümle burada'}]},
                           {'text':'Uydurma madde','evidence':[{'segment_id':2,'quote':'hiç yok böyle bir şey'}]}],'decisions':[],'risks':[],'questions':[],'actions':[]}
        out=validate_record(record,rows)
        self.assertEqual(len(out['summary']),1);self.assertEqual(out['summary'][0]['evidence'][0]['quote'],'Yarın raporu ben çıkaracağım')
        self.assertEqual((out['dropped_quotes'],out['dropped_items']),(2,1))
        with self.assertRaises(ValueError):validate_record({'summary':[{'text':'x','evidence':[{'segment_id':2,'quote':'yok'}]}],'decisions':[],'risks':[],'questions':[],'actions':[]},rows)

class GlossaryTests(unittest.TestCase):
    LINES=[{'term':'PMD','expansion':'Product Management Daily','category':'kısaltma','aliases':['pi em di'],'mishearings':['pemede','PMB'],'context':'günlük ürün toplantısı'},
           {'term':'Trendyol','category':'müşteri','mishearings':['trend yol','trendiyol']},{'term':'','category':'x'},{'nope':1}]
    def write(self,tmp):
        (Path(tmp)/'g.jsonl').write_text('\n'.join(json.dumps(l,ensure_ascii=False) for l in self.LINES)+'\nbozuk satır\n',encoding='utf-8');return Path(tmp)/'g.jsonl'
    def test_import_load_hint_and_context(self):
        from meeting_os import glossary as G
        with tempfile.TemporaryDirectory() as tmp:
            r=G.import_file(self.write(tmp),tmp);self.assertEqual((r['imported'],r['skipped'],r['shared']),(2,3,False))
            (Path(tmp)/'vocabulary.txt').write_text('Boran\nPMD\n# yorum\n')
            entries=G.load(tmp,tmp);self.assertEqual([e['term'] for e in entries],['PMD','Trendyol','Boran'])
            self.assertEqual(G.stt_hint(entries),'PMD, Trendyol, Boran');self.assertEqual(G.analysis_context(entries)[0]['expansion'],'Product Management Daily')
            with self.assertRaises(ValueError):G.import_file(Path(tmp)/'vocabulary.txt',tmp)
    def test_candidates_apply_and_review(self):
        from meeting_os import glossary as G
        from meeting_os.desktop import dispatch
        from meeting_os.types import Segment
        with tempfile.TemporaryDirectory() as tmp:
            G.import_file(self.write(tmp),tmp);entries=[e for e in G.load(tmp) if e['term'] in ('PMD','Trendyol')]
            db=Path(tmp)/'meeting-os.sqlite';s=Store(db);mid=s.create_meeting('G',{})
            a=s.add_segment(mid,Segment(0,5,'Bugün pemede toplantısında trend yol için karar aldık.','system','K1'))
            b=s.add_segment(mid,Segment(5,9,'PMD notları hazır, trendler iyi.','system','K1'));s.status(mid,'complete')
            cands=G.candidates(s.segments(mid),entries)
            self.assertEqual({(c['segment_id'],c['original'],c['replacement']) for c in cands},{(a,'pemede','PMD'),(a,'trend yol','Trendyol')})
            class LLM:
                model_id='m'
                def count(self,t):return 1
                def complete(self,system,user,max_tokens=0,schema=None):
                    return json.dumps({'decisions':[{'segment_id':a,'original':'pemede','accept':True,'reason':'kısaltma'},{'segment_id':a,'original':'trend yol','accept':False,'reason':'genel ifade'}]})
            refined=G.suggest_for_meeting(s,mid,entries,LLM());self.assertEqual([(r['original'],r['source']) for r in refined],[('pemede','llm')]);s.close()
            q=dispatch({'action':'review_queue','meeting':mid},db);g=[i for i in q['items'] if i['kind']=='glossary'];self.assertEqual(len(g),1);self.assertIn('PMD',g[0]['reason']);self.assertTrue(g[0]['verified'])
            r=dispatch({'action':'glossary_apply','meeting':mid,'segment':a,'original':'pemede','replacement':'PMD'},db);self.assertEqual(r,{'applied':True,'remaining':0})
            s=Store(db);row=[x for x in s.segments(mid) if x['id']==a][0];self.assertTrue(row['text'].startswith('Bugün PMD toplantısında'));self.assertEqual(row['original_text'],'Bugün pemede toplantısında trend yol için karar aldık.');s.close()
            summary=dispatch({'action':'glossary_summary'},db);self.assertEqual(summary['from_file'],2);self.assertEqual(summary['count'],2+summary['from_vocabulary'])
    def test_apply_all_and_dismiss(self):
        from meeting_os import glossary as G
        from meeting_os.desktop import dispatch
        from meeting_os.types import Segment
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'meeting-os.sqlite';s=Store(db);mid=s.create_meeting('G',{})
            a=s.add_segment(mid,Segment(0,5,'pemede toplantısı ve trend yol.','system','K1'));b=s.add_segment(mid,Segment(5,9,'yine pemede.','system','K1'));s.status(mid,'complete')
            meta=json.loads(s.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            meta['glossary_suggestions']=[{'segment_id':a,'original':'pemede','replacement':'PMD','source':'llm'},{'segment_id':a,'original':'trend yol','replacement':'Trendyol','source':'local'},
                                          {'segment_id':b,'original':'pemede','replacement':'PMD','source':'llm'},{'segment_id':b,'original':'yok','replacement':'X','source':'llm'}]
            with s.db:s.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta),mid))
            s.close()
            r=dispatch({'action':'glossary_apply_all','meeting':mid},db);self.assertEqual((r['applied'],r['skipped'],r['remaining']),(2,1,1))
            s=Store(db);texts={x['id']:x['text'] for x in s.segments(mid)};s.close();self.assertEqual((texts[a],texts[b]),('PMD toplantısı ve trend yol.','yine PMD.'))
            r=dispatch({'action':'glossary_dismiss','meeting':mid,'segment':a,'original':'trend yol'},db);self.assertEqual(r,{'dismissed':1,'remaining':0})
            self.assertEqual([i for i in dispatch({'action':'review_queue','meeting':mid},db)['items'] if i['kind']=='glossary'],[])
            self.assertEqual(dispatch({'action':'glossary_apply_all','meeting':mid,'verified_only':False},db)['applied'],0)
    def test_stt_hint_only_for_prompt_models(self):
        from meeting_os.openrouter import OpenRouterClient
        bodies=[]
        def transport(req,timeout):
            bodies.append(json.loads(req.data))
            class R:
                def __enter__(self):return self
                def __exit__(self,*a):pass
                def read(self,n):return json.dumps({'text':'x','usage':{}}).encode()
            return R()
        c=OpenRouterClient(api_key='k',transport=transport)
        c.transcribe(b'OggS','ogg',model='openai/gpt-transcribe',consent=True,hint='PMD, Trendyol');c.transcribe(b'OggS','ogg',model='microsoft/mai-transcribe-2',consent=True,hint='PMD')
        self.assertEqual(bodies[0]['prompt'],'PMD, Trendyol');self.assertNotIn('prompt',bodies[1])

class CompactTests(unittest.TestCase):
    def test_chunks_are_removed_after_completion_and_full_files_stay(self):
        from meeting_os.cloud_finalize import compact_capture
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=8);store=Store(Path(tmp)/'db.sqlite');mid=store.create_meeting('C',{'capture_dir':str(d)});store.status(mid,'incomplete')
            finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=LongFakeClient(),embedder=FakeEmbedder())
            names=sorted(p.name for p in d.iterdir())
            self.assertIn('system-full.flac',names);self.assertIn('mic-full.flac',names);self.assertNotIn('system-full.wav',names);self.assertNotIn('system-000000.wav',names);self.assertNotIn('mic-000000.wav',names);self.assertIn('capture-native.jsonl',names)
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0]);self.assertEqual(meta['chunks_removed'],2)
            self.assertEqual(compact_capture(store,mid),0)   # idempotent
            store.close()

    def test_half_written_partial_chunks_are_swept_too(self):
        """`mic-000003.partial.wav` is what a killed helper leaves behind. Nothing else ever removed it, so
        it sat in the folder for the life of the meeting even though its audio is in the assembled file."""
        from meeting_os.cloud_finalize import compact_capture
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=8);store=Store(Path(tmp)/'db.sqlite');mid=store.create_meeting('C',{'capture_dir':str(d)});store.status(mid,'incomplete')
            (d/'mic-000003.partial.wav').write_bytes(b'x'*2048)
            finalize_capture(store,mid,tmp,consent=True,model='deepgram/nova-3',client=LongFakeClient(),embedder=FakeEmbedder())
            names=sorted(p.name for p in d.iterdir())
            self.assertNotIn('mic-000003.partial.wav',names)
            self.assertEqual(json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])['chunks_removed'],3)
            store.close()


class JobPriorityTests(unittest.TestCase):
    def test_low_priority_flag_means_one_uploader_and_is_reported(self):
        import os
        from unittest.mock import patch
        from meeting_os import cloud_finalize as CF
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop('MEETING_OS_LOW_PRIORITY',None)
            self.assertEqual(CF.upload_workers(),CF.UPLOAD_WORKERS)
            u=CF.job_usage(__import__('time').monotonic()-2.0)
            self.assertFalse(u['low_priority']);self.assertGreaterEqual(u['wall_seconds'],2.0);self.assertGreater(u['peak_rss_mb'],0);self.assertGreaterEqual(u['cpu_seconds'],0)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'MEETING_OS_LOW_PRIORITY_FLAG':tmp+'/low.flag'}):
            os.environ.pop('MEETING_OS_LOW_PRIORITY',None)
            self.assertEqual(CF.upload_workers(),CF.UPLOAD_WORKERS)
            Path(tmp,'low.flag').write_text('');self.assertEqual(CF.upload_workers(),1)   # flag dropped mid-job
        with patch.dict(os.environ,{'MEETING_OS_LOW_PRIORITY':'1'}):
            os.environ.pop('MEETING_OS_LOW_PRIORITY_FLAG',None)
            # Low priority alone is the idle retry queue: nothing is on screen, so two uploaders, not one.
            self.assertEqual(CF.upload_workers(),CF.LOW_PRIORITY_WORKERS)
            self.assertEqual((CF.job_usage(0)['low_priority'],CF.job_usage(0)['upload_workers']),(True,CF.LOW_PRIORITY_WORKERS))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'MEETING_OS_LOW_PRIORITY':'1','MEETING_OS_LOW_PRIORITY_FLAG':tmp+'/low.flag'}):
            self.assertEqual(CF.upload_workers(),CF.LOW_PRIORITY_WORKERS)
            Path(tmp,'low.flag').write_text('')   # a meeting is on screen right now: one at a time
            self.assertEqual(CF.upload_workers(),1)


class CloudFailureTests(unittest.TestCase):
    """T7: OpenRouter down, key invalid or credit exhausted must never cost a meeting."""

    def _meeting(self,tmp,seconds=95):
        d=capture_dir(tmp,seconds=seconds);store=Store(Path(tmp)/'db.sqlite')
        mid=store.create_meeting('Kritik toplantı',{'capture_dir':str(d)});store.status(mid,'incomplete')
        return store,mid

    def test_rate_limit_is_retried_twice_and_every_paid_piece_is_kept(self):
        from unittest.mock import patch
        from meeting_os.openrouter import CloudUnavailable
        with tempfile.TemporaryDirectory() as tmp:
            store,mid=self._meeting(tmp,seconds=35)
            calls=[];waits=[]
            class C:
                def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90,**kw):
                    calls.append(1)
                    if len(calls)<=2: raise CloudUnavailable('OpenRouter HTTP 429.')   # the first piece is refused twice
                    return {'text':'metin','usage':{'seconds':30,'cost':0.001}}
            with patch('time.sleep',waits.append):
                finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=C())
            self.assertEqual(store.db.execute('SELECT status FROM meetings WHERE id=?',(mid,)).fetchone()[0],'complete')
            self.assertEqual(len(calls),4)                       # 2 pieces + 2 refusals
            self.assertEqual(len(waits),2)                       # 2 s then 8 s, plus up to 25% jitter
            self.assertTrue(all(b<=w<=b*1.25 for w,b in zip(waits,(2,8))),waits)
            paid=[u for (u,) in store.db.execute('SELECT usage FROM cloud_chunks WHERE meeting=?',(mid,)) if '"cost"' in (u or '')]
            self.assertEqual(len(paid),2)
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertNotIn('cloud_error',meta);self.assertNotIn('cloud_retry_after',meta)
            store.close()

    def test_invalid_key_is_not_retried_and_is_written_down_as_auth(self):
        from unittest.mock import patch
        from meeting_os.openrouter import CloudAuthError
        with tempfile.TemporaryDirectory() as tmp:
            store,mid=self._meeting(tmp,seconds=35)
            calls=[];waits=[]
            class C:
                def transcribe(self,*a,**kw):
                    calls.append(1);raise CloudAuthError('OpenRouter HTTP 401.')
            with patch('time.sleep',waits.append), self.assertRaises(CloudAuthError):
                finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=C())
            self.assertEqual(waits,[])                    # a wrong key does not get better by waiting
            self.assertEqual(len(calls),1)
            row=store.db.execute('SELECT status,metadata FROM meetings WHERE id=?',(mid,)).fetchone()
            self.assertEqual(row['status'],'incomplete');meta=json.loads(row['metadata'])
            self.assertEqual(meta['cloud_error']['kind'],'auth')
            self.assertEqual(meta['cloud_error']['message'],'OpenRouter anahtarı geçersiz — Ayarlar → OpenRouter')
            self.assertEqual(meta['cloud_retry_attempt'],1);self.assertIn('cloud_retry_after',meta)
            self.assertTrue(Path(meta['capture_dir']).is_dir())   # the audio is still there
            store.close()

    def test_exhausted_credit_is_written_down_as_credit(self):
        from meeting_os.openrouter import CloudCreditError
        with tempfile.TemporaryDirectory() as tmp:
            store,mid=self._meeting(tmp,seconds=35)
            class C:
                def transcribe(self,*a,**kw):raise CloudCreditError('OpenRouter HTTP 402.')
            with self.assertRaises(CloudCreditError):
                finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=C())
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual((meta['cloud_error']['kind'],meta['cloud_error']['message']),('credit','OpenRouter kredisi bitti'))
            store.close()

    def test_connection_loss_exhausts_the_retries_then_schedules_the_next_try(self):
        from datetime import datetime, timezone
        from unittest.mock import patch
        from meeting_os.openrouter import CloudUnavailable
        with tempfile.TemporaryDirectory() as tmp:
            store,mid=self._meeting(tmp,seconds=35)
            calls=[];waits=[]
            class C:
                def transcribe(self,*a,**kw):
                    calls.append(1);raise CloudUnavailable('bağlantı yok')
            with patch('time.sleep',waits.append), self.assertRaises(CloudUnavailable):
                finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=C())
            self.assertEqual(len(waits),3)                         # three waits, then the batch gives up
            self.assertTrue(all(b<=w<=b*1.25 for w,b in zip(waits,(2,8,20))),waits)
            self.assertEqual(len(calls),4)
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['cloud_error']['kind'],'unavailable')
            self.assertEqual(meta['cloud_retry_attempt'],1)
            minutes=(datetime.fromisoformat(meta['cloud_retry_after'])-datetime.now(timezone.utc)).total_seconds()/60
            self.assertTrue(9<minutes<=10,minutes)               # first backoff is 10 minutes
            # A second failure moves the next try out to 30 minutes; the audio is never touched.
            with patch('time.sleep',waits.append), self.assertRaises(CloudUnavailable):
                finalize_capture(store,mid,tmp,consent=True,client=C())
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['cloud_retry_attempt'],2)
            self.assertTrue(29<(datetime.fromisoformat(meta['cloud_retry_after'])-datetime.now(timezone.utc)).total_seconds()/60<=30)
            self.assertTrue(Path(meta['capture_dir']).is_dir())
            store.close()

    def _meta(self,store,mid):
        return json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])

    def test_the_attempt_is_counted_when_it_starts_so_a_kill_still_counts(self):
        """cloud_retry_attempt was only written by note_cloud_failure. A SIGKILL, a power cut or a kernel panic
        never reaches it, so a meeting that takes the helper down every time was offered to the idle queue for
        ever and MAX_CLOUD_RETRIES never bit."""
        from unittest.mock import patch
        from meeting_os.openrouter import CloudUnavailable
        with tempfile.TemporaryDirectory() as tmp:
            store,mid=self._meeting(tmp,seconds=35)
            class C:
                def transcribe(self,*a,**kw):raise CloudUnavailable('bağlantı yok')
            for expected in (1,2):
                # note_cloud_failure suppressed: a process the kernel killed never gets to run it either
                with patch('time.sleep',lambda s: None),patch('meeting_os.cloud_finalize.note_cloud_failure',return_value=None), \
                     self.assertRaises(CloudUnavailable):
                    finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=C())
                meta=self._meta(store,mid)
                self.assertEqual(meta['cloud_retry_attempt'],expected)
                self.assertTrue(meta['cloud_attempt_open'])   # the mark a finished attempt would have cleared
            store.close()

    def test_a_started_attempt_is_not_counted_twice_by_the_failure_that_follows(self):
        from unittest.mock import patch
        from meeting_os.openrouter import CloudUnavailable
        with tempfile.TemporaryDirectory() as tmp:
            store,mid=self._meeting(tmp,seconds=35)
            class C:
                def transcribe(self,*a,**kw):raise CloudUnavailable('bağlantı yok')
            with patch('time.sleep',lambda s: None), self.assertRaises(CloudUnavailable):
                finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=C())
            meta=self._meta(store,mid)
            self.assertEqual(meta['cloud_retry_attempt'],1);self.assertNotIn('cloud_attempt_open',meta)
            store.close()

    def test_a_cancel_closes_the_attempt_so_the_next_failure_counts_itself(self):
        from meeting_os.cloud_finalize import note_cloud_cancel, note_cloud_failure
        from meeting_os.openrouter import CloudUnavailable
        with tempfile.TemporaryDirectory() as tmp:
            store,mid=self._meeting(tmp,seconds=35)
            with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps({'cloud_retry_attempt':1,'cloud_attempt_open':True}),mid))
            note_cloud_cancel(store,mid)
            self.assertNotIn('cloud_attempt_open',self._meta(store,mid))
            note_cloud_failure(store,mid,CloudUnavailable('bağlantı yok'))
            self.assertEqual(self._meta(store,mid)['cloud_retry_attempt'],2)
            store.close()

    def test_a_finished_meeting_forgets_the_counter_and_the_open_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,mid=self._meeting(tmp,seconds=35)
            class C:
                def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90,**kw):
                    return {'text':'metin','usage':{'seconds':30,'cost':0.001}}
            finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=C())
            meta=self._meta(store,mid)
            self.assertNotIn('cloud_retry_attempt',meta);self.assertNotIn('cloud_attempt_open',meta)
            store.close()

    def test_backoff_ladder_caps_at_a_day_and_attempts_are_capped(self):
        from meeting_os.cloud_finalize import backoff_minutes, MAX_CLOUD_RETRIES
        self.assertEqual([backoff_minutes(n) for n in (1,2,3,4,5,30)],[10,30,120,360,1440,1440])
        self.assertEqual(MAX_CLOUD_RETRIES,30)
