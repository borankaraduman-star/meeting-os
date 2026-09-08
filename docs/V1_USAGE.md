# Meeting OS V1 — yerel çalışma

## Akış

Kayıt → canlı transkript → nihai transkript → yerel analiz → kaynaklı özet/kararlar/riskler/sorular/görevler → elle doğrulama → yerel taslak → elle dosya dışa aktarımı.

Konuşmacı adı ve metin düzenlemesi özet/görevleri eski işaretler. Güncel analizi yeniden oluşturun. Elle düzenlenen görev alanları ve durumlar korunur. Kaldırılan görevler geçmiş için kalır. Aynı başlık+alıntı görev kimliğini korur; başlık veya alıntısı farklı yeni çıkarımlar ayrı öneri olabilir. Kaldırıldı durumuyla tekrarları ayıklayabilirsiniz.

Yerel model, geçerli JSON veya doğru kaynak üretmezse işlem başarısız olur; eski başarılı analiz korunur. İkinci deneme de doğrulanmazsa hatayı arayüzde görürsünüz. Analizin anlamsal doğruluğu garanti değildir: alıntının gerçekten mevcut olması, yorumu tek başına kanıtlamaz. İnsan incelemesi gerekir.

Görevde önerilen araç basit yerel anahtar kelime kuralıdır. Ücret, hesap veya dış bağlantı başlatmaz. Hazırlanan paket otomatik çalıştırılmaz. Slack/Jira/Gmail/Calendar entegrasyonu otomatik kurulmaz, mesaj/ticket/takvim daveti gönderilmez.

## Komutlar

Proje klasöründen, `--db` alt komuttan önce:

```sh
.venv/bin/python -m meeting_os analyze MEETING_ID
.venv/bin/python -m meeting_os analyze MEETING_ID --force
.venv/bin/python -m meeting_os actions --owner Boran
.venv/bin/python -m meeting_os action-update TASK_ID --state in_progress
.venv/bin/python -m meeting_os action-update TASK_ID --owner 'Ece' --due-text 'cuma'
.venv/bin/python -m meeting_os prepare TASK_ID
.venv/bin/python -m meeting_os handoff TASK_ID /local/path/task.md
.venv/bin/python -m meeting_os search 'onboarding' --speaker 'Boran'
.venv/bin/python -m meeting_os ask 'onboarding PRD' --output /local/path/answer.json
```

`analyze` aynı kaynak için önceden başarılı analiz varsa modeli yeniden çağırmaz.
`--force` yeniden üretir. `prepare TASK_ID --force` yeni bir taslak sürümü üretir;
normal `prepare` güncel taslağı tekrar kullanır. Elle düzenlemeler geçmişte kalır. CLI `import/finalize` yalnızca transkript üretir; CLI'de
ardından `analyze` çağırın. Mac arayüzü bu sıralamayı otomatik yapar. Ses modeli
ile analiz modeli ayrı işlemlerde sırayla yüklenir.

## Salt okunur MCP

Sunucu sadece standart giriş/çıkış kullanır; ağ portu açmaz. Bir harici AI
uygulamasına bağlamak, sorguladığı metinleri o uygulamaya verir; bu bağlantı
otomatik kurulmamıştır. Yalnızca bilinçli olarak bağlamak istediğiniz istemciye
şu yerel komutu tanıtın:

```text
command: /Users/boran/Library/Application Support/MeetingOS/repo-v0.1/.venv/bin/python
args: ["-m", "meeting_os", "mcp"]
```

Araçlar: `list_meetings`, `search_meetings`, `get_meeting`, `list_actions`,
`speaker_contributions`. Sayfalı listeler 50 bölüm/görev döndürür. Ses dosya
yolları ve ses vektörleri dışa verilmez. Yazma, görev çalıştırma ve mesaj gönderme
aracı yoktur. JSON-RPC, MCP 2025-06-18 stdio transport kullanır.

## Kaliteyi tekrar ölç

```sh
.venv/bin/python scripts/benchmark-analysis.py --output /local/path/analysis.json
.venv/bin/python -m unittest discover -s tests -v
```

Kurgu metin testleri iptal/öneri, açık sahiplik/belirsiz sahiplik, Türkçe-İngilizce
PM jargonunu ve konuşmanın içine gömülmüş talimatları içerir. Bu metin testleri
STT doğruluğunu veya doğal toplantıda görev precision/recall değerini ölçmez.
Gerçek toplantı benchmark rehberi `BENCHMARK.md` içindedir.

Kaynaklar: [MLX-LM ile yapılandırılmış üretim](https://dottxt-ai.github.io/outlines/latest/features/models/mlxlm/),
[MCP stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports),
[Qwen3-4B model kartı](https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit).

`mcp-config.example.json` bu Mac için örnek yapılandırmadır; otomatik uygulanmaz.
