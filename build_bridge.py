"""Build the zero-dependency Cindy plugin entry; no installation or networking."""
from pathlib import Path

root = Path(__file__).resolve().parent / 'cindy-bridge'
source = '\n\n'.join((root / name).read_text(encoding='utf-8') for name in ('core.js', 'entry.js'))
(root / 'main.js').write_text(source, encoding='utf-8')
print('Built cindy-bridge/main.js')
