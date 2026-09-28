"""Odtwarza lekki portal oraz samodzielny podgląd po zmianie geometrii."""
import base64
import json
from project_config import load_house_2d_model
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = load_house_2d_model()['source_data']

geo_file = ROOT / 'geoportal_teren.json'
M = None
if geo_file.exists():
    try:
        geo = json.loads(geo_file.read_text(encoding='utf-8'))
        M = geo.get('alignment', {}).get('house_calibration', {}).get('model_to_geo_local_affine_mm')
    except Exception:
        pass

rooms = []
for r in source['rooms']:
    pts = r['floor_reference_polygon_mm']
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    if M:
        gx = (M[0][0]*cx + M[0][1]*cy + M[0][2]) / 1000.0
        gy = (M[1][0]*cx + M[1][1]*cy + M[1][2]) / 1000.0
    else:
        gx = cx / 1000.0
        gy = cy / 1000.0
    rooms.append({'x': round(gx, 4), 'y': round(gy, 4), 'number': r['number'], 'name': r['name']})

def inline_json(value):
    """Compact data without allowing a source string to close the script tag."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('</', '<\\/')


s = (ROOT / 'podglad_szablon.html').read_text(encoding='utf-8')
scene = json.loads((ROOT / 'scena_modelu.json').read_text(encoding='utf-8'))
google_georef = json.loads((ROOT / 'google_model_georef.json').read_text(encoding='utf-8'))
s = s.replace('__SCENE__', inline_json(scene))
s = s.replace('__ROOM_LABELS__', inline_json(rooms))
s = s.replace('__GOOGLE_MODEL_GEOREF__', inline_json(google_georef))
position = google_georef['center']
camera = google_georef['camera']
maps_url = (f"https://www.google.com/maps/@{position['lat']},{position['lng']},"
            f"140a,35y,{camera['heading']}h,{camera['tilt']}t/data=!3m1!1e3")
earth_url = (f"https://earth.google.com/web/@{position['lat']},{position['lng']},"
             f"{camera['center']['altitude']}a,450d,35y,{camera['heading']}h,{camera['tilt']}t,0r")
s = s.replace('__GOOGLE_MAPS_URL__', maps_url).replace('__GOOGLE_EARTH_URL__', earth_url)
ortho = (ROOT / 'geoportal_ortho.jpg')
s = s.replace('__ORTHO_JPG__', base64.b64encode(ortho.read_bytes()).decode() if ortho.exists() else '')
portal = s
standalone = s
for marker, f in [('__GLB_INTERIOR__', 'dom_wnetrze.glb'), ('__GLB_EXTERIOR__', 'dom_bryla.glb')]:
    # The hosted portal downloads a GLB only after a click. Keep embedded GLBs
    # in the separate portable HTML so its existing offline downloads work.
    portal = portal.replace(marker, '')
    f_path = ROOT / f
    encoded = base64.b64encode(f_path.read_bytes()).decode() if f_path.exists() else ''
    standalone = standalone.replace(marker, encoded)

(ROOT / 'podglad_3d.html').write_text(standalone, encoding='utf-8')
(ROOT / 'index.html').write_text(portal, encoding='utf-8')
print('Zaktualizowano podglad_3d.html i index.html')
