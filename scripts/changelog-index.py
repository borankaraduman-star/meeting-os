#!/usr/bin/env python3
"""One index for every version note: GitHub release bodies (public API, no token) plus docs/releases/*.md
(notes for tags whose GitHub release page is missing or amended). Writes docs/CHANGELOG.md and, with --html,
an HTML fragment for the live changelog page. Run after every `gh release create`:

    .venv/bin/python scripts/changelog-index.py            # docs/CHANGELOG.md
    .venv/bin/python scripts/changelog-index.py --html build/changelog-all.html
    .venv/bin/python scripts/changelog-index.py --cache build/releases.json   # reuse a saved API answer
"""
import argparse, html, json, re, sys, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = 'borankaraduman-star/meeting-os'
ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'docs'/'releases'
OUT = ROOT/'docs'/'CHANGELOG.md'
ISTANBUL = timezone(timedelta(hours=3))

# Every place a change is written down, oldest first. The changelog page and this file both link them so no log
# is ever an orphan again (Boran, 10 Sep 2026: "her biri bağımsız dosya gibi").
LOGS = [
    ('Sürüm günlüğü (canlı sayfa: kurul turları, sprint durumu, bütün sürümler)', 'https://claude.ai/code/artifact/ed7b851a-164d-4631-9322-e1bd84920425'),
    ('GitHub sürümleri (her etiketin notu ve kaynak paketi)', f'https://github.com/{REPO}/releases'),
    ('docs/CHANGELOG.md (bu dosya: bütün sürüm notları tek yerde)', 'CHANGELOG.md'),
    ('docs/AUTONOMY_2026-09-10.md (10 Eylül gece/gündüz özeti: sürüm tablosu, kök nedenler, canlı denenmeyenler, kararlar)', 'AUTONOMY_2026-09-10.md'),
    ('docs/AUTONOMY_2026-09-09.md (9 Eylül gece turu)', 'AUTONOMY_2026-09-09.md'),
    ('docs/ITERATION_CHECKPOINT.md (zaman damgalı çalışma notları, en yeni en altta)', 'ITERATION_CHECKPOINT.md'),
    ('docs/NIGHT_ITERATION.md (8 Eylül gece turu, yerel model dönemi)', 'NIGHT_ITERATION.md'),
    ('docs/TURKISH_PRECISION_CHECKPOINT.md · ASR_CHECKPOINT_PLAN.md · DIARIZATION_CHECKPOINT_PLAN.md (8–9 Eylül yerel ASR/diarization deneyleri; bulut yoluna geçildi)', 'TURKISH_PRECISION_CHECKPOINT.md'),
    ('Öğleden sonra günlüğü artefaktı (9 Eylül, 1.2.15–1.2.24)', 'https://claude.ai/code/artifact/bcf01c8b-0ee0-4a10-beb9-0bf08fcde922'),
    ('Boru hattı artefaktı (9 Eylül: kayıt → transkript → analiz şeması)', 'https://claude.ai/code/artifact/198c0af2-ed36-4f09-8cd8-5d10a22abb37'),
    ('Kullanım kılavuzu artefaktı (docs/KULLANIM.md görünümü)', 'https://claude.ai/code/artifact/add1379b-ccdb-4ae4-9f45-87982d385627'),
]


def vkey(tag):
    return tuple(int(x) for x in re.findall(r'\d+', tag))


def fetch(cache):
    if cache and Path(cache).is_file():
        return json.loads(Path(cache).read_text())
    req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/releases?per_page=100',
                                 headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'meeting-os-changelog'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if cache:
        Path(cache).parent.mkdir(parents=True, exist_ok=True); Path(cache).write_text(json.dumps(data))
    return data


def local_notes():
    """docs/releases/vX.Y.Z.md: first line `# title`, optional `Tarih: YYYY-MM-DD HH:MM`, then the body."""
    out = {}
    for p in sorted(LOCAL.glob('v*.md')) if LOCAL.is_dir() else []:
        lines = p.read_text().splitlines()
        title = lines[0].lstrip('# ').strip() if lines and lines[0].startswith('#') else p.stem
        date = ''
        body = lines[1:]
        if body and body[0].lower().startswith('tarih:'):
            date = body[0].split(':', 1)[1].strip(); body = body[1:]
        out[p.stem] = {'tag_name': p.stem, 'name': title, 'body': '\n'.join(body).strip(), 'date': date,
                       'html_url': f'https://github.com/{REPO}/releases/tag/{p.stem}', 'local': True}
    return out


def collect(cache):
    items = {}
    for r in fetch(cache):
        when = datetime.fromisoformat(r['created_at'].replace('Z', '+00:00')).astimezone(ISTANBUL)
        items[r['tag_name']] = {'tag_name': r['tag_name'], 'name': r['name'] or r['tag_name'], 'body': (r['body'] or '').strip(),
                                'date': when.strftime('%Y-%m-%d %H:%M'), 'html_url': r['html_url'], 'local': False}
    for tag, note in local_notes().items():
        if tag in items and not note['body']:
            continue
        if tag in items:
            note['date'] = note['date'] or items[tag]['date']; note['html_url'] = items[tag]['html_url']
        items[tag] = note
    return sorted(items.values(), key=lambda x: vkey(x['tag_name']), reverse=True)


def md_inline_to_html(s):
    s = html.escape(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'&lt;(https?://[^&]+)&gt;', r'<a href="\1">\1</a>', s)
    return s


def body_to_html(body):
    parts, para, items = [], [], []
    def flush():
        nonlocal para, items
        if para: parts.append('<p>' + md_inline_to_html(' '.join(para)) + '</p>'); para = []
        if items: parts.append('<ul>' + ''.join('<li>' + md_inline_to_html(i) + '</li>' for i in items) + '</ul>'); items = []
    for line in body.splitlines():
        t = line.strip()
        if not t:
            flush(); continue
        if t.startswith(('- ', '* ')):
            if para: flush()
            items.append(t[2:]); continue
        if t.startswith('#'):
            flush(); parts.append('<p><b>' + md_inline_to_html(t.lstrip('# ')) + '</b></p>'); continue
        if items and line.startswith('  '):
            items[-1] += ' ' + t; continue
        if items: flush()
        para.append(t)
    flush()
    return ''.join(parts)


def write_markdown(releases):
    lines = ['# Meeting OS — bütün sürüm notları', '',
             'Bu dosya `scripts/changelog-index.py` ile üretilir (GitHub sürüm notları + `docs/releases/*.md`). '
             f'{len(releases)} sürüm, en yeni en üstte. Diğer günlükler:', '']
    for label, url in LOGS:
        lines.append(f'- [{label}]({url})')
    lines += ['', '## Dizin', '', '| Sürüm | Tarih | Başlık |', '|---|---|---|']
    for r in releases:
        anchor = r['tag_name'].replace('.', '')
        lines.append(f"| [{r['tag_name']}](#{anchor}) | {r['date']} | {r['name']} |")
    lines += ['', '## Notlar', '']
    for r in releases:
        anchor = r['tag_name'].replace('.', '')
        src = 'yerel not · GitHub sürüm sayfası yok' if r['local'] else f"[GitHub]({r['html_url']})"
        lines += [f"<a id=\"{anchor}\"></a>", f"### {r['name']}", '', f"{r['date']} · {src}", '', r['body'] or '_(not yok)_', '']
    OUT.write_text('\n'.join(lines).rstrip() + '\n')


def write_html(releases, path):
    out = ['<h2 id="all-versions">Bütün sürümler</h2>',
           f'<p class="lede">{len(releases)} sürüm, en yeni en üstte; her başlık açılır. Aynı liste depoda <code>docs/CHANGELOG.md</code> olarak da durur.</p>']
    for r in releases:
        src = '' if r['local'] else f' · <a href="{html.escape(r["html_url"])}">GitHub</a>'
        out.append(f'<details class="rel"><summary><b>{html.escape(r["tag_name"])}</b> <span class="when">{html.escape(r["date"])}</span> {html.escape(r["name"])}{src}</summary>'
                   f'<div class="relbody">{body_to_html(r["body"]) or "<p><i>not yok</i></p>"}</div></details>')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text('\n'.join(out) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', help='JSON file with a saved GitHub releases answer (read if present, else written)')
    ap.add_argument('--html', help='also write an HTML fragment (details per version) to this path')
    a = ap.parse_args()
    releases = collect(a.cache)
    write_markdown(releases)
    if a.html:
        write_html(releases, a.html)
    print(json.dumps({'versions': len(releases), 'newest': releases[0]['tag_name'], 'markdown': str(OUT), 'html': a.html}))


if __name__ == '__main__':
    sys.exit(main())
