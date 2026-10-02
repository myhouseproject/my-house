#!/usr/bin/env python3
"""
Aktualizuje geoportal_teren.json i scena_modelu.json:
1. Ustawia georeferencję domu na PZT survey grid (EPSG:2177 -> EPSG:2180).
2. Niweluje teren NMT i ortofotomapę pod domem i tarasem do poziomu podbudowy (-0.28 m).
3. Ujednolica budynki sąsiednie jako autentyczne bryły referencyjne:
   - Ściany: dokładny obrys ewidencyjny EGiB + wysokość okapu z pomiaru LiDAR NMPT (czysta bryła bez fikcyjnych okien/drzwi),
   - Dachy: geometria dachów z okapem 0.35 m, kalenicą i rzeczywistą fototeksturą lotniczą z Geoportalu.
4. Utrzymuje naturalną zieleń drzew w skali osiedlowej.
5. Zachowuje niezmienną geometrię wejściową, aby przebudowy były idempotentne.
"""
import hashlib
import json
import math
from pathlib import Path
from project_config import cached_input_path, load_map_config, load_house_2d_model, load_terrain_model
import numpy as np
import trimesh
from shapely.geometry import Polygon, Point
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent


def load_context_source(teren, terrain_model=None):
    """Read normalized source geometry from the declarative terrain model."""
    terrain_model = terrain_model or load_terrain_model()
    source = terrain_model['context_geometry']
    nmt = next(p for p in teren['parts'] if p['name'] == 'GEO_NMT_rzeczywisty')
    xy = [[p[0], p[1]] for p in nmt['positions_m']]
    fingerprint = hashlib.sha256(json.dumps(xy, separators=(',', ':')).encode()).hexdigest()
    if (fingerprint != source['terrain_xy_sha256']
            or len(nmt['positions_m']) != len(source['terrain_z_m'])
            or teren['alignment']['geo_context_center_epsg2180'] != source['geo_context_center_epsg2180']
            or teren['alignment']['geo_context_anchor_model_mm'] != source['geo_context_anchor_model_mm']):
        raise ValueError('Geometria źródłowa nie pasuje do siatki terenu. Odśwież modules/02_terrain/model.yaml po nowym pobraniu Geoportalu.')
    return source


def main():
    if not (ROOT / 'scena_modelu.json').is_file():
        raise RuntimeError('Brak roboczej sceny. Uruchom python scripts/build.py --scope full.')
    print("Ładowanie danych...")
    cfg = load_map_config()
    terrain_model = load_terrain_model()
    data = load_house_2d_model()['source_data']
    site = terrain_model['site']
    context_render = terrain_model['context_render']
    with open(cached_input_path(ROOT, 'geoportal_teren.json'), encoding='utf-8') as f:
        teren = json.load(f)

    # Stałe wejście: nie używamy ani historii Git, ani już wygenerowanych brył.
    source = load_context_source(teren, terrain_model)
    source_parts = {p['name']: p for p in source['building_parts']}

    # 1. Dokładna macierz PZT (EPSG:2177 -> EPSG:2180)
    M2177 = np.array(cfg['model_to_epsg2177_affine'])
    TO_2180 = Transformer.from_crs(2177, 2180, always_xy=True)
    center_en = teren['alignment']['geo_context_center_epsg2180']
    GEO_CENTER_2180 = np.array(center_en, dtype=float)
    GEO_ANCHOR_MODEL_MM = np.array(cfg['fetch']['center_model_mm'], dtype=float)

    def epsg2180_to_geo_local(e, n):
        delta = np.array([e, n]) - GEO_CENTER_2180
        return GEO_ANCHOR_MODEL_MM + delta * 1000.0

    def model_to_epsg2180(x_mm, y_mm):
        v = M2177 @ np.array([x_mm, y_mm, 1.0])
        return TO_2180.transform(v[0], v[1])

    cx, cy = map(float, cfg['fetch']['center_model_mm'])
    pc = epsg2180_to_geo_local(*model_to_epsg2180(cx, cy))
    px = epsg2180_to_geo_local(*model_to_epsg2180(cx + 1000.0, cy))
    py = epsg2180_to_geo_local(*model_to_epsg2180(cx, cy + 1000.0))
    A = np.column_stack(((px - pc) / 1000.0, (py - pc) / 1000.0))
    t = pc - A @ np.array([cx, cy])
    M_pzt = np.array([
        [A[0,0], A[0,1], t[0]],
        [A[1,0], A[1,1], t[1]],
        [0.0, 0.0, 1.0]
    ])

    # 2. Obrys domu i tarasu
    def transform_pts(pts_mm):
        res = []
        for x, y in pts_mm:
            p = M_pzt @ np.array([x, y, 1.0])
            res.append((p[0] / 1000.0, p[1] / 1000.0))
        return res

    house_poly = Polygon(transform_pts(data['facade_reference_outline']['polygon_mm']))
    terrace_poly = Polygon(transform_pts(site['areas']['terrace'][0]['exterior_mm']))
    combined_building = house_poly.union(terrace_poly)

    # 3. Niwelacja NMT i Ortofoto
    nmt_part = next((p for p in teren['parts'] if p.get('name') == 'GEO_NMT_rzeczywisty'), None)
    ortho_part = next((p for p in teren['parts'] if p.get('name') == 'GEO_ORTHO_TEXTURED'), None)

    if nmt_part and ortho_part:
        pos = np.array(nmt_part['positions_m'], dtype=float)
        # Blend musi za każdym razem zaczynać od oryginalnych wysokości NMT.
        pos[:, 2] = source['terrain_z_m']
        graded_count = 0
        grading = context_render['grading']
        target_z = float(grading['target_z_m'])
        blend_dist = float(grading['blend_distance_m'])
        inside_tolerance = float(grading['inside_tolerance_m'])
        for idx in range(len(pos)):
            pt = Point(pos[idx, 0], pos[idx, 1])
            d = combined_building.distance(pt)
            if combined_building.contains(pt) or d < inside_tolerance:
                if pos[idx, 2] > target_z:
                    pos[idx, 2] = target_z
                    graded_count += 1
            elif d < blend_dist:
                curr = pos[idx, 2]
                if curr > target_z:
                    w = 0.5 * (1.0 + math.cos(math.pi * d / blend_dist))
                    pos[idx, 2] = curr * (1.0 - w) + target_z * w
                    graded_count += 1
        nmt_part['positions_m'] = np.round(pos, 6).tolist()
        ortho_part['positions_m'] = np.round(pos, 6).tolist()
        print(f"Zniwelowano {graded_count} wierzchołków NMT i ortofoto pod domem i tarasem.")

    # 4. Rzetelne budynki sąsiednie (czyste bryły geodezyjne bez zmyślonych okien/drzwi)
    building_style = context_render['buildings']
    facade_palette = building_style['facade_palette']
    roof_colors = building_style['roof_palette']

    new_building_parts = []
    print("Tworzenie rzetelnych brył budynków otoczenia (obrys EGiB + wysokość LiDAR + ortofoto)...")

    for bi in range(1, int(building_style['max_index']) + 1):
        sw_name = f'GEO_BUDYNEK_SCIANY_{bi:03d}'
        sr_name = f'GEO_BUDYNEK_DACH_{bi:03d}'
        
        sw = source_parts.get(sw_name)
        sr = source_parts.get(sr_name)
        if not sw or not sr:
            continue
            
        wv = np.array(sw['positions_m'], dtype=float)
        footprint = wv[:len(wv)//2, :2]
        base_z = float(wv[:,2].min())
        eave_z = float(wv[:,2].max())
        poly = Polygon(footprint)
        if not poly.is_valid or poly.area < 2.0:
            continue

        # Ściany jako precyzyjny obrys EGiB wyciągnięty do wysokości okapu
        wall_h = max(float(building_style['min_wall_height_m']), eave_z - base_z)
        try:
            m_walls = trimesh.creation.extrude_polygon(poly, height=wall_h, engine="earcut")
            m_walls.apply_translation([0, 0, base_z])
            new_building_parts.append({
                "name": sw_name,
                "category": "budynki_otoczenia",
                "material": "budynki_elewacja",
                "color": facade_palette[(bi - 1) % len(facade_palette)],
                "source": "Geoportal / EGiB + NMPT",
                "source_id": "GEO_BUILDINGS",
                "assumed": False,
                "note": f"Ściany budynku sąsiedniego B{bi:02d}: urzędowy obrys EGiB; rzędna okapu z pomiaru LiDAR NMPT.",
                "positions_m": np.round(m_walls.vertices, 6).tolist(),
                "faces": m_walls.faces.tolist(),
                "reference_area_m2": sw.get('reference_area_m2', 0.0)
            })
        except Exception as exc:
            raise RuntimeError(f'Nie można zbudować ścian {sw_name}') from exc

        # Dach z okapem 0.35 m i rzeczywistą ortofotomapą lotniczą z Geoportalu
        orig_roof = np.array(sr['positions_m'], dtype=float)
        if len(orig_roof) >= 6:
            new_verts = orig_roof[:6].copy()
            eave_c = np.mean(new_verts[:4, :2], axis=0)
            for i in range(4):
                dxy = new_verts[i, :2] - eave_c
                dist = np.linalg.norm(dxy)
                if dist > 1e-4:
                    new_verts[i, :2] += (dxy / dist) * float(building_style['roof_overhang_m'])
            r_dir = new_verts[5, :2] - new_verts[4, :2]
            r_len = np.linalg.norm(r_dir)
            if r_len > 1e-4:
                r_unit = r_dir / r_len
                overhang = float(building_style['roof_overhang_m'])
                new_verts[4, :2] -= r_unit * overhang
                new_verts[5, :2] += r_unit * overhang
            ridge_raise = float(building_style['ridge_raise_m'])
            g0 = [new_verts[4, 0], new_verts[4, 1], new_verts[4, 2] + ridge_raise]
            g1 = [new_verts[5, 0], new_verts[5, 1], new_verts[5, 2] + ridge_raise]
            all_v = np.vstack([new_verts, [g0, g1]])
            faces = [
                [0, 1, 5], [0, 5, 4],
                [3, 4, 5], [3, 5, 2],
                [0, 4, 3], [1, 2, 5],
                [4, 5, 7], [4, 7, 6]
            ]
            new_building_parts.append({
                "name": sr_name,
                "category": "budynki_otoczenia",
                "material": "budynki_dachy",
                "color": roof_colors[(bi - 1) % len(roof_colors)],
                "use_ortho_texture": True,
                "source": "Geoportal / EGiB + NMPT",
                "source_id": "GEO_BUILDINGS",
                "assumed": sr.get('assumed', True),
                "note": f"Dach budynku sąsiedniego B{bi:02d}: uproszczona bryła na podstawie EGiB i orientacyjnej wysokości, tekstura ortofotomapy lotniczej.",
                "positions_m": np.round(all_v, 6).tolist(),
                "faces": faces,
                "reference_area_m2": sr.get('reference_area_m2', 0.0)
            })

    print(f"Utworzono {len(new_building_parts)} rzetelnych elementów budynków otoczenia.")

    # 5. Aktualizacja drzew otoczenia
    new_tree_parts = []
    tree_heights = []

    tree_anchors = source['tree_anchors_m']
    if tree_anchors:
        print(f"Tworzenie roślinności dla {len(tree_anchors)} drzew otoczenia...")

        trunks, crowns = [], []
        tree_style = context_render['trees']
        deciduous = tree_style['deciduous']
        conifer = tree_style['conifer']
        for ti, (x, y, ground_z) in enumerate(tree_anchors):
            rng = np.random.RandomState(ti * int(tree_style['seed_multiplier']))
            total_h = float(rng.uniform(*tree_style['total_height_range_m']))
            crown_radius = float(rng.uniform(*tree_style['crown_radius_range_m']))
            is_conifer = (ti % int(tree_style['conifer_modulus'])) in tuple(tree_style['conifer_remainders'])
            crown_start = len(crowns)

            if not is_conifer:
                trunk_h = float(rng.uniform(*deciduous['trunk_height_range_m']))
                trunk = trimesh.creation.cylinder(radius=float(deciduous['trunk_radius_m']), height=trunk_h, sections=int(deciduous['trunk_sections']))
                trunk.apply_translation([x, y, ground_z + trunk_h / 2.0])
                trunks.append(trunk)

                cz = ground_z + trunk_h + crown_radius * float(deciduous['crown_z_factor'])
                # Jedna korona zamiast czterech nakładających się kul: ta sama
                # skala zieleni, 80 trójkątów zamiast 320 dla drzewa liściastego.
                c_main = trimesh.creation.icosphere(subdivisions=int(deciduous['icosphere_subdivisions']), radius=crown_radius)
                c_main.apply_scale([1.0, 1.0, float(deciduous['crown_z_scale'])])
                c_main.apply_translation([x, y, cz])
                crowns.append(c_main)

            else:
                trunk_h = total_h * float(conifer['trunk_height_factor'])
                trunk = trimesh.creation.cylinder(radius=float(conifer['trunk_radius_m']), height=trunk_h, sections=int(conifer['trunk_sections']))
                trunk.apply_translation([x, y, ground_z + trunk_h / 2.0])
                trunks.append(trunk)

                tiers = int(conifer['tiers'])
                for t_idx in range(tiers):
                    frac = (t_idx + 1) / (tiers + 1)
                    tz = ground_z + total_h * (float(conifer['tier_z_start']) + float(conifer['tier_z_span']) * frac)
                    tier_r = crown_radius * (1.0 - float(conifer['tier_radius_decrease']) * t_idx)
                    tier_h = total_h * (float(conifer['tier_height_start']) - float(conifer['tier_height_decrease']) * t_idx)
                    cone = trimesh.creation.cone(radius=tier_r, height=tier_h, sections=int(conifer['cone_sections']))
                    cone.apply_translation([x, y, tz])
                    crowns.append(cone)
            tree_heights.append(max(float(c.vertices[:, 2].max()) for c in crowns[crown_start:]) - ground_z)

        tm = trimesh.util.concatenate(trunks)
        cm = trimesh.util.concatenate(crowns)

        new_tree_parts.append({
            "name": "GEO_DRZEWA_PNIE",
            "category": "drzewa",
            "material": "drzewa_pnie",
            "color": tree_style['trunk_color'],
            "source": "Geoportal ortofoto",
            "source_id": "GEO_TREES",
            "assumed": True,
            "note": "Pozycje z ortofotomapy; niskopoligonowe drzewa o orientacyjnej wysokości.",
            "positions_m": np.round(tm.vertices, 6).tolist(),
            "faces": tm.faces.tolist()
        })
        new_tree_parts.append({
            "name": "GEO_DRZEWA_KORONY",
            "category": "drzewa",
            "material": "drzewa_korony",
            "color": tree_style['crown_color'],
            "source": "Geoportal ortofoto",
            "source_id": "GEO_TREES",
            "assumed": True,
            "note": "Pozycje z ortofotomapy; niskopoligonowe drzewa o orientacyjnej wysokości.",
            "positions_m": np.round(cm.vertices, 6).tolist(),
            "faces": cm.faces.tolist()
        })

    # 6. Zapis geoportal_teren.json
    base_geo_parts = [p for p in teren['parts'] if not p.get('name', '').startswith('GEO_BUDYNEK_') and not p.get('name', '').startswith('GEO_DRZEWA_')]
    teren['parts'] = base_geo_parts + new_building_parts + new_tree_parts
    teren['stats'].update({
        'trees': len(tree_anchors),
        'tree_median_height_m': round(float(np.median(tree_heights)), 2) if tree_heights else None,
        'tree_max_height_m': round(max(tree_heights), 2) if tree_heights else None,
        'context_buildings': sum(p['name'].startswith('GEO_BUDYNEK_SCIANY_') for p in new_building_parts),
    })

    cal = teren['alignment']['house_calibration']
    cal['model_to_geo_local_affine_mm'] = M_pzt.tolist()
    cal['status'] = 'pzt_survey_grid_georeferenced'
    cal['method'] = 'official PZT survey grid georeference (EPSG:2177 -> EPSG:2180)'
    cal['manual_offset_m'] = [0.0, 0.0]
    cal['manual_rotation_deg'] = 0.0
    house_center_geo = np.array(house_poly.centroid.coords[0])
    centroid_en = GEO_CENTER_2180 + house_center_geo - GEO_ANCHOR_MODEL_MM / 1000.0
    validation = teren.setdefault('validation', {})
    # Historical diagnostics called the parcel/fetch center the model center.
    # Keep its measured value, but identify the point so it is not mistaken for
    # the ground beneath the house (about 32 m away).
    for old_key, new_key in (
        ('nmt_at_model_center_m', 'nmt_at_fetch_center_m'),
        ('nmt_center_relative_to_model_zero_m', 'nmt_fetch_center_relative_to_model_zero_m'),
    ):
        if old_key in validation:
            validation[new_key] = validation.pop(old_key)
    validation['nmt_sample_epsg2180'] = list(center_en)
    validation['house_alignment_source'] = 'PZT_survey_grid_project'
    validation['project_house_centroid_epsg2180'] = np.round(centroid_en, 3).tolist()
    validation['calibrated_house_centroid_epsg2180'] = np.round(centroid_en, 3).tolist()
    # Wyniki dawnego dopasowania do ortofoto pozostają diagnostyką, nie aktywną kalibracją.
    for old_fit in (cal.get('orthophoto_fit'), validation.get('house_ortho_fit')):
        if old_fit is not None:
            old_fit['applied'] = False

    with open(ROOT / 'geoportal_teren.json', 'w', encoding='utf-8') as f:
        json.dump(teren, f, ensure_ascii=False, indent=2)
    print("Zapisano geoportal_teren.json!")

    # 7. Zapis scena_modelu.json
    with open(ROOT / 'scena_modelu.json', encoding='utf-8') as f:
        scena = json.load(f)
    house_and_garden = [p for p in scena['parts'] if not p.get('name', '').startswith('GEO_')]
    scena['parts'] = house_and_garden + teren['parts']
    scena['geo_alignment'] = teren['alignment']
    scena['geo_validation'] = teren['validation']
    with open(ROOT / 'scena_modelu.json', 'w', encoding='utf-8') as f:
        json.dump(scena, f, ensure_ascii=False, indent=2)
    print(f"Zapisano scena_modelu.json ({len(scena['parts'])} obiektów).")

if __name__ == '__main__':
    main()
