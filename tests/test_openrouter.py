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

    def test_credential_resolution_does_not_search_other_apps(self):
        with patch.dict('os.environ',{'OPENROUTER_API_KEY':'env-secret'},clear=True), patch('subprocess.run') as run:
            self.assertEqual(read_api_key(),'env-secret');run.assert_not_called()
        with patch.dict('os.environ',{},clear=True), patch('subprocess.run') as run:
            run.return_value.returncode=44;run.return_value.stdout=''
            with self.assertRaises(OpenRouterError):read_api_key()
            self.assertEqual(run.call_args.args[0][0],'/usr/bin/security')
            self.assertIn('local.boran.meeting-os.openrouter',run.call_args.args[0])

    def test_keychain_prompt_timeout_and_denial_are_distinguished(self):
        import subprocess
        from meeting_os.openrouter import KEYCHAIN_TIMEOUT
        self.assertGreaterEqual(KEYCHAIN_TIMEOUT,120)  # user must have time to answer the macOS access prompt
        with patch.dict('os.environ',{},clear=True), patch('subprocess.run',side_effect=subprocess.TimeoutExpired('security',KEYCHAIN_TIMEOUT)):
            with self.assertRaises(OpenRouterError) as caught:read_api_key()
            self.assertIn('zaman aşımı',str(caught.exception));self.assertNotIn('eksik',str(caught.exception))
        with patch.dict('os.environ',{},clear=True), patch('subprocess.run') as run:
            run.return_value.returncode=44;run.return_value.stdout='';run.return_value.stderr='security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.'
            with self.assertRaises(OpenRouterError) as caught:read_api_key()
            self.assertIn('eksik',str(caught.exception))
        with patch.dict('os.environ',{},clear=True), patch('subprocess.run') as run:
            run.return_value.returncode=36;run.return_value.stdout='';run.return_value.stderr='security: SecKeychainItemCopyContent: User interaction is not allowed.'
            with self.assertRaises(OpenRouterError) as caught:read_api_key()
            self.assertIn('reddedildi',str(caught.exception));self.assertNotIn('eksik',str(caught.exception))
        with patch.dict('os.environ',{},clear=True), patch('subprocess.run') as run:
            run.return_value.returncode=0;run.return_value.stdout='sk-or-secret\n';run.return_value.stderr=''
            self.assertEqual(read_api_key(),'sk-or-secret')
            self.assertEqual(run.call_args.kwargs['timeout'],KEYCHAIN_TIMEOUT)

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
        self.assertEqual(body['provider'],{'options':{'deepgram':{'diarize':True}}});self.assertEqual(body['language'],'tr');self.assertEqual(captured['timeout'],600)
        self.assertEqual(out['segments'],[{'start':0.0,'end':1.0,'text':'a','speaker':'0'},{'start':1.0,'end':2.0,'text':'b','speaker':'1'}])
        with self.assertRaises(OpenRouterError):client.transcribe(b'OggS','ogg',model='openai/gpt-transcribe',consent=True,diarize=True)
        plain=client.transcribe(b'OggS','ogg',model='openai/gpt-transcribe',consent=True);self.assertNotIn('segments',plain);self.assertNotIn('provider',captured['body'])
        for bad in ([{'start':-1,'end':1,'text':'x'}],[{'start':2,'end':1,'text':'x'}],[{'start':0,'end':1,'text':5}],'nope'):
            with self.assertRaises(OpenRouterError):parse_segments(bad)
        self.assertEqual(parse_segments(None),[]);self.assertEqual(parse_segments([{'start':0,'end':1,'text':' x ','speaker':True}])[0]['speaker'],None)

    def test_http_status_messages_are_specific_and_leak_nothing(self):
        from meeting_os.openrouter import http_error_message
        self.assertIn('reddedildi',http_error_message(401));self.assertIn('bakiye',http_error_message(402))
        self.assertIn('hız sınırı',http_error_message(429));self.assertIn('hizmet',http_error_message(503))
        for code in (401,402,429,500,418):
            text=http_error_message(code);self.assertIn(str(code),text);self.assertIn('Otomatik tekrar yapılmadı',text)

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
        self.assertEqual(len(listing['models']),7);self.assertEqual(listing['diarization_default'],'deepgram/nova-3')
        self.assertEqual([m['id'] for m in listing['models'] if m['diarization']],['deepgram/nova-3','microsoft/mai-transcribe-2'])
        for option in listing['models']:
            client=self.client({'text':'Test'})
            client.transcribe(b'RIFF','wav',model=option['id'],consent=True)
            self.assertEqual(json.loads(self.requests[0][0].data)['model'],option['id'])
        client=self.client({'text':'Test'})
        with self.assertRaises(OpenRouterError):client.transcribe(b'RIFF','wav',model='openai/not-supported',consent=True)
        self.assertEqual(self.requests,[])

if __name__=='__main__':unittest.main()
