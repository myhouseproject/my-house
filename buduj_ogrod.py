"""
Generator kompletnego modelu 3D ogrodu na podstawie projektu Kōyō Landscape (A.1, A.2, A.3).
Wszystkie elementy ogrodu mieszczą się w 100% w granicach działki ewidencyjnej 4/13.

Precyzyjne warstwowanie:
1. Teren NMT: Z_nmt (baza)
2. Ortofotomapa: Z_nmt + 0.025 m
3. Granica działki: Z_nmt + 0.045 m (zagęszczona wstęga co 1m)
4. Ogród: nawierzchnie Z_nmt + 0.07..0.14 m, obiekty/nasadzenia/oświetlenie Z_nmt + 0.08..
5. Dom: rzędne budynku parter Z=0.00..4.15 m
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon, Point

from geometria_pomocnicza import (
    make_box,
    make_cylinder,
    make_cone,
    make_sphere,
    make_quad,
    make_terrain_grid,
)

ROOT = Path(__file__).resolve().parent

# 1. Wczytanie sceny bazowej
scena_file = ROOT / "scena_modelu.json"
scena = json.loads(scena_file.read_text(encoding="utf-8"))
scena["parts"] = [p for p in scena["parts"] if not p.get("name", "").startswith("OGROD_")]

# 2. Budowa interpolatora rzędnych terenu NMT
nmt_part = None
for p in scena["parts"]:
    if p.get("name") == "GEO_NMT_rzeczywisty":
        nmt_part = p
        break

if not nmt_part:
    raise RuntimeError("Nie znaleziono GEO_NMT_rzeczywisty w scenie")

nmt_pos = np.array(nmt_part["positions_m"])
nmt_xy = nmt_pos[:, :2]
nmt_z = nmt_pos[:, 2]

def get_terrain_z(x: float, y: float) -> float:
    dists = np.hypot(nmt_xy[:, 0] - x, nmt_xy[:, 1] - y)
    k = 4
    idx = np.argpartition(dists, k)[:k]
    d_k = dists[idx]
    w = 1.0 / np.maximum(d_k, 1e-4)
    w /= np.sum(w)
    return float(np.sum(nmt_z[idx] * w))

# 3. Układ współrzędnych ogrodu (PZT survey grid)
p_stairs = np.array([9.0155, -5.8961])
u_len = np.array([0.176744, 0.984257])   # wzdłuż działki ku tyłowi
u_wid = np.array([0.984256, -0.176750])  # w poprzek w prawo (ku granicy płd-wsch)
DEFAULT_SOURCE = "Projekt KŌYŌ Landscape (A.1, A.2, A.3)"

def to_3d(L: float, W: float, z_offset: float = 0.0) -> list[float]:
    """Przelicza współrzędne ogrodu (L, W w metrach) na współrzędne modelu 3D (X, Y, Z)."""
    pt2d = p_stairs + L * u_len + W * u_wid
    z = get_terrain_z(pt2d[0], pt2d[1]) + z_offset
    return [round(float(pt2d[0]), 4), round(float(pt2d[1]), 4), round(float(z), 4)]

def coord_fn(L: float, W: float, z_offset: float = 0.0) -> list[float]:
    return to_3d(L, W, z_offset)

def get_east_fence_w(L: float) -> float:
    """Zwraca współrzędną W wschodniej granicy działki 4/13 w funkcji długości L."""
    if L >= 10.57:
        return 8.93 - ((L - 10.57) / (94.51 - 10.57)) * (8.93 - 7.91)
    else:
        return 8.93 + (10.57 - L) / (10.57 - (-9.00)) * (13.30 - 8.93)

def make_garden_box(
    name: str,
    category: str,
    color: list[float],
    L_center: float,
    W_center: float,
    L_len: float,
    W_len: float,
    height: float,
    z_base_offset: float = 0.06,
    note: str = "",
) -> dict:
    half_L = L_len / 2.0
    half_W = W_len / 2.0

    corners_2d_offsets = [
        (-half_L, -half_W),
        (half_L, -half_W),
        (half_L, half_W),
        (-half_L, half_W),
    ]

    center_2d = p_stairs + L_center * u_len + W_center * u_wid
    corners_2d = [center_2d + dl * u_len + dw * u_wid for dl, dw in corners_2d_offsets]
    terrain_zs = [get_terrain_z(p[0], p[1]) for p in corners_2d]
    max_tz = max(terrain_zs)
    cz_bot = max_tz + z_base_offset
    cz_top = cz_bot + height

    verts = []
    # Dół
    for p in corners_2d:
        verts.append([round(float(p[0]), 4), round(float(p[1]), 4), round(float(cz_bot), 4)])
    # Góra
    for p in corners_2d:
        verts.append([round(float(p[0]), 4), round(float(p[1]), 4), round(float(cz_top), 4)])

    faces = [
        [0, 2, 1], [0, 3, 2], # dół
        [4, 5, 6], [4, 6, 7], # góra
        [0, 1, 5], [0, 5, 4], # bok 1
        [1, 2, 6], [1, 6, 5], # bok 2
        [2, 3, 7], [2, 7, 6], # bok 3
        [3, 0, 4], [3, 4, 7], # bok 4
    ]

    return {
        "name": name,
        "category": category,
        "material": category,
        "color": color,
        "positions_m": verts,
        "faces": faces,
        "geometry": "solid",
        "source": DEFAULT_SOURCE,
        "note": note,
        "default_visible": True,
        "geoportal_real": True,
    }


# ==============================================================================
# AKTUALIZACJA WARSTWY 3: DZIAŁKA (granica_dzialki)
# Zagęszczenie do siatki 1-metrowej na NMT (rzędna Z = Z_nmt + 0.045m)
# ==============================================================================
parcel_segments = [
    ("GEO_PARCEL_000", (33.5040, 85.7239), (19.6629, 88.7196)),
    ("GEO_PARCEL_001", (19.6629, 88.7196), (-4.4616, -45.5726)),
    ("GEO_PARCEL_002", (-4.4616, -45.5726), (4.6816, -47.1455)),
    ("GEO_PARCEL_003", (4.6816, -47.1455), (10.6142, -48.1652)),
    ("GEO_PARCEL_004", (10.6142, -48.1652), (6.2002, -74.4996)),
    ("GEO_PARCEL_005", (12.7150, -60.5662), (14.9432, -46.5748)),
    ("GEO_PARCEL_006", (14.9432, -46.5748), (20.5189, -17.1081)),
    ("GEO_PARCEL_007", (20.5189, -17.1081), (19.6709, 2.9313)),
    ("GEO_PARCEL_008", (19.6709, 2.9313), (33.5040, 85.7239)),
]

width = 0.18
step_m = 1.0

scena["parts"] = [
    p for p in scena["parts"]
    if not p.get("name", "").startswith("OGROD_")
    and p.get("category") != "granica_dzialki"
]

for name, p0_xy, p1_xy in parcel_segments:
    p0 = np.array(p0_xy)
    p1 = np.array(p1_xy)
    d = p1 - p0
    L = float(np.linalg.norm(d))
    perp = np.array([-d[1], d[0]]) / L * (width / 2.0)
    num_steps = max(1, int(math.ceil(L / step_m)))

    verts = []
    faces = []
    for s in range(num_steps + 1):
        t = s / num_steps
        pt = p0 + t * d
        left = pt - perp
        right = pt + perp
        z_left = get_terrain_z(left[0], left[1]) + 0.045
        z_right = get_terrain_z(right[0], right[1]) + 0.045
        idx = len(verts)
        verts.append([round(float(left[0]), 4), round(float(left[1]), 4), round(float(z_left), 4)])
        verts.append([round(float(right[0]), 4), round(float(right[1]), 4), round(float(z_right), 4)])
        if s > 0:
            pl = idx - 2
            pr = idx - 1
            faces.append([pl, pr, idx + 1])
            faces.append([pl, idx + 1, idx])

    scena["parts"].append({
        "name": name,
        "category": "granica_dzialki",
        "material": "granica_dzialki",
        "color": [0.97, 0.48, 0.05, 1.0],
        "source": "GUGiK ULDK / EGiB",
        "source_id": "GEO_PARCEL",
        "assumed": False,
        "note": "Granica działki ewidencyjnej z ULDK dopasowana do NMT.",
        "positions_m": verts,
        "faces": faces,
        "reference_area_m2": round(L * width, 4),
    })

print("Zaktualizowano warstwę granicy działki do NMT.")

new_parts = []

# ==============================================================================
# WARSTWA 4: OGRÓD - NAWIERZCHNIE I TRAWNIK REKREACYJNY (100% NA DZIAŁCE 4/13)
# ==============================================================================
c_lawn = [0.34, 0.58, 0.24, 1.0]
c_gres = [0.78, 0.74, 0.70, 1.0]
c_grosseto = [0.74, 0.76, 0.75, 1.0]
c_frappe = [0.66, 0.62, 0.58, 1.0]
c_dakota = [0.26, 0.28, 0.30, 1.0]
c_grys = [0.88, 0.87, 0.85, 1.0]
c_kwarcyt = [0.64, 0.62, 0.58, 1.0]
c_pitch_turf = [0.38, 0.64, 0.22, 1.0]
c_safe = [0.68, 0.36, 0.26, 1.0]

# 1. Główny trawnik rekreacyjny ogrodu na działce 4/13 (A.2)
# W granicach działki: W od -5.20 do +6.80 m (szerokość 12 m, bezpieczny margines do obu płotów)
l_lawn = np.linspace(1.84, 78.0, 39)
w_lawn = np.linspace(-5.20, 6.80, 13)
new_parts.append(make_terrain_grid(
    "OGROD_TRAWNIK_GLOWNY", "ogrod_nawierzchnie", c_lawn,
    l_lawn, w_lawn, coord_fn, z_base_offset=0.065, height=0.025,
    note="Trawnik rekreacyjny: mieszanka traw gazonowych odpornych na deptanie (arkusz A.2)."
))

# 2. Pas z kostki Kalifornia mix Frappe wzdłuż schodów tarasu (szer. 1.84 m)
l_frappe = np.linspace(0.0, 1.84, 3)
w_frappe = np.linspace(-3.5, 3.5, 8)
new_parts.append(make_terrain_grid(
    "OGROD_KOSTKA_FRAPPE_OPASKA", "ogrod_nawierzchnie", c_frappe,
    l_frappe, w_frappe, coord_fn, z_base_offset=0.075, height=0.060,
    note="Kostka Kalifornia producent Kost-Bet, kolor mix A12 Frappe (pow. 78 m²)."
))

# 3. Pasy jasnego grysu Biała Marianna wzdłuż granic działki
# Pas zachodni (wzdłuż granicy W = -6.24 m)
l_grys = np.linspace(0.0, 78.0, 40)
w_grys_zach = np.linspace(-6.15, -5.25, 3)
new_parts.append(make_terrain_grid(
    "OGROD_GRYS_PAS_ZACHOD", "ogrod_nawierzchnie", c_grys,
    l_grys, w_grys_zach, coord_fn, z_base_offset=0.075, height=0.040,
    note="Grys jasny Biała Marianna wzdłuż zachodniej granicy działki 4/13."
))

# Pas wschodni (wzdłuż wschodniej granicy działki)
w_grys_wsch = np.linspace(6.85, 7.75, 3)
new_parts.append(make_terrain_grid(
    "OGROD_GRYS_PAS_WSCHOD", "ogrod_nawierzchnie", c_grys,
    l_grys, w_grys_wsch, coord_fn, z_base_offset=0.075, height=0.040,
    note="Grys jasny Biała Marianna wzdłuż wschodniej granicy działki 4/13."
))

# 4. Leśny meander z białym grysem Marianna (L: 78.4 do 93.0 m, W: -5.20 do 6.80 m)
l_meander = np.linspace(78.4, 93.0, 12)
w_meander = np.linspace(-5.20, 6.80, 11)
new_parts.append(make_terrain_grid(
    "OGROD_GRYS_LESNY_MEANDER", "ogrod_nawierzchnie", c_grys,
    l_meander, w_meander, coord_fn, z_base_offset=0.075, height=0.040,
    note="Strefa leśna R1 z białym grysem Marianna i meandrującą ścieżką kwarcytową."
))

# 12 Płyt kwarcytowych na meandrującej ścieżce leśnej (skorygowane na działkę)
meander_pts = [
    (79.5, -3.5), (80.8, -2.2), (82.0, -1.0), (83.2, 0.2),
    (84.5, 1.4), (85.8, 2.0), (87.0, 1.4), (88.2, 0.0),
    (89.5, -1.5), (90.8, -2.6), (92.0, -1.5), (92.8, 0.2)
]
for idx, (l_pt, w_pt) in enumerate(meander_pts):
    new_parts.append(make_garden_box(
        f"OGROD_KWARCYT_{idx+1:02d}", "ogrod_nawierzchnie", c_kwarcyt,
        L_center=l_pt, W_center=w_pt, L_len=0.75, W_len=0.55, height=0.045, z_base_offset=0.095,
        note=f"Ścieżka: Płyta Kwarcytowa Trawnikowa {idx+1}/{len(meander_pts)} (pow. 4 m²)."
    ))

# 5. Boisko wielofunkcyjne trawiaste sportowe (24.0 x 10.8 m, wycentrowane na działce)
l_pitch = np.linspace(54.0, 78.0, 17)
w_pitch = np.linspace(-4.50, 6.30, 11)
new_parts.append(make_terrain_grid(
    "OGROD_BOISKO_MURAWA", "ogrod_nawierzchnie", c_pitch_turf,
    l_pitch, w_pitch, coord_fn, z_base_offset=0.070, height=0.040,
    note="Boisko wielofunkcyjne: nawierzchnia trawiasta sportowa 24,0 × 10,8 m, w 100% na działce 4/13."
))

# Linia środkowa boiska
l_line = np.linspace(65.95, 66.05, 2)
w_line = np.linspace(-4.30, 6.10, 15)
new_parts.append(make_terrain_grid(
    "OGROD_BOISKO_LINIA_SRODKOWA", "ogrod_nawierzchnie", [0.96, 0.96, 0.96, 1.0],
    l_line, w_line, coord_fn, z_base_offset=0.110, height=0.008,
    note="Linia środkowa boiska wielofunkcyjnego."
))

# 6. Nawierzchnia bezpieczna pod plac zabaw (5.64 x 4.00 m)
l_safe = np.linspace(18.0, 23.64, 7)
w_safe = np.linspace(1.8, 5.8, 5)
new_parts.append(make_terrain_grid(
    "OGROD_NAWIERZCHNIA_BEZPIECZNA", "ogrod_nawierzchnie", c_safe,
    l_safe, w_safe, coord_fn, z_base_offset=0.070, height=0.050,
    note="Nawierzchnia bezpieczna moduły 50×50 cm, kolor terakota EPDM (pow. 19 m²)."
))

# 7. Kostka Dakota pod domek narzędziowy
l_dakota = np.linspace(42.5, 45.5, 5)
w_dakota = np.linspace(1.7, 4.7, 5)
new_parts.append(make_terrain_grid(
    "OGROD_KOSTKA_DAKOTA_DOMEK", "ogrod_nawierzchnie", c_dakota,
    l_dakota, w_dakota, coord_fn, z_base_offset=0.075, height=0.060,
    note="Kostka Dakota producent Kost-Bet, kolor standard grafit (pow. 29,8 m²)."
))

# 8. Płyty Grosseto 90x60 cm (ścieżki ogrodowe)
for col, dw in enumerate([0.52, 1.48]):
    for row in range(7):
        l_pos = 2.3 + row * 0.95
        new_parts.append(make_garden_box(
            f"OGROD_GROSSETO_FRONT_{col}_{row}", "ogrod_nawierzchnie", c_grosseto,
            L_center=l_pos, W_center=dw, L_len=0.90, W_len=0.60, height=0.06, z_base_offset=0.08,
            note="Płyta Grosseto 90×60 cm producent Kost-Bet, standard szary — ścieżka w trawniku."
        ))

for col, dw in enumerate([0.52, 1.48]):
    for row in range(2):
        l_pos = 23.2 + row * 0.95
        new_parts.append(make_garden_box(
            f"OGROD_GROSSETO_PRZED_BASENEM_{col}_{row}", "ogrod_nawierzchnie", c_grosseto,
            L_center=l_pos, W_center=dw, L_len=0.90, W_len=0.60, height=0.06, z_base_offset=0.08,
            note="Płyta Grosseto 90×60 cm — podejście do plaży basenowej."
        ))

for col, dw in enumerate([0.52, 1.48]):
    for row in range(2):
        l_pos = 35.8 + row * 0.95
        new_parts.append(make_garden_box(
            f"OGROD_GROSSETO_ZA_BASENEM_{col}_{row}", "ogrod_nawierzchnie", c_grosseto,
            L_center=l_pos, W_center=dw, L_len=0.90, W_len=0.60, height=0.06, z_base_offset=0.08,
            note="Płyta Grosseto 90×60 cm — zejście z plaży basenowej do ogrodu."
        ))

for col, dw in enumerate([-3.8, -2.8]):
    for row in range(2):
        l_pos = 38.5 + row * 0.95
        new_parts.append(make_garden_box(
            f"OGROD_GROSSETO_SZKLARNIA_{col}_{row}", "ogrod_nawierzchnie", c_grosseto,
            L_center=l_pos, W_center=dw, L_len=0.90, W_len=0.60, height=0.06, z_base_offset=0.08,
            note="Płyta Grosseto 90×60 cm — dojście do szklarni."
        ))

for col, dw in enumerate([2.0, 3.0]):
    for row in range(4):
        l_pos = 52.5 + row * 0.95
        new_parts.append(make_garden_box(
            f"OGROD_GROSSETO_WARZYWA_{col}_{row}", "ogrod_nawierzchnie", c_grosseto,
            L_center=l_pos, W_center=dw, L_len=0.90, W_len=0.60, height=0.06, z_base_offset=0.08,
            note="Płyta Grosseto 90×60 cm — ścieżka przy strefie warzywnej."
        ))

# ==============================================================================
# 9. TARAS BASENOWY I BASEN POLYSTONE (A.1 / A.2)
# Wycentrowany na działce 4/13: W od -2.50 do +4.50 m (szerokość 7.00 m)
# Ujednolicony poziom tarasu Z_terrace = -1.00 m z cokołem oporowym do terenu
# ==============================================================================
Z_TERRACE = -1.00
H_SLAB = 0.08

def make_level_box(
    name: str,
    category: str,
    color: list[float],
    L_min: float,
    L_max: float,
    W_min: float,
    W_max: float,
    z_top: float,
    z_bot: float,
    note: str = "",
) -> dict:
    corners = [(L_min, W_min), (L_max, W_min), (L_max, W_max), (L_min, W_max)]
    verts = []
    # bot
    for l, w in corners:
        p = p_stairs + l * u_len + w * u_wid
        verts.append([round(float(p[0]), 4), round(float(p[1]), 4), round(float(z_bot), 4)])
    # top
    for l, w in corners:
        p = p_stairs + l * u_len + w * u_wid
        verts.append([round(float(p[0]), 4), round(float(p[1]), 4), round(float(z_top), 4)])

    faces = [
        [0, 2, 1], [0, 3, 2],
        [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4],
        [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6],
        [3, 0, 4], [3, 4, 7],
    ]
    return {
        "name": name,
        "category": category,
        "material": category,
        "color": color,
        "positions_m": verts,
        "faces": faces,
        "geometry": "solid",
        "source": DEFAULT_SOURCE,
        "note": note,
        "default_visible": True,
        "geoportal_real": True,
    }

# 4 Części plaży tarasu basenowego z gresu ZOYA Sandstone Grey 60x60
new_parts.append(make_level_box(
    "OGROD_TARAS_BASEN_ZACHOD", "ogrod_nawierzchnie", c_gres,
    L_min=25.0, L_max=26.0, W_min=-2.50, W_max=4.50, z_top=Z_TERRACE, z_bot=Z_TERRACE - H_SLAB,
    note="Plaża basenowa zachodnia: Gres ZOYA 2.0 Sandstone Grey 60×60×2 cm."
))
new_parts.append(make_level_box(
    "OGROD_TARAS_BASEN_WSCHOD", "ogrod_nawierzchnie", c_gres,
    L_min=34.0, L_max=35.0, W_min=-2.50, W_max=4.50, z_top=Z_TERRACE, z_bot=Z_TERRACE - H_SLAB,
    note="Plaża basenowa wschodnia: Gres ZOYA 2.0 Sandstone Grey 60×60×2 cm."
))
new_parts.append(make_level_box(
    "OGROD_TARAS_BASEN_POLNOC", "ogrod_nawierzchnie", c_gres,
    L_min=26.0, L_max=34.0, W_min=-2.50, W_max=-1.00, z_top=Z_TERRACE, z_bot=Z_TERRACE - H_SLAB,
    note="Plaża basenowa północna: Gres ZOYA 2.0 Sandstone Grey 60×60×2 cm."
))
new_parts.append(make_level_box(
    "OGROD_TARAS_BASEN_POLUDNIE", "ogrod_nawierzchnie", c_gres,
    L_min=26.0, L_max=34.0, W_min=3.00, W_max=4.50, z_top=Z_TERRACE, z_bot=Z_TERRACE - H_SLAB,
    note="Plaża basenowa południowa: Gres ZOYA 2.0 Sandstone Grey 60×60×2 cm."
))

# Cokół oporowy tarasu basenowego na obwodzie
c_cokol = [0.42, 0.44, 0.46, 1.0]

cokol_pts_w = [p_stairs + 25.0 * u_len + w * u_wid for w in np.linspace(-2.50, 4.50, 8)]
verts_cw = []
faces_cw = []
for idx, pt in enumerate(cokol_pts_w):
    tz = get_terrain_z(pt[0], pt[1]) - 0.08
    v_idx = len(verts_cw)
    verts_cw.append([round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(tz), 4)])
    verts_cw.append([round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(Z_TERRACE), 4)])
    if idx > 0:
        p_bot = v_idx - 2
        p_top = v_idx - 1
        faces_cw.append([p_bot, v_idx + 1, p_top])
        faces_cw.append([p_bot, v_idx, v_idx + 1])
new_parts.append({
    "name": "OGROD_TARAS_COKOL_ZACH", "category": "ogrod_nawierzchnie", "material": "ogrod_nawierzchnie",
    "color": c_cokol, "positions_m": verts_cw, "faces": faces_cw, "geometry": "solid",
    "source": DEFAULT_SOURCE, "note": "Cokół oporowy tarasu basenowego (strona zachodnia).",
    "default_visible": True, "geoportal_real": True,
})

cokol_pts_e = [p_stairs + 35.0 * u_len + w * u_wid for w in np.linspace(-2.50, 4.50, 8)]
verts_ce = []
faces_ce = []
for idx, pt in enumerate(cokol_pts_e):
    tz = get_terrain_z(pt[0], pt[1]) - 0.08
    v_idx = len(verts_ce)
    verts_ce.append([round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(tz), 4)])
    verts_ce.append([round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(Z_TERRACE), 4)])
    if idx > 0:
        p_bot = v_idx - 2
        p_top = v_idx - 1
        faces_ce.append([p_bot, p_top, v_idx + 1])
        faces_ce.append([p_bot, v_idx + 1, v_idx])
new_parts.append({
    "name": "OGROD_TARAS_COKOL_WSCH", "category": "ogrod_nawierzchnie", "material": "ogrod_nawierzchnie",
    "color": c_cokol, "positions_m": verts_ce, "faces": faces_ce, "geometry": "solid",
    "source": DEFAULT_SOURCE, "note": "Cokół oporowy tarasu basenowego (strona wschodnia).",
    "default_visible": True, "geoportal_real": True,
})

cokol_pts_s = [p_stairs + l * u_len + 4.50 * u_wid for l in np.linspace(25.0, 35.0, 11)]
verts_cs = []
faces_cs = []
for idx, pt in enumerate(cokol_pts_s):
    tz = get_terrain_z(pt[0], pt[1]) - 0.08
    v_idx = len(verts_cs)
    verts_cs.append([round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(tz), 4)])
    verts_cs.append([round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(Z_TERRACE), 4)])
    if idx > 0:
        p_bot = v_idx - 2
        p_top = v_idx - 1
        faces_cs.append([p_bot, v_idx + 1, p_top])
        faces_cs.append([p_bot, v_idx, v_idx + 1])
new_parts.append({
    "name": "OGROD_TARAS_COKOL_POLD", "category": "ogrod_nawierzchnie", "material": "ogrod_nawierzchnie",
    "color": c_cokol, "positions_m": verts_cs, "faces": faces_cs, "geometry": "solid",
    "source": DEFAULT_SOURCE, "note": "Cokół oporowy tarasu basenowego (strona południowa).",
    "default_visible": True, "geoportal_real": True,
})

cokol_pts_n = [p_stairs + l * u_len + (-2.50) * u_wid for l in np.linspace(25.0, 35.0, 11)]
verts_cn = []
faces_cn = []
for idx, pt in enumerate(cokol_pts_n):
    tz = get_terrain_z(pt[0], pt[1]) - 0.08
    v_idx = len(verts_cn)
    verts_cn.append([round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(tz), 4)])
    verts_cn.append([round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(Z_TERRACE), 4)])
    if idx > 0:
        p_bot = v_idx - 2
        p_top = v_idx - 1
        faces_cn.append([p_bot, p_top, v_idx + 1])
        faces_cn.append([p_bot, v_idx + 1, v_idx])
new_parts.append({
    "name": "OGROD_TARAS_COKOL_POLN", "category": "ogrod_nawierzchnie", "material": "ogrod_nawierzchnie",
    "color": c_cokol, "positions_m": verts_cn, "faces": faces_cn, "geometry": "solid",
    "source": DEFAULT_SOURCE, "note": "Cokół oporowy tarasu basenowego (strona północna).",
    "default_visible": True, "geoportal_real": True,
})

# Niecka basenu Polystone (8.0 x 4.0 m, głębokość 1.50 m)
c_pool_shell = [0.08, 0.35, 0.65, 1.0]
Z_POOL_DNO = Z_TERRACE - 1.50

new_parts.append(make_level_box(
    "OGROD_BASEN_DNO", "ogrod_woda", c_pool_shell,
    L_min=26.0, L_max=34.0, W_min=-1.00, W_max=3.00, z_top=Z_POOL_DNO + 0.08, z_bot=Z_POOL_DNO,
    note="Dno basenu Polystone niebieskiego 4×8 m."
))
new_parts.append(make_level_box(
    "OGROD_BASEN_SCIANA_ZACH", "ogrod_woda", c_pool_shell,
    L_min=26.0, L_max=26.10, W_min=-1.00, W_max=3.00, z_top=Z_TERRACE, z_bot=Z_POOL_DNO,
    note="Ściana zachodnia niecki basenowej Polystone."
))
new_parts.append(make_level_box(
    "OGROD_BASEN_SCIANA_WSCH", "ogrod_woda", c_pool_shell,
    L_min=33.90, L_max=34.0, W_min=-1.00, W_max=3.00, z_top=Z_TERRACE, z_bot=Z_POOL_DNO,
    note="Ściana wschodnia niecki basenowej Polystone."
))
new_parts.append(make_level_box(
    "OGROD_BASEN_SCIANA_POLN", "ogrod_woda", c_pool_shell,
    L_min=26.10, L_max=33.90, W_min=-1.00, W_max=-0.90, z_top=Z_TERRACE, z_bot=Z_POOL_DNO,
    note="Ściana północna niecki basenowej Polystone."
))
new_parts.append(make_level_box(
    "OGROD_BASEN_SCIANA_POLD", "ogrod_woda", c_pool_shell,
    L_min=26.10, L_max=33.90, W_min=2.90, W_max=3.00, z_top=Z_TERRACE, z_bot=Z_POOL_DNO,
    note="Ściana południowa niecki basenowej Polystone."
))

# Lustro wody w basenie (krystaliczny błękit, lekko transparentny)
c_water = [0.12, 0.60, 0.94, 0.82]
new_parts.append(make_level_box(
    "OGROD_BASEN_WODA", "ogrod_woda", c_water,
    L_min=26.10, L_max=33.90, W_min=-0.90, W_max=2.90, z_top=Z_TERRACE - 0.10, z_bot=Z_TERRACE - 0.14,
    note="Lustro wody w basenie kąpielowym (wymiary 4×8 m)."
))

# Obrzeże basenu (biały kompozyt)
c_rim = [0.94, 0.94, 0.96, 1.0]
new_parts.append(make_level_box(
    "OGROD_BASEN_OBRZEZE_ZACH", "ogrod_nawierzchnie", c_rim,
    L_min=25.92, L_max=26.10, W_min=-1.10, W_max=3.10, z_top=Z_TERRACE + 0.02, z_bot=Z_TERRACE,
    note="Obrzeże przelewowe basenu."
))
new_parts.append(make_level_box(
    "OGROD_BASEN_OBRZEZE_WSCH", "ogrod_nawierzchnie", c_rim,
    L_min=33.90, L_max=34.08, W_min=-1.10, W_max=3.10, z_top=Z_TERRACE + 0.02, z_bot=Z_TERRACE,
    note="Obrzeże przelewowe basenu."
))
new_parts.append(make_level_box(
    "OGROD_BASEN_OBRZEZE_POLN", "ogrod_nawierzchnie", c_rim,
    L_min=26.10, L_max=33.90, W_min=-1.10, W_max=-0.92, z_top=Z_TERRACE + 0.02, z_bot=Z_TERRACE,
    note="Obrzeże przelewowe basenu."
))
new_parts.append(make_level_box(
    "OGROD_BASEN_OBRZEZE_POLD", "ogrod_nawierzchnie", c_rim,
    L_min=26.10, L_max=33.90, W_min=2.92, W_max=3.10, z_top=Z_TERRACE + 0.02, z_bot=Z_TERRACE,
    note="Obrzeże przelewowe basenu."
))

# Meble basenowe na plaży tarasowej
c_lounger_frame = [0.24, 0.26, 0.28, 1.0]
c_lounger_pad = [0.92, 0.92, 0.90, 1.0]
for idx, w_pos in enumerate([3.4, 4.1]):
    new_parts.append(make_level_box(
        f"OGROD_LEZAK_RAMA_{idx+1}", "ogrod_architektura", c_lounger_frame,
        L_min=34.1, L_max=34.9, W_min=w_pos - 0.25, W_max=w_pos + 0.25,
        z_top=Z_TERRACE + 0.25, z_bot=Z_TERRACE, note=f"Leżak basenowy {idx+1} z ramą antracytową."
    ))
    new_parts.append(make_level_box(
        f"OGROD_LEZAK_MATERAC_{idx+1}", "ogrod_architektura", c_lounger_pad,
        L_min=34.15, L_max=34.85, W_min=w_pos - 0.22, W_max=w_pos + 0.22,
        z_top=Z_TERRACE + 0.33, z_bot=Z_TERRACE + 0.25, note=f"Materac leżaka basenowego {idx+1}."
    ))

# Stół ogrodowy i krzesła na plaży basenowej
c_table = [0.35, 0.28, 0.22, 1.0]
new_parts.append(make_level_box(
    "OGROD_STOL_TARAS", "ogrod_architektura", c_table,
    L_min=29.1, L_max=30.9, W_min=-2.20, W_max=-1.30, z_top=Z_TERRACE + 0.74, z_bot=Z_TERRACE,
    note="Stół ogrodowy obiadowy na tarasie basenowym."
))
for idx, (dl, dw) in enumerate([(-0.6, -0.45), (0.6, -0.45), (-0.6, 0.45), (0.6, 0.45)]):
    new_parts.append(make_level_box(
        f"OGROD_KRZESLO_{idx+1}", "ogrod_architektura", c_lounger_frame,
        L_min=30.0 + dl - 0.20, L_max=30.0 + dl + 0.20, W_min=-1.75 + dw - 0.20, W_max=-1.75 + dw + 0.20,
        z_top=Z_TERRACE + 0.45, z_bot=Z_TERRACE, note=f"Krzesło ogrodowe {idx+1}."
    ))

# ==============================================================================
# WARSTWA 4: OGRÓD - MAŁA ARCHITEKTURA I STREFA SPORTOWA
# ==============================================================================
# Domek narzędziowy (2.50 x 3.00 m, wysokość 2.6 m, na L=44.0m, W=3.2m)
c_wood_shed = [0.58, 0.42, 0.28, 1.0]
c_shed_roof = [0.22, 0.24, 0.26, 1.0]
new_parts.append(make_garden_box(
    "OGROD_DOMEK_SCIANY", "ogrod_architektura", c_wood_shed,
    L_center=44.0, W_center=3.2, L_len=2.50, W_len=3.00, height=2.40, z_base_offset=0.08,
    note="Domek narzędziowy: wymiary 2,5×3,0 m, pionowe lamele drewniane."
))
new_parts.append(make_garden_box(
    "OGROD_DOMEK_DACH", "ogrod_architektura", c_shed_roof,
    L_center=44.0, W_center=3.2, L_len=2.70, W_len=3.20, height=0.15, z_base_offset=2.48,
    note="Dach jednospadowy domku narzędziowego w kolorze antracytowym."
))
new_parts.append(make_garden_box(
    "OGROD_DOMEK_DRZWI", "ogrod_architektura", [0.18, 0.20, 0.22, 1.0],
    L_center=42.74, W_center=3.2, L_len=0.06, W_len=0.90, height=2.00, z_base_offset=0.08,
    note="Drzwi wejściowe do domku narzędziowego."
))

# Szklarnia ogrodowa (1.80 x 3.00 m, wysokość 2.3 m na L=45.0m, W=-4.5m)
c_glass = [0.86, 0.94, 0.96, 0.45]
c_glass_frame = [0.18, 0.20, 0.22, 1.0]
new_parts.append(make_garden_box(
    "OGROD_SZKLARNIA_SZKLO", "ogrod_architektura", c_glass,
    L_center=45.0, W_center=-4.5, L_len=3.00, W_len=1.80, height=2.10, z_base_offset=0.08,
    note="Szklarnia ogrodowa: 3,0×1,8 m, bezpieczne szkło ogrodnicze."
))
new_parts.append(make_garden_box(
    "OGROD_SZKLARNIA_RAMA_COKOL", "ogrod_architektura", c_glass_frame,
    L_center=45.0, W_center=-4.5, L_len=3.04, W_len=1.84, height=0.10, z_base_offset=0.08,
    note="Aluminiowa podstawa cokołowa szklarni w kolorze antracytowym."
))
new_parts.append(make_garden_box(
    "OGROD_SZKLARNIA_KALENICA", "ogrod_architektura", c_glass_frame,
    L_center=45.0, W_center=-4.5, L_len=3.04, W_len=0.08, height=0.08, z_base_offset=2.18,
    note="Kalenica konstrukcyjna szklarni ogrodowej."
))

# 4 Skrzynie na warzywa (1.80 x 0.90 m, wysokość 0.60 m)
c_box_wood = [0.62, 0.46, 0.32, 1.0]
c_soil = [0.20, 0.16, 0.12, 1.0]
c_crops = [0.32, 0.68, 0.22, 1.0]
for idx, (dl, dw) in enumerate([
    (48.2, 2.3), (50.7, 2.3),
    (48.2, 3.9), (50.7, 3.9)
]):
    new_parts.append(make_garden_box(
        f"OGROD_SKRZYNIA_RAMA_{idx+1}", "ogrod_architektura", c_box_wood,
        L_center=dl, W_center=dw, L_len=1.80, W_len=0.90, height=0.60, z_base_offset=0.08,
        note=f"Skrzynia na warzywa {idx+1}/4: drewno impregnowane 180×90 cm, wys. 60 cm."
    ))
    new_parts.append(make_garden_box(
        f"OGROD_SKRZYNIA_ZIEMIA_{idx+1}", "ogrod_architektura", c_soil,
        L_center=dl, W_center=dw, L_len=1.60, W_len=0.70, height=0.10, z_base_offset=0.58,
        note=f"Podłoże próchnicze w skrzyni warzywnej {idx+1}."
    ))
    new_parts.append(make_garden_box(
        f"OGROD_SKRZYNIA_WARZYWA_{idx+1}", "ogrod_architektura", c_crops,
        L_center=dl, W_center=dw, L_len=1.50, W_len=0.60, height=0.20, z_base_offset=0.68,
        note=f"Uprawy ziół i warzyw w skrzyni {idx+1}."
    ))

# Plac zabaw Modulaki na nawierzchni bezpiecznej
c_play_wood = [0.68, 0.50, 0.32, 1.0]
c_slide = [0.96, 0.78, 0.12, 1.0]
new_parts.append(make_garden_box(
    "OGROD_PLAC_WIEZA", "ogrod_architektura", c_play_wood,
    L_center=20.0, W_center=3.2, L_len=1.40, W_len=1.40, height=2.80, z_base_offset=0.12,
    note="Wieża ze zjeżdżalnią — Plac zabaw producent: Modulaki."
))
new_parts.append(make_garden_box(
    "OGROD_PLAC_ZJEZDZALNIA", "ogrod_architektura", c_slide,
    L_center=21.8, W_center=3.2, L_len=2.20, W_len=0.55, height=0.80, z_base_offset=0.12,
    note="Zjeżdżalnia bezpieczna dla dzieci."
))
new_parts.append(make_garden_box(
    "OGROD_PLAC_HUSTAWKA", "ogrod_architektura", c_play_wood,
    L_center=20.0, W_center=4.8, L_len=0.15, W_len=2.00, height=2.20, z_base_offset=0.12,
    note="Belka podwójnej huśtawki na placu zabaw."
))

# Trampolina wpuszczana w ziemię (średnica 3.4m, na L=14.0m, W=-4.2m)
c_tramp_mat = [0.15, 0.16, 0.18, 1.0]
c_tramp_rim = [0.22, 0.55, 0.28, 1.0]
pt2d_tramp = p_stairs + 14.0 * u_len + (-4.2) * u_wid
r_tramp = 1.70
sample_zs = [get_terrain_z(pt2d_tramp[0] + r_tramp * math.cos(a), pt2d_tramp[1] + r_tramp * math.sin(a)) for a in np.linspace(0, 2*math.pi, 16)]
max_tz_tramp = max(sample_zs)
pt_tramp = [round(float(pt2d_tramp[0]), 4), round(float(pt2d_tramp[1]), 4), round(float(max_tz_tramp + 0.05), 4)]
new_parts.append(make_cylinder(
    "OGROD_TRAMPOLINA_MATA", "ogrod_architektura", c_tramp_mat,
    p_base=pt_tramp, p_top=[pt_tramp[0], pt_tramp[1], pt_tramp[2] + 0.04], radius=1.55, segments=16,
    note="Mata elastyczna trampoliny ogrodowej wpuszczanej w grunt."
))
new_parts.append(make_cylinder(
    "OGROD_TRAMPOLINA_KRAWEDZ", "ogrod_architektura", c_tramp_rim,
    p_base=[pt_tramp[0], pt_tramp[1], pt_tramp[2] + 0.04],
    p_top=[pt_tramp[0], pt_tramp[1], pt_tramp[2] + 0.10], radius=1.70, segments=16,
    note="Kołnierz ochronny trampoliny ogrodowej."
))

# Sprzęt boiska sportowego (osadzony na murawie Z_nmt + 0.11m)
c_pole = [0.85, 0.85, 0.88, 1.0]
c_net = [0.95, 0.95, 0.95, 0.75]
p_pole1 = to_3d(66.0, -4.40, 0.11)
new_parts.append(make_cylinder(
    "OGROD_SIATKA_SLUPEK_1", "ogrod_architektura", c_pole,
    p_base=p_pole1, p_top=[p_pole1[0], p_pole1[1], p_pole1[2] + 2.50], radius=0.05, segments=8,
    note="Słupek siatki do siatkówki (stal ocynkowana)."
))
p_pole2 = to_3d(66.0, 6.20, 0.11)
new_parts.append(make_cylinder(
    "OGROD_SIATKA_SLUPEK_2", "ogrod_architektura", c_pole,
    p_base=p_pole2, p_top=[p_pole2[0], p_pole2[1], p_pole2[2] + 2.50], radius=0.05, segments=8,
    note="Słupek siatki do siatkówki (stal ocynkowana)."
))
new_parts.append(make_garden_box(
    "OGROD_SIATKA_POWIERZCHNIA", "ogrod_architektura", c_net,
    L_center=66.0, W_center=0.90, L_len=0.02, W_len=10.50, height=1.00, z_base_offset=1.56,
    note="Siatka do siatkówki zawieszona na wysokości 2,43 m."
))

# Bramka piłkarska (3.0 x 2.0 m) na L=77.5m, wycentrowana na W=0.90m
c_goal = [0.95, 0.95, 0.95, 1.0]
p_g1 = to_3d(77.5, -0.60, 0.11)
new_parts.append(make_cylinder(
    "OGROD_BRAMKA_SLUPEK_L", "ogrod_architektura", c_goal,
    p_base=p_g1, p_top=[p_g1[0], p_g1[1], p_g1[2] + 2.00], radius=0.05, segments=8,
    note="Słupek lewy bramki do piłki nożnej (3×2 m)."
))
p_g2 = to_3d(77.5, 2.40, 0.11)
new_parts.append(make_cylinder(
    "OGROD_BRAMKA_SLUPEK_P", "ogrod_architektura", c_goal,
    p_base=p_g2, p_top=[p_g2[0], p_g2[1], p_g2[2] + 2.00], radius=0.05, segments=8,
    note="Słupek prawy bramki do piłki nożnej (3×2 m)."
))
new_parts.append(make_garden_box(
    "OGROD_BRAMKA_POPRZECZKA", "ogrod_architektura", c_goal,
    L_center=77.5, W_center=0.90, L_len=0.10, W_len=3.00, height=0.10, z_base_offset=2.06,
    note="Poprzeczka bramki piłkarskiej."
))
new_parts.append(make_garden_box(
    "OGROD_BRAMKA_SIATKA", "ogrod_architektura", c_net,
    L_center=77.9, W_center=0.90, L_len=0.80, W_len=3.00, height=2.00, z_base_offset=0.11,
    note="Siatka bramki piłkarskiej."
))

# Kosz do koszykówki nad bramką (wysokość 3.05 m, tablica 1.80 x 1.05 m)
p_bball = to_3d(78.0, 0.90, 0.11)
new_parts.append(make_cylinder(
    "OGROD_KOSZ_SLUP", "ogrod_architektura", [0.4, 0.4, 0.45, 1.0],
    p_base=p_bball, p_top=[p_bball[0], p_bball[1], p_bball[2] + 3.80], radius=0.08, segments=8,
    note="Słup stalowy kosza do koszykówki."
))
new_parts.append(make_garden_box(
    "OGROD_KOSZ_TABLICA", "ogrod_architektura", [0.92, 0.94, 0.96, 0.9],
    L_center=77.7, W_center=0.90, L_len=0.05, W_len=1.80, height=1.05, z_base_offset=2.71,
    note="Tablica do koszykówki z plexiglasu 180×105 cm."
))
new_parts.append(make_garden_box(
    "OGROD_KOSZ_OBRECZ", "ogrod_architektura", [0.95, 0.45, 0.05, 1.0],
    L_center=77.45, W_center=0.90, L_len=0.45, W_len=0.45, height=0.05, z_base_offset=3.16,
    note="Obręcz kosza z siatką na przepisowej wysokości 3,05 m."
))

# ==============================================================================
# WARSTWA 4: OGRÓD - NASADZENIA ROŚLINNE 3D (25 GATUNKÓW Z ARKUSZA A.3)
# ==============================================================================
c_bark = [0.32, 0.22, 0.14, 1.0]

def add_tree(
    name: str,
    L_pos: float,
    W_pos: float,
    trunk_h: float,
    trunk_r: float,
    crown_r: float,
    crown_color: list[float],
    shape: str = "sphere",
    crown_h: float = 3.0,
    note: str = "",
):
    pt2d = p_stairs + L_pos * u_len + W_pos * u_wid
    sample_zs = [get_terrain_z(pt2d[0] + trunk_r * math.cos(a), pt2d[1] + trunk_r * math.sin(a)) for a in np.linspace(0, 2*math.pi, 8)]
    max_tz = max(sample_zs)
    base_z = max_tz + 0.05
    pt_base = [round(float(pt2d[0]), 4), round(float(pt2d[1]), 4), round(float(base_z), 4)]
    pt_top = [pt_base[0], pt_base[1], round(float(base_z + trunk_h), 4)]
    new_parts.append(make_cylinder(
        f"{name}_PIEN", "ogrod_rosliny", c_bark,
        p_base=pt_base, p_top=pt_top, radius=trunk_r, segments=8,
        note=f"Pień drzewa: {note}"
    ))
    if shape == "cone":
        new_parts.append(make_cone(
            f"{name}_KORONA", "ogrod_rosliny", crown_color,
            p_base=[pt_base[0], pt_base[1], pt_base[2] + trunk_h * 0.4],
            height=crown_h, radius=crown_r, segments=10,
            note=note
        ))
    elif shape == "bonsai":
        for c_idx, (dl, dw, dz, cr) in enumerate([
            (0.0, 0.0, 0.0, crown_r),
            (0.3, -0.2, 0.3, crown_r * 0.75),
            (-0.2, 0.3, 0.5, crown_r * 0.65),
            (0.1, 0.1, 0.8, crown_r * 0.5)
        ]):
            new_parts.append(make_sphere(
                f"{name}_CHMURA_{c_idx+1}", "ogrod_rosliny", crown_color,
                center=[pt_top[0] + dl, pt_top[1] + dw, pt_top[2] + dz],
                radius=cr, segments=8, rings=5,
                note=note
            ))
    else:
        new_parts.append(make_sphere(
            f"{name}_KORONA", "ogrod_rosliny", crown_color,
            center=[pt_top[0], pt_top[1], pt_top[2] + crown_r * 0.7],
            radius=crown_r, segments=8, rings=5,
            note=note
        ))

# 1. Klon palmowy 'Fireglow' (Acer palmatum)
add_tree(
    "OGROD_KLON_PALMOWY", L_pos=1.5, W_pos=2.2, trunk_h=1.2, trunk_r=0.08, crown_r=1.4,
    crown_color=[0.74, 0.14, 0.18, 1.0],
    note="Poz. 4: Acer palmatum 'Fireglow' — klon palmowy bordowy przy tarasie."
)

# 2. Magnolia Alexandrina
add_tree(
    "OGROD_MAGNOLIA", L_pos=14.0, W_pos=-1.5, trunk_h=1.4, trunk_r=0.12, crown_r=1.8,
    crown_color=[0.42, 0.58, 0.34, 1.0],
    note="Poz. 2: Magnolia Alexandrina — magnolia soulangeana, kwitnący soliter."
)

# 3. Tulipanowiec amerykański 'Edward Gursztyn'
add_tree(
    "OGROD_TULIPANOWIEC", L_pos=12.0, W_pos=-4.5, trunk_h=1.8, trunk_r=0.14, crown_r=1.6,
    crown_color=[0.35, 0.60, 0.24, 1.0],
    note="Poz. 1: Liriodendron tulipifera 'Edward Gursztyn' — tulipanowiec amerykański."
)

# 4. Sosna drobnokwiatowa 'Schon's Bonsai'
add_tree(
    "OGROD_SOSNA_BONSAI", L_pos=31.0, W_pos=-4.2, trunk_h=1.1, trunk_r=0.10, crown_r=0.9,
    crown_color=[0.18, 0.36, 0.18, 1.0], shape="bonsai",
    note="Poz. 7: Pinus parviflora 'Schon's Bonsai' — sosna drobnokwiatowa formowana niwaki."
)

# 5. Świdośliwa Lamarcka
add_tree(
    "OGROD_SWIDOSLIWA", L_pos=41.5, W_pos=-4.2, trunk_h=1.5, trunk_r=0.10, crown_r=1.5,
    crown_color=[0.38, 0.55, 0.25, 1.0],
    note="Poz. 3: Amelanchier lamarckii — świdośliwa Lamarcka."
)

# 6. Sosny czarne 'Green Tower'
c_conifer_dark = [0.16, 0.32, 0.16, 1.0]
for idx, (l_p, w_p) in enumerate([(9.0, -4.8), (16.0, -4.8), (42.0, 1.5), (44.5, 1.5)]):
    add_tree(
        f"OGROD_SOSNA_CZARNA_{idx+1}", L_pos=l_p, W_pos=w_p, trunk_h=0.4, trunk_r=0.08,
        crown_r=0.6, crown_color=c_conifer_dark, shape="cone", crown_h=3.8,
        note="Poz. 8: Pinus nigra 'Green Tower' — sosna czarna kolumnowa."
    )

# 7. Sosny leśne w strefie tylnej (12 sztuk w meandrze, 100% na działce 4/13)
c_pine = [0.20, 0.38, 0.18, 1.0]
forest_trees = [
    (80.0, -3.8), (82.5, -2.5), (85.0, -4.0), (88.0, -3.2), (90.5, -4.2), (92.0, -3.0),
    (80.5, 4.5), (83.5, 3.8), (86.5, 5.0), (89.5, 4.2), (91.5, 5.2), (92.5, 2.0)
]
for idx, (l_p, w_p) in enumerate(forest_trees):
    add_tree(
        f"OGROD_DRZEWO_LESNE_{idx+1}", L_pos=l_p, W_pos=w_p, trunk_h=1.8, trunk_r=0.13,
        crown_r=1.5, crown_color=c_pine,
        note=f"Strefa leśna R1: drzewo {idx+1}/12 w meandrze krajobrazowym."
    )

# 8. Żywopłot z Żywotnika 'Smaragd' wzdłuż obu granic działki
c_hedge = [0.18, 0.44, 0.18, 1.0]

# Żywopłot zachodni (wzdłuż granicy W = -6.24 m, odsunięty o 0.54m w głąb działki)
for step, l_p in enumerate(np.arange(2.0, 78.0, 0.85)):
    w_fence = -5.70
    pt2d = p_stairs + l_p * u_len + w_fence * u_wid
    r = 0.38
    sample_zs = [get_terrain_z(pt2d[0] + r * math.cos(a), pt2d[1] + r * math.sin(a)) for a in np.linspace(0, 2*math.pi, 8)]
    base_z = max(sample_zs) + 0.05
    pt = [round(float(pt2d[0]), 4), round(float(pt2d[1]), 4), round(float(base_z), 4)]
    new_parts.append(make_cone(
        f"OGROD_SMARAGD_ZACH_{step+1}", "ogrod_rosliny", c_hedge,
        p_base=pt, height=2.20, radius=r, segments=7,
        note="Poz. 5/6: Thuja occidentalis 'Smaragd' — żywopłot osłonowy granicy zachodniej."
    ))

# Żywopłot wschodni (wzdłuż wschodniej granicy działki 4/13)
for step, l_p in enumerate(np.arange(2.0, 78.0, 0.85)):
    w_fence = get_east_fence_w(l_p) - 0.52
    pt2d = p_stairs + l_p * u_len + w_fence * u_wid
    r = 0.38
    sample_zs = [get_terrain_z(pt2d[0] + r * math.cos(a), pt2d[1] + r * math.sin(a)) for a in np.linspace(0, 2*math.pi, 8)]
    base_z = max(sample_zs) + 0.05
    pt = [round(float(pt2d[0]), 4), round(float(pt2d[1]), 4), round(float(base_z), 4)]
    new_parts.append(make_cone(
        f"OGROD_SMARAGD_WSCH_{step+1}", "ogrod_rosliny", c_hedge,
        p_base=pt, height=2.20, radius=r, segments=7,
        note="Poz. 5/6: Thuja occidentalis 'Smaragd' — żywopłot osłonowy granicy wschodniej."
    ))

# 9. Formowane kule: Żywotnik 'Danica' i Cis pospolity
c_topiary = [0.22, 0.48, 0.20, 1.0]
topiary_locs = [
    (1.0, 1.5), (3.0, 1.5), (5.0, 1.5), (7.0, 1.5),
    (24.5, -2.1), (24.5, 1.5), (35.5, -2.1), (35.5, 1.5),
    (38.0, 2.5), (40.0, 2.5), (53.0, -3.5), (53.0, 0.5)
]
for idx, (l_p, w_p) in enumerate(topiary_locs):
    pt = to_3d(l_p, w_p, 0.08 + 0.35)
    new_parts.append(make_sphere(
        f"OGROD_KULA_TOPIARY_{idx+1}", "ogrod_rosliny", c_topiary,
        center=pt, radius=0.35, segments=8, rings=5,
        note="Poz. 9/10: Thuja occidentalis 'Danica' / Cis w formie kuli (Taxus sp.)."
    ))

# 10. Hortensje kwitnące 'Strong Annabelle' / 'Skyfall'
c_hydrangea_white = [0.95, 0.95, 0.90, 1.0]
c_hydrangea_leaf = [0.28, 0.56, 0.24, 1.0]
hydrangea_locs = [
    (25.0, -2.2), (25.0, -1.2), (25.0, 0.1),
    (35.2, -2.2), (35.2, -1.2), (35.2, 0.1),
    (2.0, -2.5), (4.0, -2.5), (6.0, -2.5)
]
for idx, (l_p, w_p) in enumerate(hydrangea_locs):
    pt = to_3d(l_p, w_p, 0.08 + 0.45)
    new_parts.append(make_sphere(
        f"OGROD_HORTENSJA_LISCIE_{idx+1}", "ogrod_rosliny", c_hydrangea_leaf,
        center=pt, radius=0.45, segments=8, rings=4,
        note="Poz. 11/12: Hydrangea arborescens 'Strong Anabelle' — liście krzewu."
    ))
    new_parts.append(make_sphere(
        f"OGROD_HORTENSJA_KWIAT_{idx+1}", "ogrod_rosliny", c_hydrangea_white,
        center=[pt[0], pt[1], pt[2] + 0.35], radius=0.32, segments=8, rings=4,
        note="Poz. 11/12: Hydrangea 'Strong Anabelle' — kremowo-białe kwiatostany kuliste."
    ))

# 11. Trawy ozdobne
c_grass_plume = [0.76, 0.70, 0.42, 1.0]
grass_locs = [
    (10.0, 0.8), (12.0, 0.8), (14.0, 0.8), (16.0, 0.8),
    (22.0, -2.5), (22.0, -1.5), (37.0, -2.5), (37.0, -1.5),
    (48.0, 0.5), (50.0, 0.5), (52.0, 0.5)
]
for idx, (l_p, w_p) in enumerate(grass_locs):
    pt2d = p_stairs + l_p * u_len + w_p * u_wid
    r = 0.40
    sample_zs = [get_terrain_z(pt2d[0] + r * math.cos(a), pt2d[1] + r * math.sin(a)) for a in np.linspace(0, 2*math.pi, 8)]
    base_z = max(sample_zs) + 0.05
    pt = [round(float(pt2d[0]), 4), round(float(pt2d[1]), 4), round(float(base_z), 4)]
    new_parts.append(make_cone(
        f"OGROD_TRAWA_PLUME_{idx+1}", "ogrod_rosliny", c_grass_plume,
        p_base=pt, height=1.35, radius=r, segments=7,
        note="Poz. 13/14/16: Trawy ozdobne (Calamagrostis / Rozplenica / Stipa)."
    ))

# 12. Lawenda wąskolistna 'Hidcote'
c_lavender = [0.46, 0.36, 0.66, 1.0]
for idx in range(8):
    l_p = 1.0 + idx * 0.8
    pt = to_3d(l_p, -1.8, 0.08 + 0.22)
    new_parts.append(make_sphere(
        f"OGROD_LAWENDA_{idx+1}", "ogrod_rosliny", c_lavender,
        center=pt, radius=0.22, segments=7, rings=4,
        note="Poz. 19: Lavandula angustifolia 'Hidcote' — lawenda wąskolistna."
    ))

# ==============================================================================
# WARSTWA 4: OGRÓD - OŚWIETLENIE OGRODOWE 3D
# ==============================================================================
c_pirron_post = [0.20, 0.22, 0.24, 1.0]
c_pirron_glow = [1.00, 0.94, 0.78, 1.0]

# 15 Lamp cokołowych LED Pirron
pirron_locs = [
    (2.0, 1.1), (5.5, 1.1), (9.0, 1.1), (13.0, 1.1), (17.0, 1.1),
    (22.5, -2.2), (24.5, 1.8), (35.0, -2.2), (35.0, 1.8),
    (41.0, 1.2), (46.5, 1.2), (52.0, 1.2),
    (54.0, -4.8), (66.0, -4.8), (78.0, -4.8)
]
for idx, (l_p, w_p) in enumerate(pirron_locs):
    pt = to_3d(l_p, w_p, 0.08)
    new_parts.append(make_cylinder(
        f"OGROD_LAMPA_PIRRON_SLUPEK_{idx+1}", "ogrod_oswietlenie", c_pirron_post,
        p_base=pt, p_top=[pt[0], pt[1], pt[2] + 0.60], radius=0.06, segments=6,
        note=f"Lucande lampa cokołowa LED Pirron {idx+1}/15 (słupek antracytowy wys. 60 cm)."
    ))
    new_parts.append(make_sphere(
        f"OGROD_LAMPA_PIRRON_LED_{idx+1}", "ogrod_oswietlenie", c_pirron_glow,
        center=[pt[0], pt[1], pt[2] + 0.58], radius=0.05, segments=6, rings=4,
        note=f"Ciepłe źródło światła LED lampy Pirron {idx+1}."
    ))

# 6 Reflektorów gruntowych podświetlających solitery
for idx, (l_p, w_p) in enumerate([(1.2, 2.0), (13.5, -1.2), (30.5, -4.0), (11.5, -4.2), (81.0, -3.5), (84.0, 3.5)]):
    pt = to_3d(l_p, w_p, 0.08)
    new_parts.append(make_cylinder(
        f"OGROD_REFLEKTOR_PODSTAWA_{idx+1}", "ogrod_oswietlenie", [0.15, 0.15, 0.18, 1.0],
        p_base=pt, p_top=[pt[0], pt[1], pt[2] + 0.12], radius=0.09, segments=6,
        note=f"Reflektor podświetlający rośliny {idx+1}/6 (obudowa wodoszczelna IP67)."
    ))
    new_parts.append(make_sphere(
        f"OGROD_REFLEKTOR_SOCZEWKA_{idx+1}", "ogrod_oswietlenie", [1.00, 0.96, 0.85, 1.0],
        center=[pt[0], pt[1], pt[2] + 0.14], radius=0.08, segments=6, rings=4,
        note=f"Soczewka reflektora podświetlającego drzewo/soliter {idx+1}."
    ))

# Weryfikacja: sprawdzamy czy 100% wygenerowanych elementów leży w granicach działki 4/13
parcel_lw_pts = [
    (94.51, 7.91),
    (95.01, -6.24),
    (-41.43, -6.25),
    (-41.37, 3.03),
    (-41.32, 9.04),
    (-68.02, 9.35),
    (-53.16, 13.30),
    (-38.99, 13.02),
    (-9.00, 13.30),
    (10.57, 8.93),
    (94.51, 7.91)
]
parcel_poly = Polygon(parcel_lw_pts).buffer(0.05) # bufor numeryczny 5cm

out_of_bounds = []
for p in new_parts:
    pts = np.array(p["positions_m"])[:, :2]
    lws = [((pt - p_stairs) @ u_len, (pt - p_stairs) @ u_wid) for pt in pts]
    for l, w in lws:
        if not parcel_poly.contains(Point(l, w)):
            out_of_bounds.append((p["name"], l, w))
            break

if out_of_bounds:
    print(f"OSTRZEŻENIE: {len(out_of_bounds)} elementów poza działką:")
    for name, l, w in out_of_bounds[:10]:
        print(f"  {name} at L={l:.2f}, W={w:.2f}")
else:
    print("WERYFIKACJA SUKCES: 100% elementów ogrodu leży idealnie w granicach działki 4/13!")

# Dołączenie nowych części do sceny
print(f"Wygenerowano {len(new_parts)} elementów ogrodu 3D.")
scena["parts"].extend(new_parts)

# Zapisanie zaktualizowanej sceny
scena_file.write_text(json.dumps(scena, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Zapisano {len(scena['parts'])} obiektów w scena_modelu.json.")
