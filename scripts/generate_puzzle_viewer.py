#!/usr/bin/env python3
"""Generates an interactive, standalone offline HTML puzzle viewer/configurator for bathroom tiles.

Saves index.html directly into /sdcard/Download/Dom_Lazienka_R07_Puzzle/index.html
"""
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
TILES_YAML = ROOT / 'modules/06_interior/extracts/bathroom-tiles-85.yaml'
PUZZLE_DIR = Path('/sdcard/Download/Dom_Lazienka_R07_Puzzle')
OUT_HTML = PUZZLE_DIR / 'index.html'

with open(TILES_YAML, 'r', encoding='utf-8') as f:
    tiles_data = yaml.safe_load(f).get('tiles', [])

# Map of available tiles
tiles_list = []
entrance_files = set(p.name for p in (PUZZLE_DIR / 'entrance' / 'podloga').glob('*.png'))

for t in tiles_data:
    idx = t['index']
    prefix = f"{idx:02d}_"
    match = [f for f in entrance_files if f.startswith(prefix)]
    if not match:
        continue
    # Extract filename template: e.g. "01_cersanit_ikarus_white_matt_entrance_dimmed50"
    base_entrance = match[0].replace('_podloga.png', '')
    base_reverse = base_entrance.replace('_entrance_', '_reverse_')

    tiles_list.append({
        'index': idx,
        'label': t.get('label', f"{idx}. {t.get('slug', '')}"),
        'manufacturer': t.get('manufacturer', ''),
        'product': t.get('product', ''),
        'format': t.get('format', ''),
        'base_entrance': base_entrance,
        'base_reverse': base_reverse,
    })

print(f"Loaded {len(tiles_list)} active tiles for puzzle viewer.")

html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kreator Puzzli Łazienki - Mikser Płytek</title>
  <style>
    :root {{
      --bg: #121417;
      --card-bg: #1e2228;
      --card-border: #2e3440;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); padding: 12px; display: flex; flex-direction: column; align-items: center; min-height: 100vh; }}
    header {{ text-align: center; margin-bottom: 14px; max-width: 900px; width: 100%; }}
    h1 {{ font-size: 1.4rem; color: #fff; margin-bottom: 4px; }}
    p.subtitle {{ font-size: 0.85rem; color: var(--text-muted); }}

    .main-layout {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
      max-width: 1200px;
      width: 100%;
    }}
    @media (min-width: 900px) {{
      .main-layout {{ grid-template-columns: 3fr 2fr; align-items: start; }}
    }}

    /* Viewer Container */
    .viewer-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 10px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    }}
    .stage-wrapper {{
      position: relative;
      width: 100%;
      aspect-ratio: 2000 / 1600;
      background: #000;
      border-radius: 8px;
      overflow: hidden;
    }}
    .stage-layer {{
      position: absolute;
      top: 0; left: 0;
      width: 100%; height: 100%;
      pointer-events: none;
      object-fit: cover;
      transition: opacity 0.15s ease-out;
    }}

    /* Controls */
    .controls-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}
    .camera-switcher {{
      display: flex;
      gap: 8px;
      background: #14171c;
      padding: 4px;
      border-radius: 8px;
    }}
    .cam-btn {{
      flex: 1;
      padding: 8px 12px;
      border: none;
      background: transparent;
      color: var(--text-muted);
      border-radius: 6px;
      cursor: pointer;
      font-weight: 600;
      font-size: 0.85rem;
      transition: all 0.2s;
    }}
    .cam-btn.active {{
      background: var(--accent);
      color: #fff;
    }}

    .surface-group {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .surface-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.82rem;
      font-weight: 600;
      color: #d1d5db;
    }}
    .surface-tag {{
      font-size: 0.72rem;
      padding: 2px 6px;
      border-radius: 4px;
      background: #2a313d;
      color: #93c5fd;
    }}
    select {{
      width: 100%;
      background: #14171c;
      color: #f9fafb;
      border: 1px solid #374151;
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 0.85rem;
      outline: none;
      cursor: pointer;
    }}
    select:focus {{
      border-color: var(--accent);
    }}

    .button-row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 6px;
    }}
    .btn {{
      padding: 10px 14px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 0.85rem;
      cursor: pointer;
      border: none;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      transition: background 0.15s;
    }}
    .btn-secondary {{
      background: #2a313d;
      color: #e5e7eb;
    }}
    .btn-secondary:hover {{
      background: #374151;
    }}
    .btn-primary {{
      background: var(--accent);
      color: #fff;
      grid-column: span 2;
    }}
    .btn-primary:hover {{
      background: var(--accent-hover);
    }}

    .cli-box {{
      background: #14171c;
      border: 1px solid #2e3440;
      border-radius: 6px;
      padding: 8px 10px;
      font-family: monospace;
      font-size: 0.72rem;
      color: #60a5fa;
      word-break: break-all;
      user-select: all;
      cursor: pointer;
    }}
  </style>
</head>
<body>

  <header>
    <h1>🧩 Kreator Puzzli Łazienki</h1>
    <p class="subtitle">Wybierz płytki dla każdej z 5 płaszczyzn i zobacz natychmiastowy podgląd w wysokiej rozdzielczości</p>
  </header>

  <div class="main-layout">
    <!-- Podgląd (5 nałożonych warstw) -->
    <div class="viewer-card">
      <div class="stage-wrapper" id="stage">
        <img id="layer-sufit" class="stage-layer" alt="Sufit" crossorigin="anonymous">
        <img id="layer-sciana_srodkowa" class="stage-layer" alt="Ściana środkowa" crossorigin="anonymous">
        <img id="layer-sciana_lewa" class="stage-layer" alt="Ściana lewa" crossorigin="anonymous">
        <img id="layer-sciana_prawa" class="stage-layer" alt="Ściana prawa" crossorigin="anonymous">
        <img id="layer-podloga" class="stage-layer" alt="Podłoga" crossorigin="anonymous">
      </div>
    </div>

    <!-- Panel sterowania -->
    <div class="controls-card">
      <div class="camera-switcher">
        <button id="cam-entrance" class="cam-btn active" onclick="setCamera('entrance')">👁️ Wejście (Entrance)</button>
        <button id="cam-reverse" class="cam-btn" onclick="setCamera('reverse')">🔄 Odwrócony (Reverse)</button>
      </div>

      <div class="surface-group">
        <div class="surface-header">
          <span>🛋️ Podłoga</span>
          <span class="surface-tag" id="tag-podloga"></span>
        </div>
        <select id="sel-podloga" onchange="updateSurface('podloga')"></select>
      </div>

      <div class="surface-group">
        <div class="surface-header">
          <span>🧱 Ściana lewa</span>
          <span class="surface-tag" id="tag-sciana_lewa"></span>
        </div>
        <select id="sel-sciana_lewa" onchange="updateSurface('sciana_lewa')"></select>
      </div>

      <div class="surface-group">
        <div class="surface-header">
          <span>🚿 Ściana środkowa (akcentowa)</span>
          <span class="surface-tag" id="tag-sciana_srodkowa"></span>
        </div>
        <select id="sel-sciana_srodkowa" onchange="updateSurface('sciana_srodkowa')"></select>
      </div>

      <div class="surface-group">
        <div class="surface-header">
          <span>🧱 Ściana prawa</span>
          <span class="surface-tag" id="tag-sciana_prawa"></span>
        </div>
        <select id="sel-sciana_prawa" onchange="updateSurface('sciana_prawa')"></select>
      </div>

      <div class="surface-group">
        <div class="surface-header">
          <span>💡 Sufit</span>
          <span class="surface-tag" id="tag-sufit"></span>
        </div>
        <select id="sel-sufit" onchange="updateSurface('sufit')"></select>
      </div>

      <div class="button-row">
        <button class="btn btn-secondary" onclick="randomizeAll()">🎲 Losuj zestaw</button>
        <button class="btn btn-secondary" onclick="matchAllWallsToMiddle()">🎯 Wszystkie ściany jak śr.</button>
        <button class="btn btn-primary" onclick="downloadComposite()">💾 Pobierz / Zapisz render (PNG)</button>
      </div>

      <div style="font-size: 0.75rem; color: #9ca3af; margin-top: 4px;">
        Komenda Python do wygenerowania tego miksu:
      </div>
      <div class="cli-box" id="cli-cmd" title="Kliknij, aby skopiować" onclick="copyCliCmd()"></div>
    </div>
  </div>

  <canvas id="export-canvas" width="2000" height="1600" style="display: none;"></canvas>

  <script>
    const TILES = {json.dumps(tiles_list, ensure_ascii=False)};
    const ZONES = ['podloga', 'sciana_lewa', 'sciana_srodkowa', 'sciana_prawa', 'sufit'];
    
    let currentCamera = 'entrance';
    let currentSelections = {{
      podloga: 2,           // Tubądzin Travertino 57
      sciana_lewa: 1,       // Cersanit Ikarus White
      sciana_srodkowa: 67,  // Opoczno Italian Stucco
      sciana_prawa: 22,     // Cerrad
      sufit: 1              // Cersanit Ikarus White
    }};

    function init() {{
      // Populate select options
      ZONES.forEach(z => {{
        const sel = document.getElementById('sel-' + z);
        sel.innerHTML = '';
        TILES.forEach(t => {{
          const opt = document.createElement('option');
          opt.value = t.index;
          opt.textContent = `${{t.index.toString().padStart(2, '0')}}. ${{t.manufacturer}} - ${{t.product}} (${{t.format}})`;
          if (t.index === currentSelections[z]) opt.selected = true;
          sel.appendChild(opt);
        }});
      }});
      updateAll();
    }}

    function setCamera(cam) {{
      currentCamera = cam;
      document.getElementById('cam-entrance').classList.toggle('active', cam === 'entrance');
      document.getElementById('cam-reverse').classList.toggle('active', cam === 'reverse');
      updateAll();
    }}

    function getTile(idx) {{
      return TILES.find(t => t.index === idx) || TILES[0];
    }}

    function updateSurface(zone) {{
      const sel = document.getElementById('sel-' + zone);
      currentSelections[zone] = parseInt(sel.value, 10);
      updateLayer(zone);
      updateCliCmd();
    }}

    function updateLayer(zone) {{
      const tile = getTile(currentSelections[zone]);
      const base = currentCamera === 'entrance' ? tile.base_entrance : tile.base_reverse;
      const imgPath = `${{currentCamera}}/${{zone}}/${{base}}_${{zone}}.png`;
      const imgEl = document.getElementById('layer-' + zone);
      imgEl.src = imgPath;
      
      const tagEl = document.getElementById('tag-' + zone);
      if (tagEl) tagEl.textContent = `${{tile.manufacturer}} #${{tile.index}}`;
    }}

    function updateAll() {{
      ZONES.forEach(z => updateLayer(z));
      updateCliCmd();
    }}

    function randomizeAll() {{
      ZONES.forEach(z => {{
        const randTile = TILES[Math.floor(Math.random() * TILES.length)];
        currentSelections[z] = randTile.index;
        document.getElementById('sel-' + z).value = randTile.index;
      }});
      updateAll();
    }}

    function matchAllWallsToMiddle() {{
      const midVal = currentSelections.sciana_srodkowa;
      ['sciana_lewa', 'sciana_prawa', 'sufit'].forEach(z => {{
        currentSelections[z] = midVal;
        document.getElementById('sel-' + z).value = midVal;
      }});
      updateAll();
    }}

    function updateCliCmd() {{
      const cmd = `python scripts/combine_puzzle.py --camera ${{currentCamera}} --podloga ${{currentSelections.podloga}} --sciana-lewa ${{currentSelections.sciana_lewa}} --sciana-srodkowa ${{currentSelections.sciana_srodkowa}} --sciana-prawa ${{currentSelections.sciana_prawa}} --sufit ${{currentSelections.sufit}}`;
      document.getElementById('cli-cmd').textContent = cmd;
    }}

    function copyCliCmd() {{
      const cmd = document.getElementById('cli-cmd').textContent;
      navigator.clipboard.writeText(cmd).then(() => {{
        alert('Skopiowano komendę do schowka:\\n\\n' + cmd);
      }}).catch(() => {{
        prompt('Skopiuj komendę:', cmd);
      }});
    }}

    async function downloadComposite() {{
      const canvas = document.getElementById('export-canvas');
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, 2000, 1600);

      // Order of drawing layers
      const drawOrder = ['sufit', 'sciana_srodkowa', 'sciana_lewa', 'sciana_prawa', 'podloga'];
      try {{
        for (const zone of drawOrder) {{
          const imgEl = document.getElementById('layer-' + zone);
          ctx.drawImage(imgEl, 0, 0, 2000, 1600);
        }}
        const link = document.createElement('a');
        link.download = `lazienka_${{currentCamera}}_miks.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
      }} catch (err) {{
        console.warn('CORS / file:// tainted canvas:', err);
        // Fallback: copy cli command
        alert('W Twojej przeglądarce bezpośredni zapis canvas jest blokowany.\\n\\nUżyj skopiowanej komendy w Termux / konsoli, aby natychmiast zapisać obraz w Galerii!\\n\\n' + document.getElementById('cli-cmd').textContent);
      }}
    }}

    init();
  </script>
</body>
</html>
"""

OUT_HTML.write_text(html_content, encoding='utf-8')
print(f"Generated puzzle viewer: {OUT_HTML}")

# Also create a copy in /sdcard/Download/kreator_lazienki.html that redirects or opens
shortcut = Path('/sdcard/Download/kreator_lazienki.html')
shortcut.write_text(f"""<!DOCTYPE html>
<html>
<head><meta http-equiv="refresh" content="0; url=Dom_Lazienka_R07_Puzzle/index.html"></head>
<body><a href="Dom_Lazienka_R07_Puzzle/index.html">Przejdź do Kreatora Puzzli Łazienki</a></body>
</html>
""", encoding='utf-8')
print(f"Generated shortcut: {shortcut}")
