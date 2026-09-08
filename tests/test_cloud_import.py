import tempfile
import unittest
from unittest.mock import patch, Mock
from pathlib import Path
import numpy as np
import soundfile as sf
from meeting_os.store import Store
from meeting_os.cloud_import import transcribe_prepared, windows
from meeting_os.openrouter import OpenRouterError

class CloudImportTests(unittest.TestCase):
    def test_overlap_is_not_sent_twice_or_assigned_to_one_person(self):
        result=windows([(0,3,'S0'),(2,4,'S1')],4)
        self.assertEqual(result,[(0,2,'S0'),(2,3,'unknown'),(3,4,'S1')])
    def test_partial_checkpoint_resume_and_source_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'audio.wav';sf.write(path,np.zeros(16000*4),16000,subtype='FLOAT')
            store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Test',{'engine':'openrouter'})
            class Client:
                calls=0
                def transcribe(self,*args,**kwargs):
                    self.calls+=1
                    if self.calls==2:raise OpenRouterError('network')
                    return {'text':'Sprint hedefi.', 'usage':{'cost':.001}}
            client=Client();turns=[(0,2,'S0'),(2,4,'S1')]
            with self.assertRaises(OpenRouterError):transcribe_prepared(store,mid,path,turns,client,consent=True)
            self.assertEqual(len(store.segments(mid)),1)
            transcribe_prepared(store,mid,path,turns,client,consent=True)
            self.assertEqual(client.calls,3);self.assertEqual(len(store.segments(mid)),2)
            self.assertIn('coarse_timing',store.segments(mid)[0]['flags'])
            self.assertIsNone(store.segments(mid)[0]['speaker_name'])
            sf.write(path,np.ones(16000*4),16000,subtype='FLOAT')
            with self.assertRaises(ValueError):transcribe_prepared(store,mid,path,turns,client,consent=True)
            store.close()
    def test_consent_required_before_any_request(self):
        with self.assertRaises(OpenRouterError):transcribe_prepared(None,None,None,None,None,consent=False)

    def test_forty_minute_plan_is_bounded(self):
        plan=windows([(0,2400,'S0')],2400)
        self.assertEqual(len(plan),80)
        self.assertEqual(sum(b-a for a,b,_ in plan),2400)
        self.assertTrue(all(b-a<=30 for a,b,_ in plan))

    def test_file_workflow_preserves_model_audio_and_profiles(self):
        from meeting_os.cloud_import import import_file
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'test.wav';sf.write(source,np.zeros(16000*4),16000,subtype='FLOAT')
            original=source.read_bytes();store=Store(root/'db.sqlite')
            client=Mock();client.transcribe.return_value={'text':'Boran taslağı yarın hazırlayacak.','usage':{'cost':.001}}
            def convert(args,**kwargs):
                import shutil
                shutil.copyfile(source,args[-1]);return Mock(returncode=0)
            with patch('meeting_os.recovery.current_job_metadata',return_value={'worker_pid':123}), patch('meeting_os.cloud_import.subprocess.run',side_effect=convert), patch('meeting_os.isolated_diarization.isolated_file_turns',return_value=[(0,4,'system:S0')]), patch('meeting_os.final_identity.FinalEmbedder') as embedding:
                embedding.return_value.embed_file.return_value=[None]
                result=import_file(store,source,'Test',root/'data',consent=True,client=client)
                mid=result['meeting']
                self.assertEqual(store.meetings()[0]['status'],'complete')
                self.assertEqual(store.profiles(),[])
                self.assertEqual(source.read_bytes(),original)
                self.assertEqual(client.transcribe.call_args.kwargs['model'],'openai/gpt-transcribe')
                self.assertTrue(Path(__import__('json').loads(store.meetings()[0]['metadata'])['paths']['system']).exists())
                import_file(store,None,'Test',root/'data',consent=True,resume=mid,client=client)
                self.assertEqual(client.transcribe.call_count,1)
            store.close()
