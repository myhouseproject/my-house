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
from project_config import load_garden_model
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

# 3. Układ współrzędnych ogrodu (PZT survey grid) — dane z YAML.
GARDEN = load_garden_model()
FRAME = GARDEN["coordinate_frame"]
PALETTE = GARDEN["palette"]
p_stairs = np.array(FRAME["origin_m"], dtype=float)
u_len = np.array(FRAME["length_axis"], dtype=float)   # wzdłuż działki ku tyłowi
u_wid = np.array(FRAME["width_axis"], dtype=float)    # w poprzek w prawo
DEFAULT_SOURCE = GARDEN["source"]["label"]

def to_3d(L: float, W: float, z_offset: float = 0.0) -> list[float]:
    """Przelicza współrzędne ogrodu (L, W w metrach) na współrzędne modelu 3D (X, Y, Z)."""
    pt2d = p_stairs + L * u_len + W * u_wid
    z = get_terrain_z(pt2d[0], pt2d[1]) + z_offset
    return [round(float(pt2d[0]), 4), round(float(pt2d[1]), 4), round(float(z), 4)]

def coord_fn(L: float, W: float, z_offset: float = 0.0) -> list[float]:
    return to_3d(L, W, z_offset)

def get_east_fence_w(L: float) -> float:
    """Interpoluje deklaratywny profil wschodniej granicy działki 4/13."""
    points = GARDEN["parcel"]["east_fence_profile_lw"]
    if L <= points[1]["l"]:
        a, b = points[0], points[1]
    else:
        a, b = points[1], points[2]
    t = (L - a["l"]) / (b["l"] - a["l"])
    return float(a["w"] + t * (b["w"] - a["w"]))

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
# DEKLARATYWNA RECEPTURA OGRODU
# Python interpretuje parametry z modules/07_garden/model.yaml i dopasowuje Z do NMT.
# ==============================================================================
RECIPE = GARDEN["recipe"]

# Warstwa granicy działki — geometria XY i parametry renderowania z YAML.
parcel_cfg = RECIPE["parcel_render"]
width = float(parcel_cfg["width_m"])
step_m = float(parcel_cfg["step_m"])
parcel_z_offset = float(parcel_cfg["z_offset_m"])

scena["parts"] = [
    p for p in scena["parts"]
    if not p.get("name", "").startswith("OGROD_")
    and p.get("category") != "granica_dzialki"
]

for segment in parcel_cfg["segments"]:
    name = segment["name"]
    p0 = np.array(segment["p0"], dtype=float)
    p1 = np.array(segment["p1"], dtype=float)
    d = p1 - p0
    length = float(np.linalg.norm(d))
    perp = np.array([-d[1], d[0]]) / length * (width / 2.0)
    num_steps = max(1, int(math.ceil(length / step_m)))
    verts, faces = [], []
    for s in range(num_steps + 1):
        t = s / num_steps
        pt = p0 + t * d
        left, right = pt - perp, pt + perp
        z_left = get_terrain_z(left[0], left[1]) + parcel_z_offset
        z_right = get_terrain_z(right[0], right[1]) + parcel_z_offset
        idx = len(verts)
        verts.append([round(float(left[0]), 4), round(float(left[1]), 4), round(float(z_left), 4)])
        verts.append([round(float(right[0]), 4), round(float(right[1]), 4), round(float(z_right), 4)])
        if s > 0:
            pl, pr = idx - 2, idx - 1
            faces.append([pl, pr, idx + 1])
            faces.append([pl, idx + 1, idx])
    scena["parts"].append({
        "name": name,
        "category": "granica_dzialki",
        "material": "granica_dzialki",
        "color": PALETTE["parcel_boundary"],
        "source": parcel_cfg["source"],
        "source_id": parcel_cfg["source_id"],
        "assumed": False,
        "note": parcel_cfg["note"],
        "positions_m": verts,
        "faces": faces,
        "reference_area_m2": round(length * width, 4),
    })

print("Zaktualizowano warstwę granicy działki do NMT.")
new_parts = []

# Nawierzchnie opisane jako prostokątne siatki L/W.
for item in RECIPE["surfaces"]:
    l0, l1, ln = item["l"]
    w0, w1, wn = item["w"]
    new_parts.append(make_terrain_grid(
        item["name"], "ogrod_nawierzchnie", PALETTE[item["color"]],
        np.linspace(l0, l1, int(ln)), np.linspace(w0, w1, int(wn)),
        coord_fn, z_base_offset=float(item["z_offset"]), height=float(item["height"]),
        note=item["note"],
    ))

# Płyty kwarcytowe w leśnym meandrze.
stones = RECIPE["meander_stones"]
stone_l, stone_w = map(float, stones["size"])
for idx, (l_pt, w_pt) in enumerate(stones["points"]):
    new_parts.append(make_garden_box(
        f"OGROD_KWARCYT_{idx+1:02d}", "ogrod_nawierzchnie", PALETTE[stones["color"]],
        L_center=l_pt, W_center=w_pt, L_len=stone_l, W_len=stone_w,
        height=float(stones["height"]), z_base_offset=float(stones["z_offset"]),
        note=f"Ścieżka: Płyta Kwarcytowa Trawnikowa {idx+1}/{len(stones['points'])} (pow. 4 m²).",
    ))

# Modułowe płyty Grosseto.
tile = RECIPE["paver_tile"]
tile_l, tile_w = map(float, tile["size"])
for path_cfg in RECIPE["paver_paths"]:
    for col, w_pos in enumerate(path_cfg["w"]):
        for row in range(int(path_cfg["rows"])):
            l_pos = float(path_cfg["l_start"]) + row * float(path_cfg["l_step"])
            new_parts.append(make_garden_box(
                f"OGROD_GROSSETO_{path_cfg['key']}_{col}_{row}", "ogrod_nawierzchnie",
                PALETTE[tile["color"]], L_center=l_pos, W_center=w_pos,
                L_len=tile_l, W_len=tile_w, height=float(tile["height"]),
                z_base_offset=float(tile["z_offset"]), note=path_cfg["note"],
            ))

# Element o stałej rzędnej (np. taras basenowy) w lokalnym układzie L/W.
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
    for l, w in corners:
        p = p_stairs + l * u_len + w * u_wid
        verts.append([round(float(p[0]), 4), round(float(p[1]), 4), round(float(z_bot), 4)])
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
        "name": name, "category": category, "material": category, "color": color,
        "positions_m": verts, "faces": faces, "geometry": "solid",
        "source": DEFAULT_SOURCE, "note": note, "default_visible": True, "geoportal_real": True,
    }

pool = RECIPE["pool"]
Z_TERRACE = float(pool["terrace_z"])
H_SLAB = float(pool["slab_height"])
Z_POOL_DNO = Z_TERRACE - float(pool["depth"])

for item in pool["beach"]:
    l0, l1, w0, w1 = map(float, item["bounds"])
    new_parts.append(make_level_box(
        item["name"], "ogrod_nawierzchnie", PALETTE["gres"],
        l0, l1, w0, w1, Z_TERRACE, Z_TERRACE - H_SLAB, item["note"],
    ))

# Cokoły oporowe tarasu basenowego; dolna krawędź podąża za NMT.
for item in pool["retaining_walls"]:
    values = np.linspace(float(item["start"]), float(item["end"]), int(item["count"]))
    if item["axis"] == "w":
        points = [p_stairs + float(item["fixed"]) * u_len + v * u_wid for v in values]
    else:
        points = [p_stairs + v * u_len + float(item["fixed"]) * u_wid for v in values]
    verts, faces = [], []
    for idx, pt in enumerate(points):
        tz = get_terrain_z(pt[0], pt[1]) - H_SLAB
        v_idx = len(verts)
        verts.append([round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(tz), 4)])
        verts.append([round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(Z_TERRACE), 4)])
        if idx > 0:
            p_bot, p_top = v_idx - 2, v_idx - 1
            if item["flip"]:
                faces.append([p_bot, p_top, v_idx + 1])
                faces.append([p_bot, v_idx + 1, v_idx])
            else:
                faces.append([p_bot, v_idx + 1, p_top])
                faces.append([p_bot, v_idx, v_idx + 1])
    new_parts.append({
        "name": item["name"], "category": "ogrod_nawierzchnie", "material": "ogrod_nawierzchnie",
        "color": PALETTE["cokol"], "positions_m": verts, "faces": faces, "geometry": "solid",
        "source": DEFAULT_SOURCE, "note": item["note"], "default_visible": True, "geoportal_real": True,
    })

for item in pool["shell_parts"]:
    l0, l1, w0, w1 = map(float, item["bounds"])
    if "top_rel_bottom" in item:
        top = Z_POOL_DNO + float(item["top_rel_bottom"])
    else:
        top = Z_TERRACE + float(item.get("top_rel_terrace", 0.0))
    bot = Z_POOL_DNO + float(item.get("bot_rel_bottom", 0.0))
    new_parts.append(make_level_box(
        item["name"], "ogrod_woda", PALETTE["pool_shell"],
        l0, l1, w0, w1, top, bot, item["note"],
    ))

water = pool["water"]
l0, l1, w0, w1 = map(float, water["bounds"])
new_parts.append(make_level_box(
    water["name"], "ogrod_woda", PALETTE["water"], l0, l1, w0, w1,
    Z_TERRACE + float(water["top_rel_terrace"]),
    Z_TERRACE + float(water["bot_rel_terrace"]), water["note"],
))

for item in pool["rim"]:
    l0, l1, w0, w1 = map(float, item["bounds"])
    new_parts.append(make_level_box(
        item["name"], "ogrod_nawierzchnie", PALETTE["rim"], l0, l1, w0, w1,
        Z_TERRACE + float(pool["rim_top_rel"]), Z_TERRACE, "Obrzeże przelewowe basenu.",
    ))

loungers = pool["loungers"]
for idx, w_pos in enumerate(loungers["w"]):
    fl0, fl1 = loungers["frame_bounds_l"]
    pl0, pl1 = loungers["pad_bounds_l"]
    fw = float(loungers["frame_half_w"]); pw = float(loungers["pad_half_w"])
    new_parts.append(make_level_box(
        f"OGROD_LEZAK_RAMA_{idx+1}", "ogrod_architektura", PALETTE["lounger_frame"],
        fl0, fl1, w_pos-fw, w_pos+fw, Z_TERRACE+float(loungers["frame_top_rel"]), Z_TERRACE,
        f"Leżak basenowy {idx+1} z ramą antracytową.",
    ))
    new_parts.append(make_level_box(
        f"OGROD_LEZAK_MATERAC_{idx+1}", "ogrod_architektura", PALETTE["lounger_pad"],
        pl0, pl1, w_pos-pw, w_pos+pw, Z_TERRACE+float(loungers["pad_top_rel"]),
        Z_TERRACE+float(loungers["pad_bottom_rel"]), f"Materac leżaka basenowego {idx+1}.",
    ))

table = pool["table"]
l0, l1, w0, w1 = map(float, table["bounds"])
new_parts.append(make_level_box(
    "OGROD_STOL_TARAS", "ogrod_architektura", PALETTE["table"], l0, l1, w0, w1,
    Z_TERRACE+float(table["top_rel"]), Z_TERRACE, "Stół ogrodowy obiadowy na tarasie basenowym.",
))
chairs = pool["chairs"]; base_l, base_w = map(float, chairs["base"]); half = float(chairs["half_size"])
for idx, (dl, dw) in enumerate(chairs["offsets"]):
    cl, cw = base_l + dl, base_w + dw
    new_parts.append(make_level_box(
        f"OGROD_KRZESLO_{idx+1}", "ogrod_architektura", PALETTE["lounger_frame"],
        cl-half, cl+half, cw-half, cw+half, Z_TERRACE+float(chairs["top_rel"]), Z_TERRACE,
        f"Krzesło ogrodowe {idx+1}.",
    ))

# Mała architektura opisana prostymi boxami.
arch = RECIPE["architecture"]
for item in arch["boxes"]:
    new_parts.append(make_garden_box(
        item["name"], "ogrod_architektura", PALETTE[item["color"]],
        L_center=item["center"][0], W_center=item["center"][1],
        L_len=item["size"][0], W_len=item["size"][1],
        height=item["height"], z_base_offset=item["z_offset"], note=item["note"],
    ))

beds = arch["raised_beds"]
for idx, (l_pos, w_pos) in enumerate(beds["centers"]):
    for key, prefix, color, note in (
        ("frame", "OGROD_SKRZYNIA_RAMA", "box_wood", f"Skrzynia na warzywa {idx+1}/4: drewno impregnowane 180×90 cm, wys. 60 cm."),
        ("soil", "OGROD_SKRZYNIA_ZIEMIA", "soil", f"Podłoże próchnicze w skrzyni warzywnej {idx+1}."),
        ("crops", "OGROD_SKRZYNIA_WARZYWA", "crops", f"Uprawy ziół i warzyw w skrzyni {idx+1}."),
    ):
        cfg = beds[key]
        new_parts.append(make_garden_box(
            f"{prefix}_{idx+1}", "ogrod_architektura", PALETTE[color],
            L_center=l_pos, W_center=w_pos, L_len=cfg["size"][0], W_len=cfg["size"][1],
            height=cfg["height"], z_base_offset=cfg["z_offset"], note=note,
        ))

tramp = arch["trampoline"]
tc_l, tc_w = map(float, tramp["center"])
pt2d_tramp = p_stairs + tc_l * u_len + tc_w * u_wid
sample_zs = [
    get_terrain_z(
        pt2d_tramp[0] + float(tramp["sample_radius"]) * math.cos(a),
        pt2d_tramp[1] + float(tramp["sample_radius"]) * math.sin(a),
    )
    for a in np.linspace(0, 2*math.pi, int(tramp["sample_count"]))
]
base_z = max(sample_zs) + float(tramp["base_offset"])
pt_tramp = [round(float(pt2d_tramp[0]),4), round(float(pt2d_tramp[1]),4), round(float(base_z),4)]
mat_h=float(tramp["mat_height"]); rim_h=float(tramp["rim_height"])
new_parts.append(make_cylinder(
    "OGROD_TRAMPOLINA_MATA", "ogrod_architektura", PALETTE["tramp_mat"],
    p_base=pt_tramp, p_top=[pt_tramp[0],pt_tramp[1],pt_tramp[2]+mat_h],
    radius=float(tramp["mat_radius"]), segments=int(tramp["segments"]),
    note="Mata elastyczna trampoliny ogrodowej wpuszczanej w grunt.",
))
new_parts.append(make_cylinder(
    "OGROD_TRAMPOLINA_KRAWEDZ", "ogrod_architektura", PALETTE["tramp_rim"],
    p_base=[pt_tramp[0],pt_tramp[1],pt_tramp[2]+mat_h],
    p_top=[pt_tramp[0],pt_tramp[1],pt_tramp[2]+mat_h+rim_h],
    radius=float(tramp["rim_radius"]), segments=int(tramp["segments"]),
    note="Kołnierz ochronny trampoliny ogrodowej.",
))

# Wyposażenie sportowe.
sports = RECIPE["sports"]
volley=sports["volleyball"]
for idx,w_pos in enumerate(volley["pole_w"],1):
    p = to_3d(volley["l"], w_pos, volley["z_offset"])
    new_parts.append(make_cylinder(
        f"OGROD_SIATKA_SLUPEK_{idx}", "ogrod_architektura", PALETTE["pole"],
        p_base=p, p_top=[p[0],p[1],p[2]+float(volley["pole_height"])],
        radius=float(volley["pole_radius"]), segments=int(volley["segments"]),
        note="Słupek siatki do siatkówki (stal ocynkowana).",
    ))
new_parts.append(make_garden_box(
    "OGROD_SIATKA_POWIERZCHNIA", "ogrod_architektura", PALETTE["net"],
    L_center=volley["l"], W_center=volley["net_center_w"],
    L_len=volley["net_size"][0], W_len=volley["net_size"][1],
    height=volley["net_height"], z_base_offset=volley["net_z_offset"],
    note="Siatka do siatkówki zawieszona na wysokości 2,43 m.",
))

football=sports["football"]
for idx,w_pos in enumerate(football["pole_w"]):
    suffix="L" if idx==0 else "P"
    p=to_3d(football["l"],w_pos,football["z_offset"])
    new_parts.append(make_cylinder(
        f"OGROD_BRAMKA_SLUPEK_{suffix}", "ogrod_architektura", PALETTE["goal"],
        p_base=p,p_top=[p[0],p[1],p[2]+float(football["pole_height"])],
        radius=float(football["pole_radius"]),segments=int(football["segments"]),
        note=f"Słupek {'lewy' if idx==0 else 'prawy'} bramki do piłki nożnej (3×2 m).",
    ))
new_parts.append(make_garden_box(
    "OGROD_BRAMKA_POPRZECZKA","ogrod_architektura",PALETTE["goal"],
    L_center=football["crossbar_center"][0],W_center=football["crossbar_center"][1],
    L_len=football["crossbar_size"][0],W_len=football["crossbar_size"][1],
    height=football["crossbar_height"],z_base_offset=football["crossbar_z"],
    note="Poprzeczka bramki piłkarskiej.",
))
new_parts.append(make_garden_box(
    "OGROD_BRAMKA_SIATKA","ogrod_architektura",PALETTE["net"],
    L_center=football["net_center"][0],W_center=football["net_center"][1],
    L_len=football["net_size"][0],W_len=football["net_size"][1],
    height=football["net_height"],z_base_offset=football["net_z"],
    note="Siatka bramki piłkarskiej.",
))

basket=sports["basketball"]
p=to_3d(basket["post"][0],basket["post"][1],basket["z_offset"])
new_parts.append(make_cylinder(
    "OGROD_KOSZ_SLUP","ogrod_architektura",PALETTE["basketball_post"],
    p_base=p,p_top=[p[0],p[1],p[2]+float(basket["post_height"])],
    radius=float(basket["post_radius"]),segments=int(basket["segments"]),
    note="Słup stalowy kosza do koszykówki.",
))
new_parts.append(make_garden_box(
    "OGROD_KOSZ_TABLICA","ogrod_architektura",PALETTE["basketball_board"],
    L_center=basket["board_center"][0],W_center=basket["board_center"][1],
    L_len=basket["board_size"][0],W_len=basket["board_size"][1],
    height=basket["board_height"],z_base_offset=basket["board_z"],
    note="Tablica do koszykówki z plexiglasu 180×105 cm.",
))
new_parts.append(make_garden_box(
    "OGROD_KOSZ_OBRECZ","ogrod_architektura",PALETTE["basketball_rim"],
    L_center=basket["rim_center"][0],W_center=basket["rim_center"][1],
    L_len=basket["rim_size"][0],W_len=basket["rim_size"][1],
    height=basket["rim_height"],z_base_offset=basket["rim_z"],
    note="Obręcz kosza z siatką na przepisowej wysokości 3,05 m.",
))

# Rośliny.
planting=RECIPE["planting"]
def add_tree(name, L_pos, W_pos, trunk_h, trunk_r, crown_r, crown_color,
             shape="sphere", crown_h=3.0, note=""):
    pt2d = p_stairs + float(L_pos) * u_len + float(W_pos) * u_wid
    sample_zs = [
        get_terrain_z(pt2d[0]+float(trunk_r)*math.cos(a), pt2d[1]+float(trunk_r)*math.sin(a))
        for a in np.linspace(0,2*math.pi,8)
    ]
    base_z=max(sample_zs)+0.05
    pt_base=[round(float(pt2d[0]),4),round(float(pt2d[1]),4),round(float(base_z),4)]
    pt_top=[pt_base[0],pt_base[1],round(float(base_z+float(trunk_h)),4)]
    new_parts.append(make_cylinder(
        f"{name}_PIEN","ogrod_rosliny",PALETTE["bark"],p_base=pt_base,p_top=pt_top,
        radius=float(trunk_r),segments=8,note=f"Pień drzewa: {note}",
    ))
    if shape=="cone":
        new_parts.append(make_cone(
            f"{name}_KORONA","ogrod_rosliny",crown_color,
            p_base=[pt_base[0],pt_base[1],pt_base[2]+float(trunk_h)*0.4],
            height=float(crown_h),radius=float(crown_r),segments=10,note=note,
        ))
    elif shape=="bonsai":
        for c_idx,(dl,dw,dz,scale) in enumerate(planting["bonsai_clouds"]):
            new_parts.append(make_sphere(
                f"{name}_CHMURA_{c_idx+1}","ogrod_rosliny",crown_color,
                center=[pt_top[0]+dl,pt_top[1]+dw,pt_top[2]+dz],
                radius=float(crown_r)*float(scale),segments=8,rings=5,note=note,
            ))
    else:
        new_parts.append(make_sphere(
            f"{name}_KORONA","ogrod_rosliny",crown_color,
            center=[pt_top[0],pt_top[1],pt_top[2]+float(crown_r)*0.7],
            radius=float(crown_r),segments=8,rings=5,note=note,
        ))

for item in planting["trees"]:
    add_tree(
        item["name"],*item["pos"],item["trunk_h"],item["trunk_r"],item["crown_r"],item["color"],
        shape=item.get("shape","sphere"),crown_h=item.get("crown_h",3.0),note=item["note"],
    )

black=planting["black_pines"]
for idx,(l_pos,w_pos) in enumerate(black["positions"]):
    add_tree(
        f"OGROD_SOSNA_CZARNA_{idx+1}",l_pos,w_pos,black["trunk_h"],black["trunk_r"],
        black["crown_r"],PALETTE["conifer_dark"],shape="cone",crown_h=black["crown_h"],
        note="Poz. 8: Pinus nigra 'Green Tower' — sosna czarna kolumnowa.",
    )

forest=planting["forest_trees"]
for idx,(l_pos,w_pos) in enumerate(forest["positions"]):
    add_tree(
        f"OGROD_DRZEWO_LESNE_{idx+1}",l_pos,w_pos,forest["trunk_h"],forest["trunk_r"],
        forest["crown_r"],PALETTE["pine"],
        note=f"Strefa leśna R1: drzewo {idx+1}/{len(forest['positions'])} w meandrze krajobrazowym.",
    )

hedge=planting["hedge"]
for side in ("ZACH","WSCH"):
    for step,l_pos in enumerate(np.arange(float(hedge["l_start"]),float(hedge["l_end"]),float(hedge["l_step"]))):
        w_pos=float(hedge["west_w"]) if side=="ZACH" else get_east_fence_w(l_pos)-float(hedge["east_inset"])
        pt2d=p_stairs+l_pos*u_len+w_pos*u_wid
        radius=float(hedge["radius"])
        sample_zs=[get_terrain_z(pt2d[0]+radius*math.cos(a),pt2d[1]+radius*math.sin(a)) for a in np.linspace(0,2*math.pi,8)]
        pt=[round(float(pt2d[0]),4),round(float(pt2d[1]),4),round(float(max(sample_zs)+float(hedge["base_offset"])),4)]
        new_parts.append(make_cone(
            f"OGROD_SMARAGD_{side}_{step+1}","ogrod_rosliny",PALETTE["hedge"],
            p_base=pt,height=float(hedge["height"]),radius=radius,segments=int(hedge["segments"]),
            note=f"Poz. 5/6: Thuja occidentalis 'Smaragd' — żywopłot osłonowy granicy {'zachodniej' if side=='ZACH' else 'wschodniej'}.",
        ))

topiary=planting["topiary"]
for idx,(l_pos,w_pos) in enumerate(topiary["positions"]):
    new_parts.append(make_sphere(
        f"OGROD_KULA_TOPIARY_{idx+1}","ogrod_rosliny",PALETTE["topiary"],
        center=to_3d(l_pos,w_pos,float(topiary["z_offset"])),radius=float(topiary["radius"]),
        segments=8,rings=5,note="Poz. 9/10: Thuja occidentalis 'Danica' / Cis w formie kuli (Taxus sp.).",
    ))

hyd=planting["hydrangea"]
for idx,(l_pos,w_pos) in enumerate(hyd["positions"]):
    pt=to_3d(l_pos,w_pos,float(hyd["leaf_z_offset"]))
    new_parts.append(make_sphere(
        f"OGROD_HORTENSJA_LISCIE_{idx+1}","ogrod_rosliny",PALETTE["hydrangea_leaf"],
        center=pt,radius=float(hyd["leaf_radius"]),segments=8,rings=4,
        note="Poz. 11/12: Hydrangea arborescens 'Strong Anabelle' — liście krzewu.",
    ))
    new_parts.append(make_sphere(
        f"OGROD_HORTENSJA_KWIAT_{idx+1}","ogrod_rosliny",PALETTE["hydrangea_white"],
        center=[pt[0],pt[1],pt[2]+float(hyd["flower_z_add"])],radius=float(hyd["flower_radius"]),
        segments=8,rings=4,note="Poz. 11/12: Hydrangea 'Strong Anabelle' — kremowo-białe kwiatostany kuliste.",
    ))

grasses=planting["grasses"]
for idx,(l_pos,w_pos) in enumerate(grasses["positions"]):
    pt2d=p_stairs+l_pos*u_len+w_pos*u_wid
    radius=float(grasses["radius"])
    sample_zs=[get_terrain_z(pt2d[0]+radius*math.cos(a),pt2d[1]+radius*math.sin(a)) for a in np.linspace(0,2*math.pi,8)]
    pt=[round(float(pt2d[0]),4),round(float(pt2d[1]),4),round(float(max(sample_zs)+float(grasses["base_offset"])),4)]
    new_parts.append(make_cone(
        f"OGROD_TRAWA_PLUME_{idx+1}","ogrod_rosliny",PALETTE["grass_plume"],
        p_base=pt,height=float(grasses["height"]),radius=radius,segments=int(grasses["segments"]),
        note="Poz. 13/14/16: Trawy ozdobne (Calamagrostis / Rozplenica / Stipa).",
    ))

lav=planting["lavender"]
for idx in range(int(lav["count"])):
    l_pos=float(lav["l_start"])+idx*float(lav["l_step"])
    new_parts.append(make_sphere(
        f"OGROD_LAWENDA_{idx+1}","ogrod_rosliny",PALETTE["lavender"],
        center=to_3d(l_pos,float(lav["w"]),float(lav["z_offset"])),radius=float(lav["radius"]),
        segments=int(lav["segments"]),rings=int(lav["rings"]),
        note="Poz. 19: Lavandula angustifolia 'Hidcote' — lawenda wąskolistna.",
    ))

# Oświetlenie.
lighting=RECIPE["lighting"]
pirron=lighting["pirron"]
for idx,(l_pos,w_pos) in enumerate(pirron["positions"]):
    pt=to_3d(l_pos,w_pos,float(pirron["z_offset"]))
    new_parts.append(make_cylinder(
        f"OGROD_LAMPA_PIRRON_SLUPEK_{idx+1}","ogrod_oswietlenie",PALETTE["pirron_post"],
        p_base=pt,p_top=[pt[0],pt[1],pt[2]+float(pirron["post_height"])],
        radius=float(pirron["post_radius"]),segments=int(pirron["post_segments"]),
        note=f"Lucande lampa cokołowa LED Pirron {idx+1}/{len(pirron['positions'])} (słupek antracytowy wys. 60 cm).",
    ))
    new_parts.append(make_sphere(
        f"OGROD_LAMPA_PIRRON_LED_{idx+1}","ogrod_oswietlenie",PALETTE["pirron_glow"],
        center=[pt[0],pt[1],pt[2]+float(pirron["led_z_add"])],radius=float(pirron["led_radius"]),
        segments=int(pirron["led_segments"]),rings=int(pirron["led_rings"]),
        note=f"Ciepłe źródło światła LED lampy Pirron {idx+1}.",
    ))

spots=lighting["spotlights"]
for idx,(l_pos,w_pos) in enumerate(spots["positions"]):
    pt=to_3d(l_pos,w_pos,float(spots["z_offset"]))
    new_parts.append(make_cylinder(
        f"OGROD_REFLEKTOR_PODSTAWA_{idx+1}","ogrod_oswietlenie",PALETTE["spotlight_body"],
        p_base=pt,p_top=[pt[0],pt[1],pt[2]+float(spots["body_height"])],
        radius=float(spots["body_radius"]),segments=int(spots["segments"]),
        note=f"Reflektor podświetlający rośliny {idx+1}/{len(spots['positions'])} (obudowa wodoszczelna IP67).",
    ))
    new_parts.append(make_sphere(
        f"OGROD_REFLEKTOR_SOCZEWKA_{idx+1}","ogrod_oswietlenie",PALETTE["spotlight_lens"],
        center=[pt[0],pt[1],pt[2]+float(spots["lens_z_add"])],radius=float(spots["lens_radius"]),
        segments=int(spots["segments"]),rings=int(spots["lens_rings"]),
        note=f"Soczewka reflektora podświetlającego drzewo/soliter {idx+1}.",
    ))

# Weryfikacja granic działki z deklaratywnego wielokąta L/W.
validation=RECIPE["validation"]
parcel_poly=Polygon(validation["parcel_polygon_lw"]).buffer(float(validation["buffer_m"]))
out_of_bounds=[]
for part in new_parts:
    pts=np.array(part["positions_m"])[:,:2]
    lws=[((pt-p_stairs)@u_len,(pt-p_stairs)@u_wid) for pt in pts]
    for l_pos,w_pos in lws:
        if not parcel_poly.contains(Point(l_pos,w_pos)):
            out_of_bounds.append((part["name"],l_pos,w_pos))
            break
if out_of_bounds:
    print(f"OSTRZEŻENIE: {len(out_of_bounds)} elementów poza działką:")
    for name,l_pos,w_pos in out_of_bounds[:10]:
        print(f"  {name} at L={l_pos:.2f}, W={w_pos:.2f}")
else:
    print("WERYFIKACJA SUKCES: 100% elementów ogrodu leży idealnie w granicach działki 4/13!")

print(f"Wygenerowano {len(new_parts)} elementów ogrodu 3D.")

# Dołączenie nowych części do sceny
print(f"Wygenerowano {len(new_parts)} elementów ogrodu 3D.")
scena["parts"].extend(new_parts)

# Zapisanie zaktualizowanej sceny
scena_file.write_text(json.dumps(scena, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Zapisano {len(scena['parts'])} obiektów w scena_modelu.json.")
