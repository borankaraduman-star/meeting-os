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

if __name__=='__main__':unittest.main()
