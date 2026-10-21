"""Resemblyzer'in ses izi ağını (pretrained.pt) bir kez ONNX'e çevirir; paket torch taşımasın diye.

Yalnız ağ çevrilir: mel girişi (parça, 160 kare, 40 kanal) → L2 normlu parça vektörleri (parça, 256). Ön işleme
(mel, kısmi pencereleme, ortalama + L2) `meeting_os/voice_encoder.py` içinde numpy ile, Resemblyzer'in kendi
kodunun birebir karşılığıdır. Çıktı `meeting_os/assets/resemblyzer.onnx`; kaynak .pt'nin sha256'sı modelin
metadata'sına (`source_sha256`) yazılır ve `voice_encoder.SOURCE_SHA256` ile aynı olmalıdır — kayıtlı ses
profillerinin `model_id`'si o özetten gelir (docs/BUNDLE.md "Ses izi ve VAD: torch'suz").

Bu betik torch + Resemblyzer ister (requirements-local-models.txt); paketlenmiş uygulama değil, geliştirici Mac'i
çalıştırır:

    .venv/bin/python scripts/convert-resemblyzer-onnx.py [--weights pretrained.pt] [--output meeting_os/assets/resemblyzer.onnx]

Yeni dosyanın sha256'sı `voice_encoder.ONNX_SHA256`'ya yazılmadan kod onu kanonik model saymaz; sonra
`tests/test_onnx_equivalence.py` torch ile eşdeğerliği (kosinüs ≥ 0.9999) yeniden kanıtlamalıdır.
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--weights', type=Path)
    p.add_argument('--output', type=Path, default=ROOT/'meeting_os/assets/resemblyzer.onnx')
    p.add_argument('--opset', type=int, default=17)
    args = p.parse_args(argv)

    import numpy as np
    import onnx
    import torch
    import resemblyzer
    from resemblyzer import VoiceEncoder
    from resemblyzer.hparams import partials_n_frames, mel_n_channels

    weights = args.weights or Path(resemblyzer.__file__).parent/'pretrained.pt'
    source_sha = hashlib.sha256(weights.read_bytes()).hexdigest()
    encoder = VoiceEncoder(device='cpu', weights_fpath=weights, verbose=False).eval()
    torch.manual_seed(0)
    example = torch.rand(2, partials_n_frames, mel_n_channels)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # dynamo=False: TorchScript dışa aktarıcısı LSTM'i tek bir ONNX LSTM düğümüne çevirir ve ek paket istemez.
    torch.onnx.export(encoder, (example,), str(args.output), input_names=['mels'], output_names=['embeds'],
                      dynamic_axes={'mels': {0: 'partials'}, 'embeds': {0: 'partials'}},
                      opset_version=args.opset, do_constant_folding=True, dynamo=False)
    model = onnx.load(str(args.output))
    del model.metadata_props[:]
    for key, value in (('source', 'Resemblyzer==0.1.4 pretrained.pt (Apache-2.0)'), ('source_sha256', source_sha),
                       ('input', 'mels float32 [partials,160,40], librosa melspectrogram (power) .T'),
                       ('output', 'embeds float32 [partials,256], relu + L2')):
        entry = model.metadata_props.add(); entry.key = key; entry.value = value
    model.producer_name = 'meeting-os/scripts/convert-resemblyzer-onnx.py'
    onnx.checker.check_model(model)
    onnx.save(model, str(args.output))

    import onnxruntime as ort
    session = ort.InferenceSession(str(args.output), providers=['CPUExecutionProvider'])
    probe = torch.rand(5, partials_n_frames, mel_n_channels)
    with torch.no_grad(): expected = encoder(probe).numpy()
    actual = session.run(None, {'mels': probe.numpy()})[0]
    cos = (expected*actual).sum(1)/np.linalg.norm(expected, axis=1)/np.linalg.norm(actual, axis=1)
    out_sha = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(f'yazıldı: {args.output} ({args.output.stat().st_size} bayt)')
    print(f'kaynak sha256: {source_sha}')
    print(f'onnx   sha256: {out_sha}')
    print(f'rastgele mel girişinde parça kosinüsü min {cos.min():.9f}, en büyük mutlak fark {np.abs(expected-actual).max():.3e}')
    if cos.min() < 0.9999: sys.exit('ONNX çıktısı torch ile eşleşmiyor')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
