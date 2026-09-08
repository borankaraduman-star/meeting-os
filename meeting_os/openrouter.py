"""Explicit, bounded OpenRouter requests. Never called by local/default workflows."""
import base64
import json
import math
import os
import re
import subprocess
import urllib.error
import urllib.request

STT_MODEL = 'openai/gpt-transcribe'
STT_MODELS = (
    {'id':'openai/gpt-transcribe','name':'GPT Transcribe','pricing':'$0.0045/dakika; 30–40 dk yaklaşık $0.135–$0.18'},
    {'id':'openai/gpt-4o-transcribe','name':'GPT-4o Transcribe','pricing':'Token bazlı ücret; güncel fiyat OpenRouter model sayfasında'},
    {'id':'openai/gpt-4o-mini-transcribe','name':'GPT-4o Mini Transcribe','pricing':'Token bazlı ücret; güncel fiyat OpenRouter model sayfasında'},
    {'id':'openai/whisper-large-v3','name':'Whisper Large V3','pricing':'Sağlayıcıya bağlı ücret; güncel fiyat OpenRouter model sayfasında'},
    {'id':'openai/whisper-large-v3-turbo','name':'Whisper Large V3 Turbo','pricing':'Sağlayıcıya bağlı ücret; güncel fiyat OpenRouter model sayfasında'},
)

def validate_stt_model(model):
    if model not in {m['id'] for m in STT_MODELS}:
        raise OpenRouterError('Desteklenmeyen transkripsiyon modeli; model otomatik değiştirilmedi.')
    return model

KEYCHAIN_SERVICE = 'local.boran.meeting-os.openrouter'

class OpenRouterError(ValueError): pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def read_api_key():
    key = os.environ.get('OPENROUTER_API_KEY', '').strip()
    if not key:
        try:
            result = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', KEYCHAIN_SERVICE,
                                     '-a', 'openrouter', '-w'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0: key = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired): pass
    if not key or any(c.isspace() for c in key):
        raise OpenRouterError('OpenRouter anahtarı eksik. Uygulamadaki OpenRouter ayarlarına API anahtarını kaydedin.')
    return key


def _model(model):
    if not isinstance(model, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.:-]+', model):
        raise OpenRouterError('Açık bir sağlayıcı/model kimliği gerekir; otomatik model seçilmez.')
    return model


def _consent(consent):
    if consent is not True: raise OpenRouterError('OpenRouter’a içerik gönderimi için açık onay gerekir.')


class OpenRouterClient:
    MAX_AUDIO_BYTES = 8 * 1024 * 1024
    MAX_RESPONSE_BYTES = 4 * 1024 * 1024
    def __init__(self, api_key=None, *, transport=None):
        self._key = api_key or read_api_key()
        if not isinstance(self._key,str) or any(c.isspace() for c in self._key):
            raise OpenRouterError('Geçersiz OpenRouter anahtarı.')
        self._transport = transport or urllib.request.build_opener(NoRedirect()).open

    def _post(self, endpoint, payload):
        req = urllib.request.Request('https://openrouter.ai/api/v1/' + endpoint,
            data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(),
            headers={'Authorization':'Bearer '+self._key,'Content-Type':'application/json'},method='POST')
        try:
            with self._transport(req, timeout=90) as response: raw=response.read(self.MAX_RESPONSE_BYTES+1)
        except urllib.error.HTTPError as exc:
            code=exc.code
            raise OpenRouterError(f'OpenRouter HTTP {code}. Otomatik tekrar yapılmadı; anahtarı, bakiyeyi veya hizmet durumunu kontrol edin.') from None
        except (OSError, TimeoutError):
            raise OpenRouterError('OpenRouter bağlantısı tamamlanamadı. Ücret oluşmuş olabilir; otomatik tekrar yapılmadı.') from None
        if len(raw)>self.MAX_RESPONSE_BYTES: raise OpenRouterError('OpenRouter yanıtı boyut sınırını aştı.')
        try: result=json.loads(raw)
        except (ValueError,UnicodeError): raise OpenRouterError('OpenRouter geçerli JSON döndürmedi.') from None
        if not isinstance(result,dict) or 'error' in result: raise OpenRouterError('OpenRouter geçersiz/hatalı yanıt döndürdü.')
        return result

    def transcribe(self, audio, format, *, model=STT_MODEL, consent=False, language='tr'):
        _consent(consent);validate_stt_model(model)
        if not isinstance(audio,bytes) or not 0<len(audio)<=self.MAX_AUDIO_BYTES:
            raise OpenRouterError('Ses parçası boş veya 8 MiB sınırını aşıyor.')
        if format not in ('wav','mp3','flac','m4a','ogg','webm','aac'):
            raise OpenRouterError('Desteklenmeyen ses biçimi.')
        if language is not None and not re.fullmatch('[a-z]{2}',language):
            raise OpenRouterError('Dil iki harfli ISO kodu olmalı.')
        payload={'model':model,'input_audio':{'data':base64.b64encode(audio).decode(),'format':format},'response_format':'json'}
        if language:payload['language']=language
        result=self._post('audio/transcriptions',payload)
        if not isinstance(result.get('text'),str):raise OpenRouterError('OpenRouter transkript metni döndürmedi.')
        usage=result.get('usage') or {}
        if not isinstance(usage,dict):raise OpenRouterError('OpenRouter kullanım verisi geçersiz.')
        safe_usage={}
        for key in ('seconds','cost','total_tokens','input_tokens','output_tokens'):
            if key in usage:
                value=usage[key]
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                    raise OpenRouterError('OpenRouter kullanım verisi geçersiz.')
                safe_usage[key]=value
        return {'text':result['text'],'usage':safe_usage}

    def analysis(self, model, *, consent=False):
        _consent(consent)
        return OpenRouterLLM(self,_model(model))


class OpenRouterLLM:
    def __init__(self,client,model):self.client,self.model_id=client,model
    def count(self,text):return len(text.encode('utf-8'))  # conservative upper bound; no tokenizer download
    def complete(self,system,user,max_tokens=1800,schema=None):
        payload={'model':self.model_id,'messages':[{'role':'system','content':system},{'role':'user','content':user}],
                 'max_tokens':max_tokens,'temperature':0,'provider':{'allow_fallbacks':False,'require_parameters':True}}
        if schema is not None:payload['response_format']={'type':'json_schema','json_schema':{'name':'meeting_analysis','strict':True,'schema':schema}}
        result=self.client._post('chat/completions',payload)
        try:
            choice=result['choices'][0]
            text=choice['message']['content']
            if choice['finish_reason']!='stop' or not isinstance(text,str) or not text.strip():raise ValueError()
        except (KeyError,IndexError,TypeError,ValueError):raise OpenRouterError('Analiz yanıtı tamamlanmadı veya geçersiz; kısmi analiz kaydedilmedi.') from None
        return text
