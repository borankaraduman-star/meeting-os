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
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0]);self.assertEqual(meta['identity'],{'embedded':2,'named':1})
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
            self.assertEqual(identify_clusters(store,mid,paths,FakeEmbedder()),{'embedded':0,'named':1})
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
