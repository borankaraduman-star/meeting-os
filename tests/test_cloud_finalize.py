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
    def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90):
        self.calls.append({'bytes':len(audio),'format':fmt,'model':model,'diarize':diarize,'timeout':timeout})
        if self.fail_at==len(self.calls):raise OpenRouterError('network')
        if diarize:return {'text':'Merhaba. Selam.','usage':{'seconds':4,'cost':.0003},'segments':[{'start':0.0,'end':1.5,'text':'Merhaba.','speaker':'0'},{'start':1.6,'end':3.0,'text':'Selam.','speaker':'1'}]}
        return {'text':'Tek parça metin.','usage':{'seconds':4,'cost':.0003}}

class CloudFinalizeTests(unittest.TestCase):
    def test_pieces_and_labels(self):
        self.assertEqual(pieces(2500,1200),[(0,1200),(1200,2400),(2400,2500)])
        self.assertEqual(speaker_label('mic','3',0,False),'Boran');self.assertEqual(speaker_label('system','0',0,False),'Konuşmacı 1')
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
    def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90):
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
            self.assertEqual(result,{'labeled':1,'profile_saved':True,'seconds':3.5})
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
            def fake_analyze(rows,*a,**k): seen['rows']=rows; raise RuntimeError('stop here')
            with patch.object(assistant,'analyze_rows',fake_analyze,create=True):
                src=Path(assistant.__file__).read_text()
            self.assertIn("'possible_echo' not in r['flags']",src)
            rows=[r for r in store.display_segments(mid) if 'possible_echo' not in r['flags']]
            self.assertEqual([r['source'] for r in rows],['system']);store.close()

class BackchannelClient(FakeClient):
    def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90):
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
                def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90):
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
            ident=rep['identity'];self.assertEqual((ident['auto_wrong'],ident['suggestion_confirmed'],ident['auto_precision']),(1,1,0.0))
            class C:
                def transcribe(self,audio,fmt,*,model,consent,**k):return {'text':'Yarın rapor hazır olur' if 'mai' in model else 'yarin rapor','usage':{'cost':0.001}}
            out=compare(store,['microsoft/mai-transcribe-2','openai/whisper-large-v3'],C(),consent=True,encode=lambda p,a,b:b'OggS')
            self.assertEqual(out['segments'],1);self.assertEqual(out['models']['microsoft/mai-transcribe-2']['mean_wer'],0.0);self.assertEqual(out['models']['openai/whisper-large-v3']['mean_wer'],0.75)
            with self.assertRaises(Exception):compare(store,['x/y'],C(),consent=True)
            store.close()

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
