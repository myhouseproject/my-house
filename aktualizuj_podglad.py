"""Build hosted and portable viewers from generated scenes and declarative data."""
import base64
import json
from pathlib import Path
import project_config

ROOT = Path(__file__).resolve().parent


def read_json(name, default=None, *, cached=False):
    path = project_config.cached_input_path(ROOT, name) if cached else ROOT / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def inline_json(value):
    """Keep source strings from closing an inline script."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('</', '<\\/')


def build_viewer():
    source = project_config.load_house_2d_model()['source_data']
    local_scene = read_json('scena_lokalna.json', {'parts': []})
    scene = read_json('scena_modelu.json', {'parts': []})
    georef = read_json('google_model_georef.json', {})
    geo = read_json('geoportal_teren.json', {}, cached=True)
    affine = geo.get('alignment', {}).get('house_calibration', {}).get('model_to_geo_local_affine_mm')
    house_path = ROOT / 'modules/04_house_3d/model.yaml'
    house = project_config.load_house_3d_model() if house_path.exists() else {}
    parameters = house.get('parameters', {})
    policies = project_config.load_room_policies() if hasattr(project_config, 'load_room_policies') and (ROOT / 'modules/06_interior/model.yaml').exists() else {}
    decisions = project_config.load_decision_register() if hasattr(project_config, 'load_decision_register') and (ROOT / 'config/decisions.yaml').exists() else {}
    interior_path = ROOT / 'modules/06_interior/model.yaml'
    interior = project_config.load_interior_model() if interior_path.exists() else {}
    rooms = []
    for room in source['rooms']:
        polygon = [[x / 1000, y / 1000] for x, y in room['floor_reference_polygon_mm']]
        cx = sum(p[0] for p in polygon) / len(polygon)
        cy = sum(p[1] for p in polygon) / len(polygon)
        gx, gy = cx, cy
        if affine:
            gx = affine[0][0] * cx + affine[0][1] * cy + affine[0][2] / 1000
            gy = affine[1][0] * cx + affine[1][1] * cy + affine[1][2] / 1000
        finish_reference = next((part.get('finish_reference') for part in local_scene.get('parts', []) if str(part.get('room_number')) == str(room['number']) and part.get('finish_reference')), None)
        rooms.append({**room, 'finish_reference': finish_reference, 'polygon_m': polygon, 'local_x': cx, 'local_y': cy,
                      'x': gx, 'y': gy, 'policy': policies.get(room['id'], {})})
    outline = source.get('facade_reference_outline', {}).get('polygon_mm', [])
    if not outline:
        outline = [p for room in source['rooms'] for p in room['floor_reference_polygon_mm']]
    bounds = {'minx': 0, 'miny': 0, 'maxx': 1, 'maxy': 1}
    if outline:
        bounds = {key: fn(p[axis] / 1000 for p in outline)
                  for key, fn, axis in [('minx', min, 0), ('maxx', max, 0), ('miny', min, 1), ('maxy', max, 1)]}
    metadata = {'bounds_m': bounds, 'parameters': parameters, 'provenance': house.get('provenance', {}),
                'decisions': decisions.get('decisions', []), 'room_presets': interior.get('viewer_presets', {}), 'local_scene_available': bool(local_scene.get('parts')),
                'map_scene_available': bool(scene.get('parts')), 'google_available': bool(georef)}
    s = (ROOT / 'podglad_szablon.html').read_text(encoding='utf-8')
    for marker, value in [('__SCENE__', scene), ('__SCENE_LOCAL__', local_scene), ('__ROOM_LABELS__', rooms),
                          ('__VIEWER_CONFIG__', metadata), ('__GOOGLE_MODEL_GEOREF__', georef)]:
        s = s.replace(marker, inline_json(value))
    maps_url = earth_url = 'https://www.google.com/maps'
    if georef:
        position, camera = georef['center'], georef['camera']
        maps_url = (f"https://www.google.com/maps/@{position['lat']},{position['lng']},"
                    f"140a,35y,{camera['heading']}h,{camera['tilt']}t/data=!3m1!1e3")
        earth_url = (f"https://earth.google.com/web/@{position['lat']},{position['lng']},"
                     f"{camera['center']['altitude']}a,450d,35y,{camera['heading']}h,{camera['tilt']}t,0r")
    s = s.replace('__GOOGLE_MAPS_URL__', maps_url).replace('__GOOGLE_EARTH_URL__', earth_url)
    ortho = project_config.cached_input_path(ROOT, 'geoportal_ortho.jpg')
    s = s.replace('__ORTHO_JPG__', base64.b64encode(ortho.read_bytes()).decode() if ortho.exists() else '')
    portal = standalone = s
    for marker, filename in [('__GLB_INTERIOR__', 'dom_wnetrze.glb'), ('__GLB_EXTERIOR__', 'dom_bryla.glb'),
                              ('__GLB_BLOCKS__', 'dom_wnetrze_bloki.glb'), ('__GLB_SHELL__', 'dom_powloka.glb')]:
        portal = portal.replace(marker, '')
        path = ROOT / filename
        encoded = base64.b64encode(path.read_bytes()).decode() if path.exists() else ''
        standalone = standalone.replace(marker, encoded)
    (ROOT / 'podglad_3d.html').write_text(standalone, encoding='utf-8')
    (ROOT / 'index.html').write_text(portal, encoding='utf-8')
    print('Zaktualizowano podglad_3d.html i index.html')


if __name__ == '__main__':
    build_viewer()
