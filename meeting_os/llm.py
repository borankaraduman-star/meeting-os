"""Local-only text generation. No cloud provider, tools, or implicit downloads."""
from pathlib import Path
import contextlib,sys,json
DEFAULT_MODEL=Path(__file__).resolve().parents[1]/'models/analysis-qwen3'
class LocalLLM:
    def __init__(self,path=DEFAULT_MODEL):
        self.path=Path(path).resolve()
        if not (self.path/'config.json').is_file(): raise ValueError('Yerel analiz modeli eksik. models fetch analysis-qwen3 komutunu çalıştırın.')
        from mlx_lm import load
        with contextlib.redirect_stdout(sys.stderr): self.model,self.tokenizer=load(str(self.path),tokenizer_config={'trust_remote_code':False})
        metadata=self.path/'meeting-os-model.json'
        self.model_id=json.loads(metadata.read_text()).get('revision',self.path.name) if metadata.exists() else self.path.name
    def complete(self,system,user,max_tokens=1800,schema=None):
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler
        prompt=self.tokenizer.apply_chat_template([{'role':'system','content':system},{'role':'user','content':user}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
        with contextlib.redirect_stdout(sys.stderr):
            if schema is not None:
                import outlines
                from outlines.types import JsonSchema
                if not hasattr(self,'structured'):self.structured=outlines.from_mlxlm(self.model,self.tokenizer)
                return self.structured(prompt,output_type=JsonSchema(schema),max_tokens=max_tokens,sampler=make_sampler(temp=0.0))
            return generate(self.model,self.tokenizer,prompt=prompt,max_tokens=max_tokens,sampler=make_sampler(temp=0.0),verbose=False)
    def count(self,text): return len(self.tokenizer.encode(text))
