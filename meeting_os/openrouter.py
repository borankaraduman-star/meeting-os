"""Explicit, bounded OpenRouter requests. Never called by local/default workflows."""
import base64
import contextvars
import json
import math
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

STT_MODEL = 'openai/gpt-transcribe'
STT_MODELS = (
    {'id':'microsoft/mai-transcribe-2','name':'Microsoft MAI-Transcribe 2 (konuşmacı ayrımı · Türkçe önerilen)','pricing':'≈ $0.10/saat (9 Eylül 2026 ölçümü: 60 s = $0.0017); konuşmacı ayrımı dahil','diarization':{'azure':{'diarization':{'enabled':True}}}},
    {'id':'deepgram/nova-3','name':'Deepgram Nova-3 (konuşmacı ayrımı · Türkçe zayıf)','pricing':'$0.0043/dakika; 9 Eylül 2026 testinde Türkçe karakterler eksik çıktı','diarization':{'deepgram':{'diarize':True}}},
    {'id':'openai/gpt-transcribe','name':'GPT Transcribe (ayrım yok)','pricing':'$0.0045/dakika; 30–40 dk yaklaşık $0.135–$0.18','diarization':None,'prompt':True},
    {'id':'openai/gpt-4o-transcribe','name':'GPT-4o Transcribe (ayrım yok)','pricing':'Token bazlı ücret; güncel fiyat OpenRouter model sayfasında','diarization':None,'prompt':True},
    {'id':'openai/gpt-4o-mini-transcribe','name':'GPT-4o Mini Transcribe (ayrım yok)','pricing':'Token bazlı ücret; güncel fiyat OpenRouter model sayfasında','diarization':None,'prompt':True},
    {'id':'openai/whisper-large-v3','name':'Whisper Large V3 (ayrım yok)','pricing':'Sağlayıcıya bağlı ücret; güncel fiyat OpenRouter model sayfasında','diarization':None},
    {'id':'openai/whisper-large-v3-turbo','name':'Whisper Large V3 Turbo (ayrım yok)','pricing':'Sağlayıcıya bağlı ücret; güncel fiyat OpenRouter model sayfasında','diarization':None},
)
DIARIZATION_DEFAULT_MODEL = 'microsoft/mai-transcribe-2'
ANALYSIS_MODELS = (   # chat models with strict JSON schema output, verified on OpenRouter endpoints 2026-09-09
    {'id':'deepseek/deepseek-v3.2','name':'DeepSeek V3.2 (varsayılan: 30/30 kıyas)','pricing':'$0.27/M giriş, $0.40/M çıkış; 2 saatlik toplantı ≈ 2 cent'},
    {'id':'openai/gpt-4.1-mini','name':'GPT-4.1 mini','pricing':'$0.40/M giriş, $1.60/M çıkış; 40 dk toplantı ≈ 3 cent, 2 saatlik toplantı ≈ $0,08'},
    {'id':'openai/gpt-4o-mini','name':'GPT-4o mini','pricing':'$0.15/M giriş, $0.60/M çıkış'},
    {'id':'google/gemini-2.5-flash','name':'Gemini 2.5 Flash','pricing':'$0.30/M giriş, $2.50/M çıkış'},
    # Added 10 Sep 2026 for a head-to-head benchmark (Boran: "analizde neden GPT?"); prices read off OpenRouter that day.
    {'id':'anthropic/claude-haiku-4.5','name':'Claude Haiku 4.5','pricing':'$1.00/M giriş, $5.00/M çıkış'},
    {'id':'anthropic/claude-sonnet-5','name':'Claude Sonnet 5','pricing':'$2.00/M giriş, $10.00/M çıkış'},
    {'id':'google/gemini-3-flash-preview','name':'Gemini 3 Flash (önizleme)','pricing':'$0.50/M giriş, $3.00/M çıkış'},
    {'id':'openai/gpt-5-nano','name':'GPT-5 nano','pricing':'$0.05/M giriş, $0.40/M çıkış'},
    {'id':'openai/gpt-5.6-luna','name':'GPT-5.6 luna','pricing':'$0.20/M giriş, $1.20/M çıkış'},
    {'id':'qwen/qwen3-235b-a22b-2507','name':'Qwen3 235B','pricing':'$0.22/M giriş, $0.88/M çıkış'},
    {'id':'mistralai/mistral-small-2603','name':'Mistral Small','pricing':'$0.15/M giriş, $0.60/M çıkış'},
    {'id':'z-ai/glm-5.3-flash','name':'GLM 5.3 Flash','pricing':'$0.15/M giriş, $0.50/M çıkış'},
    {'id':'deepseek/deepseek-v4-flash','name':'DeepSeek V4 Flash','pricing':'$0.08/M giriş, $0.17/M çıkış'},
    {'id':'deepseek/deepseek-v4.1-flash','name':'DeepSeek V4.1 Flash','pricing':'$0.15/M giriş, $0.60/M çıkış'},
    {'id':'deepseek/deepseek-v4-pro','name':'DeepSeek V4 Pro','pricing':'$0.87/M giriş, $1.74/M çıkış'},
)
# 10–11 Sep 2026 head-to-head (scripts/benchmark-analysis-cloud.py, 10 fictional cases, 3 runs): DeepSeek V3.2 30/30 with no
# dropped task and no leak; gpt-4.1-mini 26/30 (one leak); Mistral Small 18/20; GLM 5.3 Flash rate-limited upstream in 3
# of 4 runs; Gemini 3 Flash broke quotes; Sonnet 5 ten times the price. DeepSeek is slower (≈26 s vs 9 s a chunk) — the
# analysis runs after the meeting, so a 2-hour meeting costs ≈3 minutes instead of 1, for half the money.
ANALYSIS_DEFAULT_MODEL = 'deepseek/deepseek-v3.2'
CHAT_TIMEOUT = 240   # a real 2-hour chunk on a slower model; 90 s was sized for gpt-4.1-mini and would cut DeepSeek mid-answer
# USD per million tokens (input, output), read off the model pages on 9 Sep 2026 — the same numbers the
# `pricing` strings above show the user. Only a fallback: OpenRouter returns the real charge in `usage.cost`
# when the request asks for it, and an estimate made from this table is always marked `estimated`.
ANALYSIS_PRICES = {'openai/gpt-4.1-mini': (0.40, 1.60), 'openai/gpt-4o-mini': (0.15, 0.60), 'google/gemini-2.5-flash': (0.30, 2.50),
                   'anthropic/claude-haiku-4.5': (1.00, 5.00), 'anthropic/claude-sonnet-5': (2.00, 10.00), 'google/gemini-3-flash-preview': (0.50, 3.00),
                   'deepseek/deepseek-v3.2': (0.27, 0.40), 'openai/gpt-5-nano': (0.05, 0.40), 'openai/gpt-5.6-luna': (0.20, 1.20), 'qwen/qwen3-235b-a22b-2507': (0.22, 0.88),
                   'mistralai/mistral-small-2603': (0.15, 0.60), 'z-ai/glm-5.3-flash': (0.15, 0.50),
                   'deepseek/deepseek-v4-flash': (0.08, 0.17), 'deepseek/deepseek-v4.1-flash': (0.15, 0.60), 'deepseek/deepseek-v4-pro': (0.87, 1.74)}


def estimate_analysis_cost(model, prompt_tokens, completion_tokens):
    """USD from the price table, or None for a model we have no price for (never a made-up zero)."""
    price = ANALYSIS_PRICES.get(model)
    if price is None: return None
    return round((float(prompt_tokens or 0)*price[0] + float(completion_tokens or 0)*price[1])/1_000_000, 6)


# Set for the length of one analysis by assistant.analyze; see analysis_usage_recorder. A ContextVar rather
# than a plain global: the reset token restores exactly this scope's value, and a concurrent analysis in
# another thread or task cannot end up billing its chunks to somebody else's meeting.
_USAGE_SINK = contextvars.ContextVar('meeting_os_usage_sink', default=None)


def analysis_usage_recorder(sink):
    """Context manager that routes every chat completion's usage to `sink(model, usage)` while it is open.

    A chat call happens deep inside intelligence.analyze_rows, which knows nothing about a meeting or a
    database; the meeting id lives one level up in assistant.analyze. Rather than thread a store through
    four call signatures that have no other use for it, the analysis brackets its own calls here."""
    import contextlib
    @contextlib.contextmanager
    def scope():
        token = _USAGE_SINK.set(sink)
        try: yield
        finally: _USAGE_SINK.reset(token)
    return scope()


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0: return None
    return value


def chat_usage(model, raw):
    """The billable part of a chat completion response: {'prompt_tokens','completion_tokens','cost','estimated'}.
    Anything the provider did not send, or sent as nonsense, is dropped rather than guessed at."""
    usage = raw if isinstance(raw, dict) else {}
    prompt = _number(usage.get('prompt_tokens'))
    completion = _number(usage.get('completion_tokens'))
    cost = _number(usage.get('cost'))
    if prompt is None and completion is None and cost is None: return None   # nothing billable was reported: no row, no made-up zero
    estimated = False
    if cost is None:
        cost = estimate_analysis_cost(model, prompt, completion)
        estimated = cost is not None
    return {'model': model, 'prompt_tokens': int(prompt or 0), 'completion_tokens': int(completion or 0),
            'cost': float(cost or 0.0), 'estimated': estimated}

def validate_analysis_model(model):
    if model not in {m['id'] for m in ANALYSIS_MODELS}:
        raise OpenRouterError('Desteklenmeyen analiz modeli; model otomatik değiştirilmedi.')
    return model

def supports_prompt(model):
    """Models whose upstream API accepts a spelling-hint prompt; OpenRouter pass-through is measured, not assumed."""
    return any(m['id']==model and m.get('prompt') for m in STT_MODELS)


def diarization_options(model):
    """Provider-specific diarization switch verified on 2026-09-09, or None when the model has none."""
    for m in STT_MODELS:
        if m['id']==model: return m['diarization']
    return None

def validate_stt_model(model):
    if model not in {m['id'] for m in STT_MODELS}:
        raise OpenRouterError('Desteklenmeyen transkripsiyon modeli; model otomatik değiştirilmedi.')
    return model

KEYCHAIN_SERVICE = 'local.boran.meeting-os.openrouter'

class OpenRouterError(ValueError):
    """Base for everything the cloud path can fail with. `kind` and `user_message` are what the app persists
    and shows; `retryable` decides whether a piece is worth sending again."""
    kind='other';retryable=False;user_message=None

class CloudAuthError(OpenRouterError):
    """401/403: the key is wrong or the account may not use this model. Retrying only wastes the meeting's time."""
    kind='auth';user_message='OpenRouter anahtarı geçersiz — Ayarlar → OpenRouter'

class CloudCreditError(OpenRouterError):
    """402: nothing is broken, the account is simply out of money. Only the user can fix it."""
    kind='credit';user_message='OpenRouter kredisi bitti'

class CloudUnavailable(OpenRouterError):
    """Timeout, dropped connection, 408/429/5xx: the service, not the account. Worth another try later."""
    kind='unavailable';retryable=True;user_message='OpenRouter şu an yanıt vermiyor; ses güvende, boşta yeniden denenecek'


def cloud_error_class(code):
    """HTTP status → the exception class that carries the right Turkish line and retry decision."""
    if code in (401,403): return CloudAuthError
    if code==402: return CloudCreditError
    if code in (408,429) or code>=500: return CloudUnavailable
    return OpenRouterError   # 400/404/413: a request we must not repeat unchanged


def error_kind(exc): return getattr(exc,'kind','other')

def error_message(exc):
    """One honest sentence for the meeting list: the classified line when we have one, the raw message otherwise."""
    return getattr(exc,'user_message',None) or str(exc)[:300]


RETRYABLE_CODES = (408,429)   # plus every 5xx; see cloud_error_class

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


KEY_CACHE = Path.home() / 'Library/Application Support/MeetingOS/openrouter.key'   # 0600, written by the app after its one Keychain read


def read_api_key():
    """Environment first (the app hands the key to every job), then the 0600 file the app wrote after its single
    Keychain read. Python never calls `security`: a Terminal-spawned process asking the Keychain is exactly what
    produced an endless queue of "security wants to use your keychain" dialogs on 10 Sep 2026."""
    key = os.environ.get('OPENROUTER_API_KEY', '').strip()
    if not key:
        try: key = KEY_CACHE.read_text(encoding='utf-8').strip()
        except OSError: key = ''
    if not key:
        raise OpenRouterError('OpenRouter anahtarı bulunamadı. Meeting OS uygulamasını bir kez açın (Ayarlar → Sistem → OpenRouter anahtarı); anahtar uygulamanın klasörüne alınır.')
    if any(c.isspace() for c in key):
        raise OpenRouterError('OpenRouter anahtarı bozuk görünüyor; Ayarlar → Sistem → OpenRouter anahtarı ile yeniden kaydedin.')
    return key


def _model(model):
    if not isinstance(model, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.:-]+', model):
        raise OpenRouterError('Açık bir sağlayıcı/model kimliği gerekir; otomatik model seçilmez.')
    return model


def _consent(consent):
    if consent is not True: raise OpenRouterError('OpenRouter’a içerik gönderimi için açık onay gerekir.')


def http_error_message(code):
    detail={401:'OpenRouter anahtarı reddedildi; anahtarı kontrol edip yeniden kaydedin.',
            402:'OpenRouter bakiyesi yetersiz; hesabınıza kredi ekleyin.',
            403:'OpenRouter bu isteği reddetti; hesap/model erişimini kontrol edin.',
            404:'Seçilen model veya uç nokta OpenRouter’da bulunamadı.',
            408:'OpenRouter isteği zaman aşımına uğradı.',
            413:'Ses parçası OpenRouter sınırını aştı.',
            429:'OpenRouter hız sınırı; biraz bekleyip sürdürün.'}.get(code)
    if detail is None:
        detail='OpenRouter hizmet hatası; biraz bekleyip sürdürün.' if code>=500 else 'Anahtarı, bakiyeyi veya hizmet durumunu kontrol edin.'
    # Transient statuses are now retried in place (see cloud_finalize.RETRY_WAITS); the others still are not.
    tail='Birkaç kez yeniden denendi' if code in RETRYABLE_CODES or code>=500 else 'Otomatik tekrar yapılmadı'
    return f'OpenRouter HTTP {code}. {detail} {tail}; tamamlanan parçalar korunuyor.'


def parse_segments(raw):
    """Provider segments -> bounded list of {start,end,text,speaker}; never invents timing or speakers."""
    if raw is None: return []
    if not isinstance(raw,list) or len(raw)>20000: raise OpenRouterError('OpenRouter konuşmacı bölümleri geçersiz.')
    out=[]
    for item in raw:
        if not isinstance(item,dict): raise OpenRouterError('OpenRouter konuşmacı bölümleri geçersiz.')
        start,end,text=item.get('start'),item.get('end'),item.get('text')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (start,end)) or start<0 or end<start:
            raise OpenRouterError('OpenRouter bölüm zamanları geçersiz.')
        if not isinstance(text,str): raise OpenRouterError('OpenRouter bölüm metni geçersiz.')
        speaker=item.get('speaker')
        if speaker is not None and (isinstance(speaker,bool) or not isinstance(speaker,(int,str))): speaker=None
        out.append({'start':float(start),'end':float(end),'text':text.strip(),'speaker':None if speaker is None else str(speaker)})
    return out


class OpenRouterClient:
    MAX_AUDIO_BYTES = 8 * 1024 * 1024
    MAX_RESPONSE_BYTES = 4 * 1024 * 1024
    def __init__(self, api_key=None, *, transport=None, max_audio_bytes=None):
        if max_audio_bytes: self.MAX_AUDIO_BYTES=int(max_audio_bytes)
        self._key = api_key or read_api_key()
        if not isinstance(self._key,str) or any(c.isspace() for c in self._key):
            raise OpenRouterError('Geçersiz OpenRouter anahtarı.')
        self._transport = transport or urllib.request.build_opener(NoRedirect()).open

    def _post(self, endpoint, payload, timeout=90):
        req = urllib.request.Request('https://openrouter.ai/api/v1/' + endpoint,
            data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(),
            headers={'Authorization':'Bearer '+self._key,'Content-Type':'application/json'},method='POST')
        try:
            with self._transport(req, timeout=timeout) as response: raw=response.read(self.MAX_RESPONSE_BYTES+1)
        except urllib.error.HTTPError as exc:
            detail=''
            if 400<=exc.code<500:
                try: detail=exc.read(2000).decode('utf-8','replace')
                except Exception: detail=''
                detail=re.sub(r'\s+',' ',detail)[:220]
            if detail: print(f'OpenRouter sağlayıcı ayrıntısı (HTTP {exc.code}): {detail}',file=__import__('sys').stderr,flush=True)  # log only; the user-facing message stays free of provider/request echoes
            error=cloud_error_class(exc.code)(http_error_message(exc.code)); error.code=exc.code   # the status stays readable to callers that adapt the request
            raise error from None
        except (OSError, TimeoutError):
            raise CloudUnavailable('OpenRouter bağlantısı tamamlanamadı. Ücret oluşmuş olabilir; tamamlanan parçalar korunuyor.') from None
        if len(raw)>self.MAX_RESPONSE_BYTES: raise OpenRouterError('OpenRouter yanıtı boyut sınırını aştı.')
        try: result=json.loads(raw)
        except (ValueError,UnicodeError): raise OpenRouterError('OpenRouter geçerli JSON döndürmedi.') from None
        if not isinstance(result,dict) or 'error' in result: raise OpenRouterError('OpenRouter geçersiz/hatalı yanıt döndürdü.')
        return result

    def transcribe(self, audio, format, *, model=STT_MODEL, consent=False, language='tr', diarize=False, timeout=90, hint=None):
        _consent(consent);validate_stt_model(model)
        if not isinstance(audio,bytes) or not 0<len(audio)<=self.MAX_AUDIO_BYTES:
            raise OpenRouterError(f'Ses parçası boş veya {self.MAX_AUDIO_BYTES//(1024*1024)} MiB sınırını aşıyor.')
        if format not in ('wav','mp3','flac','m4a','ogg','webm','aac'):
            raise OpenRouterError('Desteklenmeyen ses biçimi.')
        if language is not None and not re.fullmatch('[a-z]{2}',language):
            raise OpenRouterError('Dil iki harfli ISO kodu olmalı.')
        payload={'model':model,'input_audio':{'data':base64.b64encode(audio).decode(),'format':format},'response_format':'json'}
        if language:payload['language']=language
        if hint and supports_prompt(model): payload['prompt']=str(hint)[:1000]   # glossary spelling hint; ignored by providers that do not read it
        options=diarization_options(model) if diarize else None
        if diarize and options is None:raise OpenRouterError('Seçilen model konuşmacı ayrımı sunmuyor; model otomatik değiştirilmedi.')
        payload['provider']={'data_collection':'deny'}   # every audio piece, mic included, asks the provider not to keep it
        if options:
            payload['response_format']='verbose_json';payload['timestamp_granularities']=['segment'];payload['provider']['options']=options
        result=self._post('audio/transcriptions',payload,timeout=timeout)
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
        out={'text':result['text'],'usage':safe_usage}
        if options: out['segments']=parse_segments(result.get('segments'))
        return out

    def analysis(self, model, *, consent=False):
        _consent(consent)
        return OpenRouterLLM(self,_model(model))


class OpenRouterLLM:
    supports_const_choices=False   # strict JSON schema mode rejects anyOf/const evidence menus; quotes are verified locally instead
    def __init__(self,client,model):self.client,self.model_id=client,model
    def count(self,text):return max(1,len(text.encode('utf-8'))//3)  # ≈ tokens for Turkish; no tokenizer download
    @staticmethod
    def _starved(result):
        try:
            choice=result['choices'][0]; text=choice['message'].get('content')
            return choice.get('finish_reason')=='length' and not (isinstance(text,str) and text.strip())
        except (KeyError,IndexError,TypeError,AttributeError): return False
    def complete(self,system,user,max_tokens=1800,schema=None):
        payload={'model':self.model_id,'messages':[{'role':'system','content':system},{'role':'user','content':user}],
                 'max_tokens':max_tokens,'temperature':0,'provider':{'allow_fallbacks':False,'require_parameters':True,'data_collection':'deny'}}
        if schema is not None:payload['response_format']={'type':'json_schema','json_schema':{'name':'meeting_analysis','strict':True,'schema':schema}}
        payload['usage']={'include':True}   # OpenRouter then returns the real charge in usage.cost; without it analysis money is invisible
        try: result=self.client._post('chat/completions',payload,timeout=CHAT_TIMEOUT)
        except OpenRouterError as exc:
            # Reasoning-family endpoints (GPT-5, Claude Sonnet 5) accept no `temperature`; with require_parameters
            # OpenRouter answers 404 "no endpoints found that can handle the requested parameters". One retry as a
            # reasoning request (10 Sep 2026 benchmark): no temperature, low effort (this is extraction against a strict
            # schema, not a puzzle) and room for the thinking tokens that otherwise eat the whole answer budget.
            if getattr(exc,'code',None)!=404 or 'temperature' not in payload: raise
            payload.pop('temperature'); payload['reasoning']={'effort':'low'}; payload['max_tokens']=max_tokens+6000
            result=self.client._post('chat/completions',payload,timeout=CHAT_TIMEOUT)
        if self._starved(result) and 'reasoning' not in payload:
            # A thinking model that stopped for length with nothing to show: it spent the budget reasoning. Same
            # remedy, one retry; a second empty answer is an error like any other.
            payload.pop('temperature',None); payload['reasoning']={'effort':'low'}; payload['max_tokens']=max_tokens+6000
            result=self.client._post('chat/completions',payload,timeout=CHAT_TIMEOUT)
        sink=_USAGE_SINK.get()
        if sink is not None:
            try:
                usage=chat_usage(self.model_id,result.get('usage'))
                if usage is not None: sink(self.model_id,usage)
            except Exception: pass   # bookkeeping must never lose a completed, paid-for analysis
        try:
            choice=result['choices'][0]
            text=choice['message']['content']
            if choice['finish_reason']!='stop' or not isinstance(text,str) or not text.strip():raise ValueError()
        except (KeyError,IndexError,TypeError,ValueError):
            # Why, in the job log only: the finish reason and the size of what came back, never the content.
            try: choice=result['choices'][0]; why=f"finish={choice.get('finish_reason')!r} chars={len(choice.get('message',{}).get('content') or '')} model={self.model_id}"
            except Exception: why='no choices'
            print(f'Meeting OS: Analiz yanıtı geçersiz ({why})',file=__import__('sys').stderr,flush=True)
            raise OpenRouterError('Analiz yanıtı tamamlanmadı veya geçersiz; kısmi analiz kaydedilmedi.') from None
        return text
