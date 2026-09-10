import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from meeting_os.openrouter import OpenRouterClient, OpenRouterError, read_api_key


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class OpenRouterTests(unittest.TestCase):
    def client(self, result):
        self.requests = []
        def transport(request, timeout):
            self.requests.append((request, timeout))
            return Response(json.dumps(result).encode())
        return OpenRouterClient('secret-not-for-logs', transport=transport)

    def test_no_upload_without_explicit_consent(self):
        client = self.client({'text':'Merhaba'})
        for consent in (False, None, 'true', 1):
            with self.assertRaises(OpenRouterError):
                client.transcribe(b'RIFF', 'wav', model='openai/gpt-transcribe', consent=consent)
        self.assertEqual(self.requests, [])

    def test_exact_provider_model_and_no_fabricated_speakers(self):
        client = self.client({'text':'Sprint hedefini konuşalım.', 'usage':{'seconds':12,'cost':0.0009}})
        result = client.transcribe(b'RIFF', 'wav', model='openai/gpt-transcribe', consent=True)
        req, timeout = self.requests[0]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, 'https://openrouter.ai/api/v1/audio/transcriptions')
        self.assertEqual(body['model'], 'openai/gpt-transcribe')
        self.assertEqual(body['input_audio'], {'data':'UklGRg==','format':'wav'})
        self.assertEqual(body['language'], 'tr')
        self.assertNotIn('prompt', body)
        self.assertNotIn('segments', result)
        self.assertEqual(result['usage']['cost'], 0.0009)
        self.assertLessEqual(timeout, 90)

    def test_bad_inputs_never_reach_network(self):
        client = self.client({})
        for kwargs in ({'audio':b''}, {'format':'exe'}, {'model':'auto'}, {'language':'turkish'}, {'audio':b'x'*(client.MAX_AUDIO_BYTES+1)}):
            args=dict(audio=b'RIFF',format='wav',model='openai/gpt-transcribe',consent=True)
            args.update(kwargs)
            with self.assertRaises(OpenRouterError):client.transcribe(**args)
        self.assertEqual(self.requests, [])

    def test_http_errors_are_sanitized_not_retried_or_redirected(self):
        calls=[]
        def transport(req, timeout):
            calls.append(req)
            raise urllib.error.HTTPError(req.full_url, 429, 'secret-not-for-logs', {}, io.BytesIO(b'private transcript'))
        client=OpenRouterClient('secret-not-for-logs',transport=transport)
        with self.assertRaises(OpenRouterError) as caught:
            client.transcribe(b'RIFF','wav',model='openai/gpt-transcribe',consent=True)
        self.assertNotIn('secret',str(caught.exception));self.assertNotIn('private',str(caught.exception))
        self.assertIn('429',str(caught.exception));self.assertEqual(len(calls),1)
        from meeting_os.openrouter import NoRedirect
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.example'))

    def test_malformed_response_rejected(self):
        for value in ({}, {'text':[]}, {'text':'x','usage':{'cost':float('nan')}}, {'error':{'message':'private'}}):
            client=self.client(value)
            with self.assertRaises(OpenRouterError):client.transcribe(b'RIFF','wav',model='openai/gpt-transcribe',consent=True)

    def test_credential_resolution_never_touches_the_keychain(self):
        """Environment first, then the 0600 file the app wrote; Python never runs `security` (a Terminal-spawned
        process asking the Keychain produced an endless queue of dialogs on 10 Sep 2026)."""
        import tempfile
        from pathlib import Path
        from meeting_os import openrouter
        with patch.dict('os.environ',{'OPENROUTER_API_KEY':'env-secret'},clear=True), patch('subprocess.run') as run:
            self.assertEqual(read_api_key(),'env-secret');run.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp)/'openrouter.key'
            with patch.dict('os.environ',{},clear=True), patch.object(openrouter,'KEY_CACHE',cache), patch('subprocess.run') as run:
                with self.assertRaises(OpenRouterError) as caught:read_api_key()
                self.assertIn('uygulamasını bir kez açın',str(caught.exception));run.assert_not_called()
                cache.write_text('file-secret\n')
                self.assertEqual(read_api_key(),'file-secret');run.assert_not_called()
                cache.write_text('bad key\n')
                with self.assertRaises(OpenRouterError):read_api_key()
    def test_diarization_request_and_segment_parsing(self):
        from meeting_os.openrouter import parse_segments, diarization_options
        self.assertEqual(diarization_options('deepgram/nova-3'),{'deepgram':{'diarize':True}});self.assertIsNone(diarization_options('openai/gpt-transcribe'))
        captured={}
        def transport(req,timeout):
            captured['body']=json.loads(req.data);captured['timeout']=timeout
            class R:
                def __enter__(self):return self
                def __exit__(self,*a):pass
                def read(self,n):return json.dumps({'text':'a b','usage':{'seconds':2},'segments':[{'start':0,'end':1,'text':'a','speaker':0},{'start':1,'end':2,'text':'b','speaker':1}]}).encode()
            return R()
        client=OpenRouterClient(api_key='k',transport=transport)
        out=client.transcribe(b'OggS','ogg',model='deepgram/nova-3',consent=True,diarize=True,timeout=600)
        body=captured['body'];self.assertEqual(body['response_format'],'verbose_json');self.assertEqual(body['timestamp_granularities'],['segment'])
        self.assertEqual(body['provider'],{'options':{'deepgram':{'diarize':True}},'data_collection':'deny'});self.assertEqual(body['language'],'tr');self.assertEqual(captured['timeout'],600)
        self.assertEqual(out['segments'],[{'start':0.0,'end':1.0,'text':'a','speaker':'0'},{'start':1.0,'end':2.0,'text':'b','speaker':'1'}])
        with self.assertRaises(OpenRouterError):client.transcribe(b'OggS','ogg',model='openai/gpt-transcribe',consent=True,diarize=True)
        plain=client.transcribe(b'OggS','ogg',model='openai/gpt-transcribe',consent=True);self.assertNotIn('segments',plain);self.assertEqual(captured['body']['provider'],{'data_collection':'deny'})
        for bad in ([{'start':-1,'end':1,'text':'x'}],[{'start':2,'end':1,'text':'x'}],[{'start':0,'end':1,'text':5}],'nope'):
            with self.assertRaises(OpenRouterError):parse_segments(bad)
        self.assertEqual(parse_segments(None),[]);self.assertEqual(parse_segments([{'start':0,'end':1,'text':' x ','speaker':True}])[0]['speaker'],None)

    def test_http_status_messages_are_specific_and_leak_nothing(self):
        from meeting_os.openrouter import http_error_message
        self.assertIn('reddedildi',http_error_message(401));self.assertIn('bakiye',http_error_message(402))
        self.assertIn('hız sınırı',http_error_message(429));self.assertIn('hizmet',http_error_message(503))
        for code in (401,402,418):
            text=http_error_message(code);self.assertIn(str(code),text);self.assertIn('Otomatik tekrar yapılmadı',text)
        for code in (408,429,500,503):   # transient: cloud_finalize retries these in place before giving up
            text=http_error_message(code);self.assertIn(str(code),text);self.assertIn('Birkaç kez yeniden denendi',text)
        from meeting_os.openrouter import CloudAuthError,CloudCreditError,CloudUnavailable,cloud_error_class,error_kind
        self.assertEqual([cloud_error_class(c) for c in (401,403,402,429,500,404)],
                         [CloudAuthError,CloudAuthError,CloudCreditError,CloudUnavailable,CloudUnavailable,OpenRouterError])
        self.assertEqual([error_kind(c('x')) for c in (CloudAuthError,CloudCreditError,CloudUnavailable)],['auth','credit','unavailable'])
        self.assertTrue(CloudUnavailable('x').retryable);self.assertFalse(CloudAuthError('x').retryable)

    def test_analysis_adapter_uses_requested_model_and_json_schema(self):
        client=self.client({'choices':[{'finish_reason':'stop','message':{'content':'{"summary":[]}'}}]})
        llm=client.analysis('openai/gpt-5.6-luna',consent=True)
        self.assertEqual(llm.complete('system','source',schema={'type':'object'}),'{'+'"summary":[]}')
        req,_=self.requests[0];body=json.loads(req.data)
        self.assertTrue(req.full_url.endswith('/chat/completions'))
        self.assertEqual(body['model'],'openai/gpt-5.6-luna')
        self.assertEqual(body['response_format']['type'],'json_schema')
        self.assertEqual(body['provider']['allow_fallbacks'],False)
        client=self.client({'choices':[{'finish_reason':'length','message':{'content':'partial'}}]})
        with self.assertRaises(OpenRouterError):client.analysis('openai/gpt-5.6-luna',consent=True).complete('s','u')

    def test_every_advertised_model_is_sent_exactly_and_unknown_is_blocked(self):
        import tempfile
        from pathlib import Path
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            listing=dispatch({'action':'openrouter_models'},Path(tmp)/'db.sqlite')
        self.assertEqual(listing['default'],'openai/gpt-transcribe')
        self.assertEqual(len(listing['models']),7);self.assertEqual(listing['diarization_default'],'microsoft/mai-transcribe-2')
        self.assertEqual([m['id'] for m in listing['models'] if m['diarization']],['microsoft/mai-transcribe-2','deepgram/nova-3'])
        for option in listing['models']:
            client=self.client({'text':'Test'})
            client.transcribe(b'RIFF','wav',model=option['id'],consent=True)
            self.assertEqual(json.loads(self.requests[0][0].data)['model'],option['id'])
        client=self.client({'text':'Test'})
        with self.assertRaises(OpenRouterError):client.transcribe(b'RIFF','wav',model='openai/not-supported',consent=True)
        self.assertEqual(self.requests,[])

if __name__=='__main__':unittest.main()


class AnalysisUsageTests(unittest.TestCase):
    """Analysis money used to be invisible: the chat response's usage block was read and thrown away, so the
    cost report could only ever show transcription. Every chat call is now metered."""
    RESPONSE = {'choices':[{'finish_reason':'stop','message':{'content':'{"summary":[]}'}}]}
    client = OpenRouterTests.client

    def test_the_request_asks_for_the_charge_and_the_response_is_recorded(self):
        from meeting_os.openrouter import analysis_usage_recorder
        client=self.client({**self.RESPONSE,'usage':{'prompt_tokens':1200,'completion_tokens':300,'cost':0.00042}})
        seen=[]
        with analysis_usage_recorder(lambda model,usage: seen.append((model,usage))):
            client.analysis('openai/gpt-4.1-mini',consent=True).complete('s','u')
        body=json.loads(self.requests[0][0].data)
        self.assertEqual(body['usage'],{'include':True})   # without this OpenRouter sends no cost at all
        self.assertEqual(seen,[('openai/gpt-4.1-mini',{'model':'openai/gpt-4.1-mini','prompt_tokens':1200,'completion_tokens':300,'cost':0.00042,'estimated':False})])

    def test_a_provider_that_sends_no_cost_is_estimated_from_the_price_table_and_marked(self):
        from meeting_os.openrouter import analysis_usage_recorder, estimate_analysis_cost
        client=self.client({**self.RESPONSE,'usage':{'prompt_tokens':1_000_000,'completion_tokens':1_000_000}})
        seen=[]
        with analysis_usage_recorder(lambda model,usage: seen.append(usage)):
            client.analysis('openai/gpt-4.1-mini',consent=True).complete('s','u')
        self.assertEqual((seen[0]['cost'],seen[0]['estimated']),(2.0,True))   # $0.40/M in + $1.60/M out
        self.assertEqual(estimate_analysis_cost('openai/gpt-4.1-mini',500_000,0),0.2)
        self.assertIsNone(estimate_analysis_cost('someone/unpriced',10,10))   # no invented zero

    def test_junk_usage_and_a_missing_sink_never_break_an_analysis(self):
        from meeting_os.openrouter import analysis_usage_recorder, chat_usage
        for junk in (None,'lots',{'prompt_tokens':-4,'completion_tokens':float('nan'),'cost':True},[]):
            self.assertIsNone(chat_usage('someone/unpriced',junk))   # nothing billable reported → no row, no made-up zero
        client=self.client({**self.RESPONSE,'usage':{'cost':0.1}})
        self.assertEqual(client.analysis('openai/gpt-4.1-mini',consent=True).complete('s','u'),'{"summary":[]}')   # no recorder installed
        def explode(model,usage): raise RuntimeError('disk full')
        with analysis_usage_recorder(explode):
            self.assertEqual(self.client({**self.RESPONSE,'usage':{'cost':0.1}}).analysis('openai/gpt-4.1-mini',consent=True).complete('s','u'),'{"summary":[]}')

    def test_the_store_and_the_cost_report_add_the_calls_up(self):
        import tempfile
        from pathlib import Path
        from meeting_os.store import Store
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'meeting-os.sqlite';s=Store(db);mid=s.create_meeting('Sprint',{})
            self.assertEqual(s.analysis_usage(),[])   # no table until something was analysed
            self.assertEqual(s.analysis_cost_totals(),{'cost':0.0,'calls':0,'estimated':False})
            s.record_analysis_usage(mid,'openai/gpt-4.1-mini',{'prompt_tokens':1000,'completion_tokens':200,'cost':0.004,'estimated':False})
            s.record_analysis_usage(mid,'openai/gpt-4.1-mini',{'prompt_tokens':900,'completion_tokens':100,'cost':0.003,'estimated':True})
            self.assertEqual(s.analysis_cost_totals(mid),{'cost':0.007,'calls':2,'estimated':True})
            s.close()
            report=dispatch({'action':'cost_report'},db)
            self.assertEqual((report['analysis_cost'],report['analysis_calls'],report['analysis_estimated']),(0.007,2,True))
            s=Store(db)
            self.assertEqual(s.analysis_cost_totals(),{'cost':0.007,'calls':2,'estimated':True})
            s.delete_meeting(mid)   # a deleted meeting takes its bookkeeping with it
            self.assertEqual(s.analysis_usage(),[]);s.close()

    def test_an_analysis_records_its_calls_against_the_meeting(self):
        import tempfile
        from pathlib import Path
        from meeting_os.store import Store
        from meeting_os.types import Segment
        from meeting_os import assistant
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'meeting-os.sqlite';s=Store(db);mid=s.create_meeting('Sprint',{})
            sid=s.add_segment(mid,Segment(0,8,'Ben PRD taslağını yarın hazırlayacağım.','mic','Ben'));s.status(mid,'complete')
            payload=json.dumps({'summary':[{'text':'PRD taslağı hazırlanacak.','evidence':[{'segment_id':sid,'quote':'PRD taslağını yarın hazırlayacağım'}]}],
                                'decisions':[],'risks':[],'questions':[],'actions':[]},ensure_ascii=False)
            client=self.client({'choices':[{'finish_reason':'stop','message':{'content':payload}}],'usage':{'prompt_tokens':800,'completion_tokens':120,'cost':0.0009}})
            assistant.analyze(s,mid,client.analysis('openai/gpt-4.1-mini',consent=True))
            rows=s.analysis_usage(mid)
            self.assertEqual([(r['meeting'],r['model'],r['prompt_tokens'],r['completion_tokens'],r['cost'],r['estimated']) for r in rows],
                             [(mid,'openai/gpt-4.1-mini',800,120,0.0009,0)])
            s.close()
