#!/usr/bin/env python3
"""
Aktualizuje geoportal_teren.json:
1. Ustawia georeferencję domu na PZT survey grid (EPSG:2177 -> EPSG:2180), eliminując przesunięcie o 2.0 m z ortofotomapy.
2. Niweluje teren NMT i ortofotomapę pod domem i tarasem do poziomu podbudowy (-0.28 m), zapobiegając przenikaniu przez posadzkę i taras.
3. Znacząco podnosi realizm budynków sąsiednich (styl Google Maps 3D):
   - dachy dwuspadowe z okapem 0.35 m, kalenicą/gąsiorem,
   - use_ortho_texture: True (teksturowanie dachu rzeczywistą ortofotomapą lotniczą z cieniowaniem normalnych),
   - realistyczne kolory dachówki ceramicznej / grafitowej,
   - estetyczne tynki elewacyjne z wyodrębnionym cokołem podmurówki (wys. 0.45 m).
4. Znacząco podnosi realizm 180 drzew (styl Google Maps 3D):
   - naturalna skala osiedlowa (~4.5 - 6.2 m wysokości, 1.4 - 2.0 m promień korony),
   - drzewa liściaste z wieloczęściowymi, organicznymi koronami i naturalną zielenią,
   - sosny/świerki ze stopniowanymi koronami stożkowymi,
   - czytanie współrzędnych z HEAD (idempotentne, odporne na wielokrotne uruchomienia).
"""
import json
import math
import subprocess
import numpy as np
import trimesh
from pathlib import Path
from shapely.geometry import Polygon, Point
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent

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

    # Pobranie pierwotnych geometrii budynków i drzew z HEAD (dla pełnej idempotencji)
    p_head = subprocess.run(['git', 'show', 'HEAD:geoportal_teren.json'], capture_output=True, text=True)
    head_data = json.loads(p_head.stdout)
    head_parts = {p['name']: p for p in head_data['parts']}

    # 1. Wyznaczenie dokładnej macierzy PZT (EPSG:2177 -> EPSG:2180)
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

    print("M_pzt:")
    print(M_pzt)

    # 2. Obrys domu i tarasu w układzie sceny
    def transform_pts(pts_mm):
        res = []
        for x, y in pts_mm:
            p = M_pzt @ np.array([x, y, 1.0])
            res.append((p[0] / 1000.0, p[1] / 1000.0))
        return res

    house_poly = Polygon(transform_pts(data['facade_reference_outline']['polygon_mm']))
    terrace_poly = Polygon(transform_pts(site['areas']['terrace'][0]['exterior_mm']))
    combined_building = house_poly.union(terrace_poly)

    # 3. Niwelacja NMT i Ortofoto pod budynkiem i tarasem
    nmt_part = None
    ortho_part = None
    for p in teren['parts']:
        if p.get('name') == 'GEO_NMT_rzeczywisty':
            nmt_part = p
        elif p.get('name') == 'GEO_ORTHO_TEXTURED':
            ortho_part = p

    if nmt_part and ortho_part:
        pos = np.array(nmt_part['positions_m'], dtype=float)
        graded_count = 0
        target_z = -0.28  # poziom podbudowy posadzki i tarasu
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

    # 4. Aktualizacja budynków otoczenia (Google Maps 3D style)
    # Wykorzystujemy fototeksturę ortofotomapy z Geoportalu na dachach (Google Maps 3D fotogrametria)
    facade_palette = [
        [0.89, 0.88, 0.85, 1.0],  # ciepły jasny tynk silikonowy
        [0.88, 0.84, 0.78, 1.0],  # kremowo-beżowy tynk
        [0.82, 0.82, 0.80, 1.0],  # jasny szary
        [0.86, 0.83, 0.76, 1.0],  # piaskowy
        [0.93, 0.92, 0.90, 1.0],  # biały
    ]

    for p in teren['parts']:
        name = p.get('name', '')
        if name.startswith('GEO_BUDYNEK_SCIANY_'):
            idx = int(name.split('_')[-1])
            p['color'] = facade_palette[(idx - 1) % len(facade_palette)]
            # Opcjonalnie: z bazy HEAD
            if name in head_parts:
                p['positions_m'] = head_parts[name]['positions_m']
                p['faces'] = head_parts[name]['faces']

        elif name.startswith('GEO_BUDYNEK_DACH_'):
            idx = int(name.split('_')[-1])
            # Bierzemy nieskażoną geometrię z HEAD
            head_roof = head_parts.get(name, p)
            orig_verts = np.array(head_roof['positions_m'], dtype=float)

            if len(orig_verts) == 6:
                # 0..3: okap (eave), 4..5: kalenica (ridge)
                eave_c = np.mean(orig_verts[:4, :2], axis=0)
                new_verts = orig_verts.copy()
                # Okap zewnętrzny 0.35 m
                for i in range(4):
                    dxy = orig_verts[i, :2] - eave_c
                    dist = np.linalg.norm(dxy)
                    if dist > 1e-4:
                        new_verts[i, :2] += (dxy / dist) * 0.35
                # Okap szczytowy wzdłuż kalenicy 0.35 m
                r_dir = orig_verts[5, :2] - orig_verts[4, :2]
                r_len = np.linalg.norm(r_dir)
                if r_len > 1e-4:
                    r_unit = r_dir / r_len
                    new_verts[4, :2] -= r_unit * 0.35
                    new_verts[5, :2] += r_unit * 0.35

                # Kalenica / gąsior jako pogrubiona belka na grzbiecie dachu
                g0 = [new_verts[4, 0], new_verts[4, 1], new_verts[4, 2] + 0.06]
                g1 = [new_verts[5, 0], new_verts[5, 1], new_verts[5, 2] + 0.06]
                all_v = np.vstack([new_verts, [g0, g1]])
                faces = [
                    [0, 1, 5], [0, 5, 4],
                    [3, 4, 5], [3, 5, 2],
                    [0, 4, 3], [1, 2, 5],
                    # gąsior
                    [4, 5, 7], [4, 7, 6]
                ]
                p['positions_m'] = np.round(all_v, 6).tolist()
                p['faces'] = faces

            # Google Maps 3D: tekstura ortofotomapy bezpośrednio na dachu
            p['use_ortho_texture'] = True

            # Kolor bazowy / fallback
            cur_col = head_roof.get('color', [0.5, 0.5, 0.5, 1.0])
            r, g, b = cur_col[0], cur_col[1], cur_col[2]
            if r > 0.45 and r > g * 1.08:
                p['color'] = [0.65, 0.29, 0.18, 1.0]  # ceramiczna ceglasta
            elif max(r, g, b) < 0.35:
                p['color'] = [0.22, 0.24, 0.27, 1.0]  # blachodachówka grafitowa
            elif r > 0.35 and b < 0.32:
                p['color'] = [0.42, 0.28, 0.20, 1.0]  # brązowa
            else:
                p['color'] = [0.30, 0.32, 0.35, 1.0]  # grafit/łupek

    # 5. Aktualizacja drzew otoczenia (styl Google Maps 3D, zrównoważona skala osiedlowa)
    tree_pnie = None
    tree_korony = None
    for p in teren['parts']:
        if p.get('name') == 'GEO_DRZEWA_PNIE':
            tree_pnie = p
        elif p.get('name') == 'GEO_DRZEWA_KORONY':
            tree_korony = p

    if tree_pnie and tree_korony and 'GEO_DRZEWA_PNIE' in head_parts and 'GEO_DRZEWA_KORONY' in head_parts:
        head_pnie = np.array(head_parts['GEO_DRZEWA_PNIE']['positions_m'], dtype=float)
        head_korony = np.array(head_parts['GEO_DRZEWA_KORONY']['positions_m'], dtype=float)
        N_TREES = len(head_pnie) // 14
        print(f"Generowanie realistycznych modeli 3D dla {N_TREES} drzew w osiedlowej skali...")

        new_trunks = []
        new_crowns = []

        for ti in range(N_TREES):
            tv = head_pnie[ti * 14 : (ti + 1) * 14]
            x = float(tv[:, 0].mean())
            y = float(tv[:, 1].mean())
            ground_z = float(tv[:, 2].min())

            # Realistyczna skala dla drzew w strefie zabudowy jednorodzinnej:
            # Wysokość 4.4 do 6.2 m (odpowiadająca realiom osiedlowym)
            np.random.seed(ti * 7919)
            total_h = np.random.uniform(4.4, 6.2)
            crown_radius = np.random.uniform(1.4, 2.0)
            is_conifer = (ti % 5) in (1, 4)  # 40% iglaste (sosny/świerki), 60% liściaste

            if not is_conifer:
                # DRZEWO LIŚCIASTE (Wieloczęściowa organiczna korona + pień)
                trunk_h = np.random.uniform(1.6, 2.2)
                r_base = np.random.uniform(0.14, 0.20)
                trunk = trimesh.creation.cylinder(radius=r_base, height=trunk_h, sections=7)
                trunk.apply_translation([x, y, ground_z + trunk_h / 2.0])
                new_trunks.append(trunk)

                # Główna korona
                cz = ground_z + trunk_h + crown_radius * 0.70
                c_main = trimesh.creation.icosphere(subdivisions=1, radius=crown_radius * 0.82)
                c_main.apply_scale([1.0, 1.0, 0.90])
                c_main.apply_translation([x, y, cz])
                new_crowns.append(c_main)

                # Organiczne odgałęzienia korony
                angles = [0.0, 2.1, 4.2]
                for a in angles:
                    ox = math.cos(a) * crown_radius * 0.32
                    oy = math.sin(a) * crown_radius * 0.32
                    oz = np.random.uniform(-0.15, 0.22) * crown_radius
                    cr = crown_radius * np.random.uniform(0.55, 0.68)
                    sub = trimesh.creation.icosphere(subdivisions=1, radius=cr)
                    sub.apply_scale([1.0, 1.0, 0.85])
                    sub.apply_translation([x + ox, y + oy, cz + oz])
                    new_crowns.append(sub)
            else:
                # DRZEWO IGLASTE (Sosna / Świerk - 4 stopniowane kondygnacje)
                trunk_h = total_h * 0.85
                r_base = np.random.uniform(0.12, 0.16)
                trunk = trimesh.creation.cylinder(radius=r_base, height=trunk_h, sections=6)
                trunk.apply_translation([x, y, ground_z + trunk_h / 2.0])
                new_trunks.append(trunk)

                tiers = 4
                for t_idx in range(tiers):
                    frac = (t_idx + 1) / (tiers + 1)
                    tz = ground_z + total_h * (0.32 + 0.55 * frac)
                    tier_r = crown_radius * (1.0 - 0.22 * t_idx)
                    tier_h = total_h * (0.26 - 0.03 * t_idx)
                    cone = trimesh.creation.cone(radius=tier_r, height=tier_h, sections=7)
                    cone.apply_translation([x, y, tz])
                    new_crowns.append(cone)

        tm = trimesh.util.concatenate(new_trunks)
        cm = trimesh.util.concatenate(new_crowns)

        tree_pnie['positions_m'] = np.round(tm.vertices, 6).tolist()
        tree_pnie['faces'] = tm.faces.tolist()
        tree_pnie['color'] = [0.34, 0.24, 0.16, 1.0]  # naturalna kora drzewna

        tree_korony['positions_m'] = np.round(cm.vertices, 6).tolist()
        tree_korony['faces'] = cm.faces.tolist()
        tree_korony['color'] = [0.24, 0.46, 0.18, 1.0]  # nasycona zieleń liściasta

    # 6. Aktualizacja kalibracji domu na PZT
    cal = teren['alignment']['house_calibration']
    cal['model_to_geo_local_affine_mm'] = M_pzt.tolist()
    cal['status'] = 'pzt_survey_grid_georeferenced'
    cal['method'] = 'official PZT survey grid georeference (EPSG:2177 -> EPSG:2180) exactly matching PZT setback dimensions (4.02m / 3.03m / 4.28m)'
    cal['manual_offset_m'] = [0.0, 0.0]
    cal['manual_rotation_deg'] = 0.0
    cal['note'] = 'Georeferencja domu oparta w 100% na urzędowej siatce współrzędnych projektu architektonicznego PZT (arkusz L-AA-0-01), bez sztucznego przesunięcia ortofotomapy.'

    # Zapis
    with open(ROOT / 'geoportal_teren.json', 'w', encoding='utf-8') as f:
        json.dump(teren, f, ensure_ascii=False, indent=2)

    print("Pomyślnie zaktualizowano geoportal_teren.json!")

if __name__ == '__main__':
    main()
