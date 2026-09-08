"""Experimental pinned-Qwen CPU adapter; never selected by production defaults."""
import json,re,tempfile,time
from pathlib import Path
from .supervisor import run_guarded

class NativeLocalLLM:
    def __init__(self,model,runtime,context_size=4096):
        self.model=Path(model).resolve();self.runtime=Path(runtime).resolve()
        if not self.model.is_file():raise ValueError('Local GGUF model missing')
        for name in ('llama-completion','llama-tokenize'):
            if not (self.runtime/name).is_file():raise ValueError('Native runtime missing: '+name)
        if not 128<=context_size<=4096:raise ValueError('Experimental context must be128..4096')
        self.context_size=context_size
        metadata=self.model.parent/'meeting-os-model.json'
        details=json.loads(metadata.read_text()) if metadata.exists() else {}
        self.model_id=':'.join(str(v) for v in (self.model.name,details.get('revision','unknown'),details.get('verified_sha256','unverified')))
    def _execute(self,name,args,output,timeout):
        command=[str(self.runtime/name),'-m',str(self.model),'--offline',*args]
        with output.open('wb') as stream:
            run_guarded(command,timeout=timeout,isolated=True,output_stream=stream,failure_details=False)
        return output.read_text()
    def count(self,text):
        with tempfile.TemporaryDirectory(prefix='meeting-os-count-') as temp:
            root=Path(temp);prompt=root/'prompt.txt';prompt.write_text(text)
            raw=self._execute('llama-tokenize',['--file',str(prompt),'--ids'],root/'tokens.json',30)
            tokens=json.loads(raw)
            if not isinstance(tokens,list) or any(type(t)!=int or t<0 for t in tokens):raise ValueError('Invalid native token count')
            return len(tokens)
    def complete(self,system,user,max_tokens=1800,schema=None):
        # Explicit ChatML for this pinned non-thinking Qwen Instruct family.
        # Reject embedded delimiters rather than letting transcript data create roles.
        if any(re.search(r'<\|[^>]*\|>',text) for text in (system,user)):
            raise ValueError('Reserved chat delimiter in input')
        if type(max_tokens)!=int or not 1<=max_tokens<=2400:raise ValueError('Invalid output token limit')
        started=time.monotonic()
        prompt=f'<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n'
        if self.count(prompt)+max_tokens>self.context_size:
            raise ValueError('Native context budget exceeded; input was not truncated')
        with tempfile.TemporaryDirectory(prefix='meeting-os-native-') as temp:
            root=Path(temp);source=root/'prompt.txt';source.write_text(prompt)
            args=['--file',str(source),'--no-conversation','--no-display-prompt','--no-context-shift','--no-warmup',
                  '--gpu-layers','0','--no-kv-offload','--no-op-offload','--fit','off',
                  '--threads','2','--threads-batch','2','--batch-size','128','--ubatch-size','128',
                  '--ctx-size',str(self.context_size),'--n-predict',str(max_tokens),'--seed','42','--temp','0','--color','off']
            if schema is not None:
                path=root/'schema.json';path.write_text(json.dumps(schema));args+=['--json-schema-file',str(path)]
            remaining=120-(time.monotonic()-started)
            if remaining<=0:raise ValueError('Native request time budget exceeded')
            raw=self._execute('llama-completion',args,root/'response.txt',remaining).strip()
            if schema is not None:
                import jsonschema
                def invalid(value):raise ValueError('Non-finite JSON number')
                parsed=json.loads(raw,parse_constant=invalid)
                try:jsonschema.validate(parsed,schema)
                except jsonschema.ValidationError as exc:raise ValueError('Native output violates schema') from exc
            return raw
