# Model, yazılım ve veri kaynakları

Uygulama kendi yerel kodudur. Üçüncü taraf paket ve modellerin kendi lisansları
geçerlidir; kaynak arşivi model ağırlıklarını veya Python paketlerini yeniden
dağıtmaz. Bu Mac’te indirilen ağırlıklar `models/` altında kalır.

- Apple ScreenCaptureKit / AVFoundation: macOS SDK. Ekran kareleri kaydedilmez.
- OpenAI Whisper: https://github.com/openai/whisper — MIT.
- MLX Whisper: https://github.com/ml-explore/mlx-examples/tree/main/whisper — MIT.
- whisper.cpp: https://github.com/ggml-org/whisper.cpp — MIT; build scriptinde
  commit sabittir. Quantized model repository: https://huggingface.co/ggerganov/whisper.cpp .
- Silero VAD: https://github.com/snakers4/silero-vad — MIT.
- Resemblyzer: https://github.com/resemble-ai/Resemblyzer — Apache-2.0;
  model paket içindeki `pretrained.pt` dosyasıdır, profil namespace SHA256 içerir.
- SpeechBrain ECAPA: https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb .
- sherpa-onnx: https://github.com/k2-fsa/sherpa-onnx — Apache-2.0.
  Modeller: https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/models.html .
  Kullanılan pyannote segmentation 3.0 ONNX arşivi kendi MIT/CNRS lisansını
  içerir. TitaNet-small ONNX, resmî `speaker-recongition-models` release’indendir;
  NVIDIA/NeMo model kaynağına ait koşullar ayrıca geçerlidir. İndirme URL’leri
  ve SHA256 değerleri `meeting_os/models.py` içindedir. Reverb kullanılmadı.
- İsteğe bağlı pyannote Community-1: https://huggingface.co/pyannote/speaker-diarization-community-1 .
  Gated model indirilmedi; kullanıcı tarafından sağlanan yerel pipeline adaptörü
  dışında varsayılan bağımlılık değildir.
- ffmpeg: https://ffmpeg.org/ — kurulu binary’nin build lisansı geçerlidir;
  kaynak paketimiz binary’yi içermez.

## Test verileri

- Google FLEURS: https://huggingface.co/datasets/google/fleurs — CC-BY-4.0.
  Turkish test split ilk 12 satır, `raw_transcription` referansı. Ses kopyaları
  yeniden PCM WAV olarak yazıldı. `benchmarks/fleurs-tr/SOURCE.md`.
- LibriSpeech / Vassil Panayotov, Daniel Povey ve çalışma arkadaşları:
  https://www.openslr.org/12/ — CC-BY-4.0. Dev-clean sesleri; konuşmacı testleri
  farklı utterance’ları ayırır. Dört sesli fixture 250 ms boşluklarla birleştirilmiş
  türevdir. Doğal toplantı değildir. Scriptler yeniden üretilebilir seçimi tanımlar.
- Resmî sherpa test sesi `0-four-speakers-zh.wav` yalnızca yerel deney için
  önbelleğe indirildi; kaynak paketine dahil değildir.
- macOS Yelda/Samantha sesleriyle üretilen sentetik Türkçe ve code-switch
  fixture’ları yalnızca işlev/karşılaştırma testidir; gerçek kişiyi taklit etmez.

CC-BY-4.0 metni: https://creativecommons.org/licenses/by/4.0/ .
Test verilerinden kimlik güvenilirliği veya toplantı doğruluğu garantisi çıkarılmaz.
