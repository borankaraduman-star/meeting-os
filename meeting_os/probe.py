"""Self-test. One command a teammate can run (or the nightly heartbeat can run for them) that says, in
plain Turkish, whether this Mac can record, transcribe and keep its data — before the meeting, not
during it. Every check is cheap and local unless `network=True`."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MIN_FREE_BYTES = 3 * 1024**3        # same warning line as the capture helper


def _item(key, ok, detail, fix=None, level='error'):
    d = {'key': key, 'ok': bool(ok), 'detail': detail}
    if not ok: d['fix'] = fix; d['level'] = level
    return d


def run(root, data_dir, *, network=False, timeout=8):
    root = Path(root); data = Path(data_dir); items = []
    items.append(_item('python', sys.version_info >= (3, 12), f'Python {sys.version.split()[0]}', 'scripts/install.sh yeniden çalıştırın'))
    ffmpeg = shutil.which('ffmpeg') or ('/opt/homebrew/bin/ffmpeg' if os.access('/opt/homebrew/bin/ffmpeg', os.X_OK) else None)
    items.append(_item('ffmpeg', bool(ffmpeg), ffmpeg or 'ffmpeg yok', 'brew install ffmpeg'))
    helper = root / 'build/MeetingCapture.app/Contents/MacOS/MeetingCapture'
    if helper.exists():
        try:
            with tempfile.TemporaryDirectory() as tmp:
                r = subprocess.run([str(helper), '--output', tmp, '--self-test'], capture_output=True, text=True, timeout=timeout)
                wrote = sorted(p.name for p in Path(tmp).glob('*.wav'))
            items.append(_item('capture_helper', r.returncode == 0 and len(wrote) >= 2, 'kayıt yardımcısı öz-testi geçti' if r.returncode == 0 else (r.stderr or r.stdout or f'çıkış {r.returncode}').strip()[:200], 'sh scripts/build-capture.sh'))
        except Exception as exc: items.append(_item('capture_helper', False, str(exc)[:200], 'sh scripts/build-capture.sh'))
    else: items.append(_item('capture_helper', False, 'kayıt yardımcısı derlenmemiş', 'sh scripts/build-capture.sh'))
    try:
        import resemblyzer  # noqa: F401
        items.append(_item('speaker_model', True, 'Resemblyzer hazır'))
    except Exception as exc: items.append(_item('speaker_model', False, f'Resemblyzer yüklenemedi: {str(exc)[:120]}', '.venv/bin/python -m pip install -e ".[speakers]"'))
    db = data / 'meeting-os.sqlite'
    if db.exists():
        try:
            con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
            verdict = con.execute('PRAGMA quick_check').fetchone()[0]; meetings = con.execute('SELECT count(*) FROM meetings').fetchone()[0]; con.close()
            items.append(_item('database', verdict == 'ok', f'{meetings} toplantı · quick_check {verdict}', 'Boran’a tanılama raporu gönderin; veritabanı yedekten kurtarılır'))
        except Exception as exc: items.append(_item('database', False, str(exc)[:160], 'Boran’a tanılama raporu gönderin'))
    else: items.append(_item('database', True, 'henüz toplantı yok'))
    try:
        data.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data, prefix='.probe-', delete=True): pass
        items.append(_item('data_writable', True, str(data)))
    except Exception as exc: items.append(_item('data_writable', False, str(exc)[:160], 'Klasör izinlerini kontrol edin'))
    try:
        free = shutil.disk_usage(data if data.is_dir() else data.parent).free
        items.append(_item('disk', free >= MIN_FREE_BYTES, f'{free/1024**3:.1f} GB boş', 'Eski sesleri temizleyin (Ayarlar → Depolama)', level='warning'))
    except OSError as exc: items.append(_item('disk', False, str(exc)[:120], None, level='warning'))
    try:
        from .openrouter import KEYCHAIN_SERVICE
        has_key = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', KEYCHAIN_SERVICE], capture_output=True, timeout=5).returncode == 0
    except Exception: has_key = False
    items.append(_item('api_key', has_key, 'OpenRouter anahtarı Keychain’de' if has_key else 'OpenRouter anahtarı yok', 'Ayarlar → OpenRouter → anahtarı yapıştırın'))
    try:
        from . import glossary as G
        entries = G.load(data, root); items.append(_item('glossary', True, f'{len(entries)} terim'))
    except Exception as exc: items.append(_item('glossary', False, str(exc)[:160], 'Sözlük dosyasını Ayarlar’dan yeniden içe aktarın', level='warning'))
    try:
        from .reports import load_settings, host_dir
        rs = load_settings(data); folder = host_dir(rs)
        if rs.get('share_reports'):
            anchor = folder
            while not anchor.exists() and anchor.parent != anchor: anchor = anchor.parent
            items.append(_item('reports', os.access(anchor, os.W_OK), str(folder), 'Ayarlar → Güncelleme ve raporlar → klasörü seçin', level='warning'))
        else: items.append(_item('reports', True, 'rapor paylaşımı kapalı'))
    except Exception as exc: items.append(_item('reports', False, str(exc)[:160], None, level='warning'))
    if network:
        try:
            import urllib.request
            req = urllib.request.Request('https://openrouter.ai/api/v1/models', method='HEAD', headers={'User-Agent': 'meeting-os-probe'})
            with urllib.request.urlopen(req, timeout=timeout) as resp: items.append(_item('openrouter', resp.status < 500, f'openrouter.ai HTTP {resp.status}'))
        except Exception as exc: items.append(_item('openrouter', False, f'openrouter.ai erişilemedi: {str(exc)[:100]}', 'İnternet bağlantısını kontrol edin', level='warning'))
    failed = [i for i in items if not i['ok'] and i.get('level') == 'error']; warned = [i for i in items if not i['ok'] and i.get('level') == 'warning']
    return {'ok': not failed, 'failed': [i['key'] for i in failed], 'warnings': [i['key'] for i in warned], 'items': items, 'at': datetime.now(timezone.utc).isoformat()}


def summary_line(result):
    if result['ok'] and not result['warnings']: return 'Öz-test temiz'
    names = {'python': 'Python', 'ffmpeg': 'ffmpeg', 'capture_helper': 'kayıt yardımcısı', 'speaker_model': 'ses modeli', 'database': 'veritabanı', 'data_writable': 'veri klasörü', 'disk': 'disk', 'api_key': 'OpenRouter anahtarı', 'glossary': 'sözlük', 'reports': 'raporlar', 'openrouter': 'OpenRouter erişimi'}
    parts = [names.get(k, k) for k in result['failed']] + [names.get(k, k) + ' (uyarı)' for k in result['warnings']]
    return 'Öz-test: ' + ', '.join(parts)


def main(argv=None):
    import argparse
    from .cli import DATA_DIR, ROOT
    ap = argparse.ArgumentParser(prog='meeting_os probe'); ap.add_argument('--network', action='store_true'); ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    result = run(ROOT, DATA_DIR, network=a.network)
    if a.json: print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for i in result['items']: print(('✔ ' if i['ok'] else ('! ' if i.get('level') == 'warning' else '✘ ')) + i['key'] + ': ' + i['detail'] + ('' if i['ok'] or not i.get('fix') else ' → ' + i['fix']))
        print(summary_line(result))
    return 0 if result['ok'] else 1
