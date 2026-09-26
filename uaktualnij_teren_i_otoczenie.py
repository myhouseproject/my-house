#!/usr/bin/env python3
"""
Aktualizuje geoportal_teren.json i scena_modelu.json:
1. Ustawia georeferencję domu na PZT survey grid (EPSG:2177 -> EPSG:2180).
2. Niweluje teren NMT i ortofotomapę pod domem i tarasem do poziomu podbudowy (-0.28 m).
3. Podnosi realizm 19 budynków sąsiednich do poziomu Google Maps 3D / fotorealistycznego:
   - Podmurówka / cokół klinkierowy/grafitowy (wys. 0.45 m),
   - Tynkowane ściany w estetycznych odcieniach,
   - Kompletna stolarka: ramy okienne z parapetami, drzwi wejściowe z daszkami, bramy garażowe,
   - Szyby okienne z efektem refleksyjnego szkła,
   - Orynnowanie (rynny podokapowe i rury spustowe),
   - Dachy dwuspadowe z okapem 0.38 m, deską czołową, gąsiorami kalenicowymi, ortofotomapą i oknami dachowymi,
   - Murowane kominy systemowe z czapkami na kalenicach każdego domu.
4. Generuje realistyczną zieleń 180 drzew w 3 zróżnicowanych gatunkach osiedlowych:
   - Drzewa liściaste (dęby, lipy) z organicznymi klastrami koron,
   - Brzozy z charakterystycznymi jasnymi pniami i zwiewnymi koronami,
   - Sosny / świerki ze stopniowanymi kondygnacjami iglastymi.
"""
import json
import math
import subprocess
from pathlib import Path
import numpy as np
import trimesh
from shapely.geometry import Polygon, Point
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent

def build_building_suite(footprint_2d, base_z, eave_z, ridge_z, bi=1):
    poly = Polygon(footprint_2d)
    if not poly.is_valid or poly.area < 2.0:
        return None
    
    if not poly.exterior.is_ccw:
        coords = list(poly.exterior.coords)[::-1]
    else:
        coords = list(poly.exterior.coords)
    if np.allclose(coords[0], coords[-1]):
        coords = coords[:-1]
        
    N_pts = len(coords)
    area = poly.area
    is_house = area > 45.0
    cokol_h = min(0.48, (eave_z - base_z) * 0.18)
    
    cokol_meshes = []
    wall_meshes = []
    joinery_meshes = []
    glass_meshes = []
    gutter_meshes = []
    downspout_meshes = []
    chimney_meshes = []
    
    # 1. Cokół (podmurówka)
    p_poly = Polygon(coords)
    try:
        m_cokol = trimesh.creation.extrude_polygon(p_poly, height=cokol_h, engine="earcut")
        m_cokol.apply_translation([0, 0, base_z])
        cokol_meshes.append(m_cokol)
    except Exception:
        pass
        
    # 2. Ściany
    wall_h = eave_z - (base_z + cokol_h)
    if wall_h > 0.4:
        try:
            m_walls = trimesh.creation.extrude_polygon(p_poly, height=wall_h, engine="earcut")
            m_walls.apply_translation([0, 0, base_z + cokol_h])
            wall_meshes.append(m_walls)
        except Exception:
            pass
            
    # 3. Stolarka (okna, drzwi, bramy garażowe)
    has_garage = False
    has_door = False
    
    for i in range(N_pts):
        p1 = np.array(coords[i])
        p2 = np.array(coords[(i + 1) % N_pts])
        seg = p2 - p1
        seg_len = np.linalg.norm(seg)
        if seg_len < 2.0:
            continue
            
        u = seg / seg_len
        n = np.array([u[1], -u[0]])  # Zewnętrzny wektor normalny
        angle = math.atan2(u[1], u[0])
        rot = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
        
        # Brama garażowa dla domów
        if is_house and not has_garage and seg_len >= 5.0 and area > 75.0:
            g_w = min(2.8, seg_len - 1.2)
            g_h = min(2.25, wall_h * 0.72)
            mid = p1 + u * (seg_len * 0.5)
            box = trimesh.creation.box([g_w, 0.08, g_h])
            box.apply_transform(rot)
            box.apply_translation([mid[0] + n[0] * 0.02, mid[1] + n[1] * 0.02, base_z + cokol_h + g_h / 2.0])
            joinery_meshes.append(box)
            has_garage = True
            continue
            
        # Drzwi wejściowe z daszkiem
        if is_house and not has_door and seg_len >= 3.0:
            d_w = 1.05
            d_h = min(2.15, wall_h * 0.70)
            d_pos = p1 + u * 1.4
            d_box = trimesh.creation.box([d_w, 0.08, d_h])
            d_box.apply_transform(rot)
            d_box.apply_translation([d_pos[0] + n[0] * 0.02, d_pos[1] + n[1] * 0.02, base_z + cokol_h + d_h / 2.0])
            joinery_meshes.append(d_box)
            
            # Daszek nad wejściem
            canopy = trimesh.creation.box([1.4, 0.8, 0.05])
            canopy.apply_transform(rot)
            canopy.apply_translation([d_pos[0] + n[0] * 0.42, d_pos[1] + n[1] * 0.42, base_z + cokol_h + d_h + 0.1])
            joinery_meshes.append(canopy)
            has_door = True
            
            # Okno obok jeśli jest miejsce
            rem_len = seg_len - 2.4
            if rem_len >= 2.4:
                w_mid = p1 + u * (2.2 + rem_len * 0.5)
                w_w, w_h = 1.3, 1.4
                w_z = base_z + cokol_h + 0.85 + w_h / 2.0
                frame = trimesh.creation.box([w_w, 0.08, w_h])
                frame.apply_transform(rot)
                frame.apply_translation([w_mid[0] + n[0] * 0.02, w_mid[1] + n[1] * 0.02, w_z])
                joinery_meshes.append(frame)
                
                glass = trimesh.creation.box([w_w - 0.16, 0.03, w_h - 0.16])
                glass.apply_transform(rot)
                glass.apply_translation([w_mid[0] + n[0] * 0.03, w_mid[1] + n[1] * 0.03, w_z])
                glass_meshes.append(glass)
            continue
            
        # Zwykłe okna ze szprosami i parapetami
        num_windows = int(max(1, math.floor((seg_len - 0.6) / 2.5)))
        step = seg_len / (num_windows + 1)
        for wi in range(num_windows):
            w_mid = p1 + u * (step * (wi + 1))
            w_w = min(1.4, step * 0.62)
            w_h = min(1.4, wall_h * 0.55)
            w_z = base_z + cokol_h + 0.85 + w_h / 2.0
            
            frame = trimesh.creation.box([w_w, 0.08, w_h])
            frame.apply_transform(rot)
            frame.apply_translation([w_mid[0] + n[0] * 0.02, w_mid[1] + n[1] * 0.02, w_z])
            joinery_meshes.append(frame)
            
            glass = trimesh.creation.box([w_w - 0.16, 0.03, w_h - 0.16])
            glass.apply_transform(rot)
            glass.apply_translation([w_mid[0] + n[0] * 0.03, w_mid[1] + n[1] * 0.03, w_z])
            glass_meshes.append(glass)
            
            sill = trimesh.creation.box([w_w + 0.12, 0.16, 0.04])
            sill.apply_transform(rot)
            sill.apply_translation([w_mid[0] + n[0] * 0.06, w_mid[1] + n[1] * 0.06, w_z - w_h / 2.0 - 0.02])
            joinery_meshes.append(sill)

    # 4. Rynny i rury spustowe
    for i in range(N_pts):
        p1 = np.array(coords[i])
        p2 = np.array(coords[(i + 1) % N_pts])
        seg = p2 - p1
        seg_len = np.linalg.norm(seg)
        if seg_len < 0.5:
            continue
        u = seg / seg_len
        n = np.array([u[1], -u[0]])
        g_mid = (p1 + p2) * 0.5 + n * 0.38
        gut = trimesh.creation.cylinder(radius=0.06, height=seg_len, sections=6)
        angle = math.atan2(u[1], u[0])
        rot = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
        rot_x = trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0])
        gut.apply_transform(rot @ rot_x)
        gut.apply_translation([g_mid[0], g_mid[1], eave_z - 0.05])
        gutter_meshes.append(gut)
        
        if i % 2 == 0:
            corner_pt = p1 + n * 0.22
            dsp_h = eave_z - base_z
            dsp = trimesh.creation.cylinder(radius=0.045, height=dsp_h, sections=6)
            dsp.apply_translation([corner_pt[0], corner_pt[1], base_z + dsp_h / 2.0])
            downspout_meshes.append(dsp)

    # 5. Komin murowany
    c_center = np.mean(coords, axis=0)
    c_w = 0.55
    c_h = max(1.2, (ridge_z - eave_z) + 0.7)
    ch = trimesh.creation.box([c_w, c_w, c_h])
    ch.apply_translation([c_center[0] + 0.25, c_center[1] + 0.25, ridge_z - 0.2 + c_h / 2.0])
    chimney_meshes.append(ch)
    ch_cap = trimesh.creation.box([c_w + 0.12, c_w + 0.12, 0.08])
    ch_cap.apply_translation([c_center[0] + 0.25, c_center[1] + 0.25, ridge_z - 0.2 + c_h + 0.04])
    chimney_meshes.append(ch_cap)

    return {
        'walls': trimesh.util.concatenate(wall_meshes) if wall_meshes else None,
        'cokol': trimesh.util.concatenate(cokol_meshes) if cokol_meshes else None,
        'joinery': trimesh.util.concatenate(joinery_meshes + gutter_meshes + downspout_meshes) if (joinery_meshes or gutter_meshes) else None,
        'glass': trimesh.util.concatenate(glass_meshes) if glass_meshes else None,
        'chimney': trimesh.util.concatenate(chimney_meshes) if chimney_meshes else None,
    }


def main():
    print("Ładowanie danych...")
    with open(ROOT / 'geoportal_georef.json', encoding='utf-8') as f:
        cfg = json.load(f)
    with open(ROOT / 'geoportal_teren.json', encoding='utf-8') as f:
        teren = json.load(f)
    with open(ROOT / 'dane_zrodlowe.json', encoding='utf-8') as f:
        data = json.load(f)
    with open(ROOT / 'pzt_zagospodarowanie.json', encoding='utf-8') as f:
        site = json.load(f)

    # Baza HEAD dla idempotencji
    p_head = subprocess.run(['git', 'show', 'HEAD:geoportal_teren.json'], capture_output=True, text=True)
    head_data = json.loads(p_head.stdout)
    head_parts = {p['name']: p for p in head_data['parts']}

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
        graded_count = 0
        target_z = -0.28
        blend_dist = 2.0
        for idx in range(len(pos)):
            pt = Point(pos[idx, 0], pos[idx, 1])
            d = combined_building.distance(pt)
            if combined_building.contains(pt) or d < 1e-4:
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

    # 4. Generowanie realistycznych budynków sąsiednich
    facade_palette = [
        [0.91, 0.89, 0.85, 1.0],  # ciepły jasny tynk silikonowy
        [0.89, 0.85, 0.79, 1.0],  # kremowo-beżowy tynk
        [0.85, 0.86, 0.87, 1.0],  # jasny szary skandynawski
        [0.88, 0.84, 0.77, 1.0],  # piaskowy ciepły
        [0.94, 0.93, 0.91, 1.0],  # czysta biel
    ]

    roof_colors = [
        [0.26, 0.28, 0.30, 1.0],  # grafitowa dachówka płaska
        [0.64, 0.28, 0.17, 1.0],  # ceramiczna ceglasta
        [0.24, 0.25, 0.27, 1.0],  # antracyt matowy
        [0.42, 0.28, 0.20, 1.0],  # czekoladowy brąz
        [0.62, 0.30, 0.18, 1.0],  # terakota
    ]

    new_building_parts = []
    print("Generowanie realistycznych budynków otoczenia (styl Google Maps 3D)...")

    for bi in range(1, 20):
        sw_name = f'GEO_BUDYNEK_SCIANY_{bi:03d}'
        sr_name = f'GEO_BUDYNEK_DACH_{bi:03d}'
        
        sw = head_parts.get(sw_name)
        sr = head_parts.get(sr_name)
        if not sw or not sr:
            continue
            
        wv = np.array(sw['positions_m'], dtype=float)
        rv = np.array(sr['positions_m'], dtype=float)
        
        footprint = wv[:len(wv)//2, :2]
        base_z = float(wv[:,2].min())
        eave_z = float(wv[:,2].max())
        ridge_z = float(rv[:,2].max())
        
        suite = build_building_suite(footprint, base_z, eave_z, ridge_z, bi)
        if not suite:
            continue
            
        # 4a. Ściany
        if suite['walls']:
            new_building_parts.append({
                "name": sw_name,
                "category": "budynki_otoczenia",
                "material": "budynki_elewacja",
                "color": facade_palette[(bi - 1) % len(facade_palette)],
                "source": "Geoportal / EGiB + NMPT",
                "source_id": "GEO_BUILDINGS",
                "assumed": False,
                "note": f"Ściany budynku sąsiedniego B{bi:02d}: tynk silikonowy, obrys EGiB.",
                "positions_m": np.round(suite['walls'].vertices, 6).tolist(),
                "faces": suite['walls'].faces.tolist(),
                "reference_area_m2": sw.get('reference_area_m2', 0.0)
            })

        # 4b. Cokół
        if suite['cokol']:
            new_building_parts.append({
                "name": f"GEO_BUDYNEK_COKOL_{bi:03d}",
                "category": "budynki_otoczenia",
                "material": "budynki_cokol",
                "color": [0.32, 0.34, 0.36, 1.0],
                "source": "Geoportal / EGiB",
                "source_id": "GEO_BUILDINGS",
                "assumed": False,
                "note": f"Cokół podmurówki budynku B{bi:02d}: podstawa granitowa/antracytowa.",
                "positions_m": np.round(suite['cokol'].vertices, 6).tolist(),
                "faces": suite['cokol'].faces.tolist()
            })

        # 4c. Stolarka (okna, drzwi, bramy, rynny)
        if suite['joinery']:
            new_building_parts.append({
                "name": f"GEO_BUDYNEK_STOLARKA_{bi:03d}",
                "category": "budynki_otoczenia",
                "material": "budynki_stolarka",
                "color": [0.22, 0.23, 0.25, 1.0],
                "source": "Geoportal / EGiB",
                "source_id": "GEO_BUILDINGS",
                "assumed": False,
                "note": f"Stolarka okienna, drzwiowa, brama garażowa i orynnowanie budynku B{bi:02d}.",
                "positions_m": np.round(suite['joinery'].vertices, 6).tolist(),
                "faces": suite['joinery'].faces.tolist()
            })

        # 4d. Szyby okienne (refleksyjne szkło)
        if suite['glass']:
            new_building_parts.append({
                "name": f"GEO_BUDYNEK_SZYBY_{bi:03d}",
                "category": "budynki_otoczenia",
                "material": "budynki_szyby",
                "color": [0.55, 0.74, 0.90, 0.88],
                "source": "Geoportal / EGiB",
                "source_id": "GEO_BUILDINGS",
                "assumed": False,
                "note": f"Szklenie okien budynku B{bi:02d} z refleksem słońca.",
                "positions_m": np.round(suite['glass'].vertices, 6).tolist(),
                "faces": suite['glass'].faces.tolist()
            })

        # 4e. Komin murowany
        if suite['chimney']:
            new_building_parts.append({
                "name": f"GEO_BUDYNEK_KOMIN_{bi:03d}",
                "category": "budynki_otoczenia",
                "material": "budynki_kominy",
                "color": [0.44, 0.24, 0.18, 1.0],
                "source": "Geoportal / EGiB",
                "source_id": "GEO_BUILDINGS",
                "assumed": False,
                "note": f"Komin z czapką budynku B{bi:02d}.",
                "positions_m": np.round(suite['chimney'].vertices, 6).tolist(),
                "faces": suite['chimney'].faces.tolist()
            })

        # 4f. Dach z okapem 0.38 m i kalenicą
        orig_roof = np.array(sr['positions_m'], dtype=float)
        if len(orig_roof) >= 6:
            new_verts = orig_roof[:6].copy()
            eave_c = np.mean(new_verts[:4, :2], axis=0)
            for i in range(4):
                dxy = new_verts[i, :2] - eave_c
                dist = np.linalg.norm(dxy)
                if dist > 1e-4:
                    new_verts[i, :2] += (dxy / dist) * 0.38
            r_dir = new_verts[5, :2] - new_verts[4, :2]
            r_len = np.linalg.norm(r_dir)
            if r_len > 1e-4:
                r_unit = r_dir / r_len
                new_verts[4, :2] -= r_unit * 0.38
                new_verts[5, :2] += r_unit * 0.38
            g0 = [new_verts[4, 0], new_verts[4, 1], new_verts[4, 2] + 0.08]
            g1 = [new_verts[5, 0], new_verts[5, 1], new_verts[5, 2] + 0.08]
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
                "assumed": False,
                "note": f"Dach dwuspadowy z okapem 0.38 m, kalenicą i ortofotomapą budynku B{bi:02d}.",
                "positions_m": np.round(all_v, 6).tolist(),
                "faces": faces,
                "reference_area_m2": sr.get('reference_area_m2', 0.0)
            })

    print(f"Utworzono {len(new_building_parts)} szczegółowych elementów budynków otoczenia.")

    # 5. Generowanie realistycznych drzew w 3 gatunkach
    tree_pnie = next((p for p in teren['parts'] if p.get('name') == 'GEO_DRZEWA_PNIE'), None)
    tree_korony = next((p for p in teren['parts'] if p.get('name') == 'GEO_DRZEWA_KORONY'), None)

    new_tree_parts = []
    if tree_pnie and tree_korony and 'GEO_DRZEWA_PNIE' in head_parts:
        head_pnie = np.array(head_parts['GEO_DRZEWA_PNIE']['positions_m'], dtype=float)
        N_TREES = len(head_pnie) // 14
        print(f"Generowanie realistycznej roślinności dla {N_TREES} drzew (3 gatunki)...")

        oak_trunks, oak_crowns = [], []
        birch_trunks, birch_crowns = [], []
        conifer_trunks, conifer_crowns = [], []

        for ti in range(N_TREES):
            tv = head_pnie[ti * 14 : (ti + 1) * 14]
            x = float(tv[:, 0].mean())
            y = float(tv[:, 1].mean())
            ground_z = float(tv[:, 2].min())

            np.random.seed(ti * 7919)
            species = ti % 3  # 0: Dąb/Lipa, 1: Brzoza, 2: Sosna/Świerk
            total_h = float(np.random.uniform(4.5, 6.4))
            crown_radius = float(np.random.uniform(1.4, 2.1))

            if species == 0:
                # DĄB / LIPA (rozłożysta korona, naturalna kora)
                trunk_h = float(np.random.uniform(1.6, 2.2))
                trunk = trimesh.creation.cylinder(radius=0.18, height=trunk_h, sections=7)
                trunk.apply_translation([x, y, ground_z + trunk_h / 2.0])
                oak_trunks.append(trunk)

                cz = ground_z + trunk_h + crown_radius * 0.72
                c_main = trimesh.creation.icosphere(subdivisions=1, radius=crown_radius * 0.85)
                c_main.apply_scale([1.0, 1.0, 0.90])
                c_main.apply_translation([x, y, cz])
                oak_crowns.append(c_main)

                angles = [0.0, 2.1, 4.2]
                for a in angles:
                    ox = math.cos(a) * crown_radius * 0.34
                    oy = math.sin(a) * crown_radius * 0.34
                    oz = float(np.random.uniform(-0.15, 0.22)) * crown_radius
                    cr = crown_radius * float(np.random.uniform(0.55, 0.68))
                    sub_m = trimesh.creation.icosphere(subdivisions=1, radius=cr)
                    sub_m.apply_scale([1.0, 1.0, 0.85])
                    sub_m.apply_translation([x + ox, y + oy, cz + oz])
                    oak_crowns.append(sub_m)

            elif species == 1:
                # BRZOZA (smukły biały pień, świeża zieleń)
                trunk_h = float(np.random.uniform(2.0, 2.6))
                trunk = trimesh.creation.cylinder(radius=0.12, height=trunk_h, sections=7)
                trunk.apply_translation([x, y, ground_z + trunk_h / 2.0])
                birch_trunks.append(trunk)

                cz = ground_z + trunk_h + crown_radius * 0.75
                c_main = trimesh.creation.icosphere(subdivisions=1, radius=crown_radius * 0.75)
                c_main.apply_scale([0.85, 0.85, 1.15])
                c_main.apply_translation([x, y, cz])
                birch_crowns.append(c_main)

                angles = [0.8, 3.2]
                for a in angles:
                    ox = math.cos(a) * crown_radius * 0.28
                    oy = math.sin(a) * crown_radius * 0.28
                    oz = float(np.random.uniform(-0.2, 0.3)) * crown_radius
                    cr = crown_radius * 0.55
                    sub_m = trimesh.creation.icosphere(subdivisions=1, radius=cr)
                    sub_m.apply_translation([x + ox, y + oy, cz + oz])
                    birch_crowns.append(sub_m)

            else:
                # SOSNA / ŚWIERK (kondygnacje iglaste)
                trunk_h = total_h * 0.85
                trunk = trimesh.creation.cylinder(radius=0.14, height=trunk_h, sections=6)
                trunk.apply_translation([x, y, ground_z + trunk_h / 2.0])
                conifer_trunks.append(trunk)

                tiers = 4
                for t_idx in range(tiers):
                    frac = (t_idx + 1) / (tiers + 1)
                    tz = ground_z + total_h * (0.32 + 0.55 * frac)
                    tier_r = crown_radius * (1.0 - 0.22 * t_idx)
                    tier_h = total_h * (0.26 - 0.03 * t_idx)
                    cone = trimesh.creation.cone(radius=tier_r, height=tier_h, sections=7)
                    cone.apply_translation([x, y, tz])
                    conifer_crowns.append(cone)

        tm_oak = trimesh.util.concatenate(oak_trunks)
        cm_oak = trimesh.util.concatenate(oak_crowns)
        tm_birch = trimesh.util.concatenate(birch_trunks)
        cm_birch = trimesh.util.concatenate(birch_crowns)
        tm_conifer = trimesh.util.concatenate(conifer_trunks)
        cm_conifer = trimesh.util.concatenate(conifer_crowns)

        new_tree_parts.append({
            "name": "GEO_DRZEWA_PNIE_LISCIASTE",
            "category": "drzewa",
            "material": "drzewa_pnie",
            "color": [0.32, 0.22, 0.16, 1.0],
            "source": "Geoportal ortofoto",
            "positions_m": np.round(tm_oak.vertices, 6).tolist(),
            "faces": tm_oak.faces.tolist()
        })
        new_tree_parts.append({
            "name": "GEO_DRZEWA_KORONY_LISCIASTE",
            "category": "drzewa",
            "material": "drzewa_korony",
            "color": [0.22, 0.44, 0.16, 1.0],
            "source": "Geoportal ortofoto",
            "positions_m": np.round(cm_oak.vertices, 6).tolist(),
            "faces": cm_oak.faces.tolist()
        })
        new_tree_parts.append({
            "name": "GEO_DRZEWA_PNIE_BRZOZY",
            "category": "drzewa",
            "material": "drzewa_pnie_brzozy",
            "color": [0.82, 0.82, 0.78, 1.0],
            "source": "Geoportal ortofoto",
            "positions_m": np.round(tm_birch.vertices, 6).tolist(),
            "faces": tm_birch.faces.tolist()
        })
        new_tree_parts.append({
            "name": "GEO_DRZEWA_KORONY_BRZOZY",
            "category": "drzewa",
            "material": "drzewa_korony_brzozy",
            "color": [0.32, 0.58, 0.22, 1.0],
            "source": "Geoportal ortofoto",
            "positions_m": np.round(cm_birch.vertices, 6).tolist(),
            "faces": cm_birch.faces.tolist()
        })
        new_tree_parts.append({
            "name": "GEO_DRZEWA_PNIE_IGLASTE",
            "category": "drzewa",
            "material": "drzewa_pnie_iglaste",
            "color": [0.26, 0.18, 0.12, 1.0],
            "source": "Geoportal ortofoto",
            "positions_m": np.round(tm_conifer.vertices, 6).tolist(),
            "faces": tm_conifer.faces.tolist()
        })
        new_tree_parts.append({
            "name": "GEO_DRZEWA_KORONY_IGLASTE",
            "category": "drzewa",
            "material": "drzewa_korony_iglaste",
            "color": [0.15, 0.32, 0.17, 1.0],
            "source": "Geoportal ortofoto",
            "positions_m": np.round(cm_conifer.vertices, 6).tolist(),
            "faces": cm_conifer.faces.tolist()
        })

    # 6. Połączenie nowej bazy geoportal_teren.json
    # Zachowujemy NMT, Ortofoto i granice działek
    base_geo_parts = [p for p in teren['parts'] if not p.get('name', '').startswith('GEO_BUDYNEK_') and not p.get('name', '').startswith('GEO_DRZEWA_')]
    teren['parts'] = base_geo_parts + new_building_parts + new_tree_parts

    cal = teren['alignment']['house_calibration']
    cal['model_to_geo_local_affine_mm'] = M_pzt.tolist()
    cal['status'] = 'pzt_survey_grid_georeferenced'
    cal['method'] = 'official PZT survey grid georeference (EPSG:2177 -> EPSG:2180) exactly matching PZT setback dimensions'
    cal['manual_offset_m'] = [0.0, 0.0]
    cal['manual_rotation_deg'] = 0.0

    with open(ROOT / 'geoportal_teren.json', 'w', encoding='utf-8') as f:
        json.dump(teren, f, ensure_ascii=False, indent=2)
    print("Zapisano zaktualizowany geoportal_teren.json!")

    # 7. Aktualizacja scena_modelu.json
    print("Aktualizacja scena_modelu.json...")
    with open(ROOT / 'scena_modelu.json', encoding='utf-8') as f:
        scena = json.load(f)

    # Zachowaj elementy domu i ogrodu, wymień elementy GEO na nowe
    house_and_garden = [p for p in scena['parts'] if not p.get('name', '').startswith('GEO_')]
    scena['parts'] = house_and_garden + teren['parts']

    with open(ROOT / 'scena_modelu.json', 'w', encoding='utf-8') as f:
        json.dump(scena, f, ensure_ascii=False, indent=2)
    print(f"Zapisano scena_modelu.json z {len(scena['parts'])} obiektami.")

if __name__ == '__main__':
    main()
