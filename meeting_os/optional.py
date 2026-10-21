"""Paketin bilerek taşımadığı yerel model kütüphaneleri için anlaşılır hata.

Paket yalnız bulut yolunu taşır (docs/BUNDLE.md): yazıya çevirme ve analiz OpenRouter'da, yerelde yalnız ses izi
(ONNX). mlx, mlx-whisper, mlx-lm, outlines, openai-whisper, speechbrain, pyannote ve torch artık ne pakette ne
`requirements-macos-tested.txt` içinde; `requirements-local-models.txt` geliştirici Mac'ine isteğe bağlı ek
olarak kurar. Bu yollardan biri seçildiğinde kullanıcı ham `ModuleNotFoundError` değil, ne yapacağını söyleyen
bir Türkçe cümle görür.
"""
import importlib

LOCAL_HINT = ('Bu kurulum yerel modelleri taşımıyor; Ayarlar → Sistem → Yazıya çevirme: “OpenRouter (bulut)” '
              'seçin. Geliştirici Mac’inde: .venv/bin/python -m pip install -r requirements-local-models.txt')


class MissingComponent(ValueError):
    """A ValueError so the CLI's existing handler prints the sentence, not a traceback."""
    kind = 'missing_component'


def require(module, feature):
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        top = (getattr(exc, 'name', None) or module).split('.')[0]
        if top == 'onnxruntime':
            raise MissingComponent(f'{feature} için gereken onnxruntime bu kurulumda yok; uygulamayı yeniden indirip kurun.') from exc
        raise MissingComponent(f'{feature} için gereken “{top}” paketi yok. {LOCAL_HINT}') from exc
