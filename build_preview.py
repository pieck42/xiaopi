"""Embed the original PNGs into a portable, single-file preview."""
from pathlib import Path
import base64
import json

ROOT = Path(__file__).resolve().parent
html = (ROOT / 'preview.template.html').read_text(encoding='utf-8')
html = html.replace('__ANIMATION_SCRIPT__', (ROOT / 'preview-animation.js').read_text(encoding='utf-8'))
for name in ('fox', 'dragon'):
    data = base64.b64encode((ROOT / 'assets' / f'{name}-actions-v2.png').read_bytes()).decode()
    html = html.replace(f'__{name.upper()}_DATA__', 'data:image/png;base64,' + data)
manifest = json.loads((ROOT / 'assets' / 'animations.json').read_text(encoding='utf-8'))
html = html.replace('__ANIMATION_MANIFEST__', json.dumps(manifest, ensure_ascii=False))
(ROOT / '小皮预览.html').write_text(html, encoding='utf-8')
print('Built self-contained preview')
