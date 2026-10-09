#!/usr/bin/env python3
"""Generate a static puzzle viewer page for the public GitHub Pages site.

This script is intentionally resilient in CI: it never reads from the Android /sdcard
folder and it does not require pre-generated puzzle slices to exist. The page renders
with the tile catalog and relative image paths, so it can be published under /puzzle/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TILES_YAML = ROOT / 'modules/06_interior/extracts/bathroom-tiles-85.yaml'
DEFAULT_OUTPUT = ROOT / 'puzzle' / 'index.html'


def load_tiles(tile_path: Path):
    if not tile_path.is_file():
        raise FileNotFoundError(f'Missing tile catalog: {tile_path}')

    with tile_path.open('r', encoding='utf-8') as handle:
        data = yaml.safe_load(handle) or {}

    tiles = []
    for tile in data.get('tiles', []):
        index = int(tile['index'])
        tiles.append({
            'index': index,
            'label': tile.get('label', f'{index}. {tile.get("slug", "")}'),
            'manufacturer': tile.get('manufacturer', ''),
            'product': tile.get('product', ''),
            'format': tile.get('format', ''),
            'base_entrance': f'{index:02d}_tile',
            'base_reverse': f'{index:02d}_tile',
        })
    return tiles


def render_html(tiles):
    return f"""<!DOCTYPE html>
<html lang=\"pl\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Kreator Puzzli Łazienki</title>
  <style>
    :root {{
      --bg: #121417;
      --card-bg: #1e2228;
      --card-border: #2e3440;
      --accent: #3b82f6;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --soft: #1c2a35;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); min-height: 100vh; padding: 16px; }}
    header {{ max-width: 1200px; margin: 0 auto 16px; text-align: center; }}
    h1 {{ font-size: clamp(1.6rem, 2vw, 2.2rem); margin-bottom: 8px; }}
    .subtitle {{ color: var(--text-muted); font-size: 0.95rem; }}
    .notice {{
      max-width: 1200px; margin: 0 auto 16px; background: rgba(30, 58, 63, 0.72); border: 1px solid #2a5f6f; border-radius: 12px;
      color: #bae6fd; padding: 12px 14px; line-height: 1.5;
    }}
    .layout {{ max-width: 1200px; margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(300px, 1fr); gap: 16px; }}
    .viewer, .controls {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.18); padding: 12px; }}
    .stage {{ position: relative; width: 100%; aspect-ratio: 2000 / 1600; background: #000; border-radius: 8px; overflow: hidden; }}
    .stage img {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }}
    .camera-switcher {{ display: flex; gap: 8px; margin-bottom: 12px; }}
    .cam-btn, .btn {{ border: 1px solid var(--card-border); border-radius: 8px; background: #1c2430; color: var(--text); padding: 10px 12px; font-weight: 600; cursor: pointer; }}
    .cam-btn.active, .btn-primary {{ background: var(--accent); border-color: var(--accent); color: white; }}
    .surface {{ margin-bottom: 12px; }}
    .surface-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-weight: 600; }}
    .tag {{ background: var(--soft); border: 1px solid #2d4c5d; color: #93c5fd; border-radius: 999px; padding: 4px 8px; font-size: 0.72rem; }}
    select {{ width: 100%; padding: 10px 12px; border: 1px solid #374151; border-radius: 8px; background: #141a20; color: var(--text); font-size: 0.95rem; }}
    .btn-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }}
    .cli {{ background: #131a1f; border: 1px solid var(--card-border); border-radius: 8px; color: #7dd3fc; padding: 10px 12px; margin-top: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.76rem; word-break: break-all; }}
    .toolbar {{ margin-top: 14px; }}
    a {{ color: #7dd3fc; text-decoration: none; }}
    @media (max-width: 840px) {{ .layout {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>🧩 Kreator Puzzli Łazienki</h1>
    <div class=\"subtitle\">Główny portal pozostaje pod <code>/</code>, a ten widok działa osobno pod <code>/puzzle/</code>.</div>
  </header>

  <div class=\"notice\">
    Ta strona jest publikowana jako osobna podstrona GitHub Pages. Utrzymany zostaje obecny portal główny, natomiast puzzle ma odrębny adres pod <strong>/puzzle/</strong>.
    Wersja statyczna nie wymaga dostępu do lokalnych zasobów — obrazy mogą być podłączone w katalogu podstrony.
  </div>

  <div class=\"layout\">
    <div class=\"viewer\">
      <div class=\"stage\">
        <img id=\"layer-sufit\" alt=\"Sufit\">
        <img id=\"layer-sciana_srodkowa\" alt=\"Ściana środkowa\">
        <img id=\"layer-sciana_lewa\" alt=\"Ściana lewa\">
        <img id=\"layer-sciana_prawa\" alt=\"Ściana prawa\">
        <img id=\"layer-podloga\" alt=\"Podłoga\">
      </div>
    </div>

    <div class=\"controls\">
      <div class=\"camera-switcher\">
        <button id=\"cam-entrance\" class=\"cam-btn active\" type=\"button\">Wejście</button>
        <button id=\"cam-reverse\" class=\"cam-btn\" type=\"button\">Odwrócone</button>
      </div>

      <div class=\"surface\">
        <div class=\"surface-head\"><span>Podłoga</span><span id=\"tag-podloga\" class=\"tag\"></span></div>
        <select id=\"sel-podloga\"></select>
      </div>
      <div class=\"surface\">
        <div class=\"surface-head\"><span>Ściana lewa</span><span id=\"tag-sciana_lewa\" class=\"tag\"></span></div>
        <select id=\"sel-sciana_lewa\"></select>
      </div>
      <div class=\"surface\">
        <div class=\"surface-head\"><span>Ściana środkowa</span><span id=\"tag-sciana_srodkowa\" class=\"tag\"></span></div>
        <select id=\"sel-sciana_srodkowa\"></select>
      </div>
      <div class=\"surface\">
        <div class=\"surface-head\"><span>Ściana prawa</span><span id=\"tag-sciana_prawa\" class=\"tag\"></span></div>
        <select id=\"sel-sciana_prawa\"></select>
      </div>
      <div class=\"surface\">
        <div class=\"surface-head\"><span>Sufit</span><span id=\"tag-sufit\" class=\"tag\"></span></div>
        <select id=\"sel-sufit\"></select>
      </div>

      <div class=\"btn-row\">
        <button class=\"btn\" type=\"button\" id=\"btn-random\">Losuj</button>
        <button class=\"btn btn-primary\" type=\"button\" id=\"btn-export\">Pobierz</button>
      </div>
      <div class=\"cli\" id=\"cli-cmd\"></div>

      <div class=\"toolbar\">
        <a href=\"../\">← Powrót do portalu</a>
      </div>
    </div>
  </div>

  <script>
    const TILES = {json.dumps(tiles, ensure_ascii=False)};
    const ZONES = ['podloga', 'sciana_lewa', 'sciana_srodkowa', 'sciana_prawa', 'sufit'];
    let currentCamera = 'entrance';
    let currentSelections = {{
      podloga: 2,
      sciana_lewa: 1,
      sciana_srodkowa: 67,
      sciana_prawa: 22,
      sufit: 1
    }};

    function getTile(index) {{
      return TILES.find(tile => tile.index === index) || TILES[0];
    }}

    function updateCli() {{
      const command = `python scripts/combine_puzzle.py --camera ${{currentCamera}} --podloga ${{currentSelections.podloga}} --sciana-lewa ${{currentSelections.sciana_lewa}} --sciana-srodkowa ${{currentSelections.sciana_srodkowa}} --sciana-prawa ${{currentSelections.sciana_prawa}} --sufit ${{currentSelections.sufit}}`;
      document.getElementById('cli-cmd').textContent = command;
    }}

    function setCamera(camera) {{
      currentCamera = camera;
      document.getElementById('cam-entrance').classList.toggle('active', camera === 'entrance');
      document.getElementById('cam-reverse').classList.toggle('active', camera === 'reverse');
      ZONES.forEach(zone => updateLayer(zone));
      updateCli();
    }}

    function updateLayer(zone) {{
      const tile = getTile(currentSelections[zone]);
      const base = currentCamera === 'entrance' ? tile.base_entrance : tile.base_reverse;
      const image = `./${{currentCamera}}/${{zone}}/${{base}}_${{zone}}.png`;
      const el = document.getElementById('layer-' + zone);
      if (el) {{
        el.src = image;
        el.onerror = () => {{ el.style.display = 'none'; }};
      }}
      const tag = document.getElementById('tag-' + zone);
      if (tag) tag.textContent = `${{tile.manufacturer}} #${{tile.index}}`;
    }}

    function updateAll() {{
      ZONES.forEach(zone => {{
        const select = document.getElementById('sel-' + zone);
        select.innerHTML = '';
        TILES.forEach(tile => {{
          const option = document.createElement('option');
          option.value = String(tile.index);
          option.textContent = `${{String(tile.index).padStart(2, '0')}}. ${{tile.manufacturer}} - ${{tile.product}} (${{tile.format}})`;
          if (tile.index === currentSelections[zone]) option.selected = true;
          select.appendChild(option);
        }});
      }});
      ZONES.forEach(zone => updateLayer(zone));
      updateCli();
    }}

    document.getElementById('cam-entrance').addEventListener('click', () => setCamera('entrance'));
    document.getElementById('cam-reverse').addEventListener('click', () => setCamera('reverse'));
    document.getElementById('btn-random').addEventListener('click', () => {{
      ZONES.forEach(zone => {{
        const randomTile = TILES[Math.floor(Math.random() * TILES.length)];
        currentSelections[zone] = randomTile.index;
        document.getElementById('sel-' + zone).value = String(randomTile.index);
      }});
      ZONES.forEach(zone => updateLayer(zone));
      updateCli();
    }});
    document.getElementById('btn-export').addEventListener('click', () => {{
      alert('Wersja statyczna. W pełnym środowisku puzzle generuje się lokalnie i eksportuje do katalogu puzzle/.\n\n' + document.getElementById('cli-cmd').textContent);
    }});

    ZONES.forEach(zone => {{
      document.getElementById('sel-' + zone).addEventListener('change', (event) => {{
        currentSelections[zone] = Number(event.target.value);
        updateLayer(zone);
        updateCli();
      }});
    }});

    updateAll();
  </script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tiles', type=Path, default=DEFAULT_TILES_YAML, help='Tile metadata YAML file')
    parser.add_argument('--output', '-o', type=Path, default=DEFAULT_OUTPUT, help='Output HTML file')
    args = parser.parse_args()

    tiles = load_tiles(args.tiles)
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(tiles), encoding='utf-8')
    print(f'Generated puzzle page: {output}')


if __name__ == '__main__':
    main()
