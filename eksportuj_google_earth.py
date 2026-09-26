#!/usr/bin/env python3
"""
Generuje pliki KMZ i GLB dla Google Earth:
- dom_Gruszowa60.kmz (do otwarcia w Google Earth Pro / Web z pełną georeferencją na ul. Gruszowej 60 w Częstochowie)
- dom_Gruszowa60.glb (zoptymalizowany model GLB do importu w Google Earth Web)
"""
import io
import json
import math
import zipfile
from pathlib import Path
import numpy as np
import trimesh
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent

def main():
    print("Ładowanie danych modelu...")
    with open(ROOT / 'geoportal_georef.json', encoding='utf-8') as f:
        cfg = json.load(f)
    with open(ROOT / 'geoportal_teren.json', encoding='utf-8') as f:
        teren = json.load(f)
    with open(ROOT / 'dane_zrodlowe.json', encoding='utf-8') as f:
        data = json.load(f)
    with open(ROOT / 'scena_modelu.json', encoding='utf-8') as f:
        scena = json.load(f)

    # 1. Obliczenie georeferencji WGS84 dla domu
    M_pzt = np.array(teren['alignment']['house_calibration']['model_to_geo_local_affine_mm'])
    center_en = teren['alignment']['geo_context_center_epsg2180']
    GEO_CENTER_2180 = np.array(center_en, dtype=float)
    GEO_ANCHOR_MODEL_MM = np.array(cfg['fetch']['center_model_mm'], dtype=float)

    t2180_to_wgs84 = Transformer.from_crs(2180, 4326, always_xy=True)

    house_pts = np.array(data['facade_reference_outline']['polygon_mm'])
    c_model_mm = house_pts.mean(axis=0)

    # Transformacja punktu odniesienia do EPSG:2180 i WGS84
    p_geo_mm = M_pzt @ np.array([c_model_mm[0], c_model_mm[1], 1.0])
    delta_m = (p_geo_mm[:2] - GEO_ANCHOR_MODEL_MM) / 1000.0
    c_2180 = GEO_CENTER_2180 + delta_m
    lon0, lat0 = t2180_to_wgs84.transform(c_2180[0], c_2180[1])

    # Kąt obrotu osi Y modelu względem Północy
    p_model_y = c_model_mm + np.array([0.0, 10000.0])
    p_geo_y = M_pzt @ np.array([p_model_y[0], p_model_y[1], 1.0])
    delta_y_m = (p_geo_y[:2] - GEO_ANCHOR_MODEL_MM) / 1000.0
    c_2180_y = GEO_CENTER_2180 + delta_y_m
    d_east = c_2180_y[0] - c_2180[0]
    d_north = c_2180_y[1] - c_2180[1]
    heading_deg = math.degrees(math.atan2(d_east, d_north)) % 360.0

    print(f"Lokalizacja domu w WGS84: lat={lat0:.7f}, lon={lon0:.7f}")
    print(f"Obrót (heading): {heading_deg:.2f}°")

    # 2. Zebranie siatek 3D domu i ogrodu ze scena_modelu.json
    # Wybieramy wszystkie elementy domu i ogrodu (bez terenu i sąsiadów, bo w Google Earth jest już prawdziwy teren i sąsiedzi!)
    valid_categories = {
        'sciany', 'uzupelnienia', 'stolarka', 'podlogi', 'izolacja',
        'strop', 'dach', 'daszek', 'elewacja', 'nawierzchnie', 'schody',
        'ogrod_nawierzchnie', 'ogrod_woda', 'ogrod_architektura', 'ogrod_rosliny', 'ogrod_oswietlenie'
    }

    sub_meshes = []
    # Centroid domu w metrach
    cx_m = c_model_mm[0] / 1000.0
    cy_m = c_model_mm[1] / 1000.0

    for p in scena['parts']:
        cat = p.get('category', '')
        if cat not in valid_categories:
            continue
        v = np.array(p['positions_m'], dtype=float)
        f = np.array(p['faces'], dtype=int)
        if len(v) < 3 or len(f) < 1:
            continue
        
        # Centrujemy model wokół środka domu (0, 0 w punkcie odniesienia)
        v_centered = v.copy()
        v_centered[:, 0] -= cx_m
        v_centered[:, 1] -= cy_m

        color = p.get('color', [0.8, 0.8, 0.8, 1.0])
        rgba = [int(c * 255) for c in color[:4]]
        if len(rgba) == 3:
            rgba.append(255)

        m = trimesh.Trimesh(vertices=v_centered, faces=f, process=False)
        m.visual.vertex_colors = np.tile(rgba, (len(v_centered), 1))
        sub_meshes.append(m)

    print(f"Połączono {len(sub_meshes)} elementów domu i ogrodu.")
    combined = trimesh.util.concatenate(sub_meshes)

    # Zapisz GLB dla Google Earth Web
    glb_out = ROOT / 'dom_Gruszowa60.glb'
    combined.export(str(glb_out), file_type='glb')
    print(f"Zapisano {glb_out.name} ({glb_out.stat().st_size / 1024 / 1024:.2f} MB)")

    # 3. Tworzenie modelu COLLADA DAE dla KMZ
    dae_bytes = combined.export(file_type='dae')

    # Obliczenie współrzędnych obrysu domu w WGS84 dla bryły wytłaczanej (Android KML)
    house_coords_kml = []
    for p in house_pts:
        p_geo = M_pzt @ np.array([p[0], p[1], 1.0])
        delta_m = (p_geo[:2] - GEO_ANCHOR_MODEL_MM) / 1000.0
        c_2180 = GEO_CENTER_2180 + delta_m
        lon, lat = t2180_to_wgs84.transform(c_2180[0], c_2180[1])
        house_coords_kml.append(f"{lon:.7f},{lat:.7f},4.15")
    house_coords_kml.append(house_coords_kml[0])
    house_coords_str = " ".join(house_coords_kml)

    # Obliczenie współrzędnych granic działki 4/13 w WGS84 (Android KML)
    p_stairs = np.array([9.0155, -5.8961])
    u_len = np.array([-0.17676, 0.98425])
    u_wid = np.array([0.98425, 0.17676])
    parcel_pts = [(94.51, 7.91), (95.01, -6.24), (-41.43, -6.25), (-41.37, 3.03), (-9.00, 3.03), (-9.00, 13.30), (10.57, 8.93)]
    parcel_coords_kml = []
    for l, w in parcel_pts:
        xy = p_stairs + l * u_len + w * u_wid
        p_geo = M_pzt @ np.array([xy[0]*1000.0, xy[1]*1000.0, 1.0])
        delta_m = (p_geo[:2] - GEO_ANCHOR_MODEL_MM) / 1000.0
        c_2180 = GEO_CENTER_2180 + delta_m
        lon, lat = t2180_to_wgs84.transform(c_2180[0], c_2180[1])
        parcel_coords_kml.append(f"{lon:.7f},{lat:.7f},0.2")
    parcel_coords_kml.append(parcel_coords_kml[0])
    parcel_coords_str = " ".join(parcel_coords_kml)

    # Funkcja pomocnicza do konwersji części siatek 3D na poligony KML MultiGeometry
    def to_wgs84(x_m, y_m):
        p_geo = M_pzt @ np.array([x_m * 1000.0, y_m * 1000.0, 1.0])
        delta_m = (p_geo[:2] - GEO_ANCHOR_MODEL_MM) / 1000.0
        c_2180 = GEO_CENTER_2180 + delta_m
        return t2180_to_wgs84.transform(c_2180[0], c_2180[1])

    def parts_to_multi_geometry(parts, min_z_filter=None):
        polys = []
        for p in parts:
            v = np.array(p['positions_m'])
            f = np.array(p['faces'])
            v_wgs = []
            for pt in v:
                lon, lat = to_wgs84(pt[0], pt[1])
                v_wgs.append((lon, lat, pt[2]))
            for face in f:
                pts = [v_wgs[i] for i in face]
                if min_z_filter is not None and any(pt[2] < min_z_filter for pt in pts):
                    continue
                pts.append(pts[0])
                c_str = ' '.join(f'{lon:.7f},{lat:.7f},{z:.2f}' for lon, lat, z in pts)
                polys.append(f'<Polygon><altitudeMode>relativeToGround</altitudeMode><outerBoundaryIs><LinearRing><coordinates>{c_str}</coordinates></LinearRing></outerBoundaryIs></Polygon>')
        return '<MultiGeometry>' + ''.join(polys) + '</MultiGeometry>'

    roof_mg = parts_to_multi_geometry([p for p in scena['parts'] if p.get('category') in ['dach', 'daszek']])
    win_mg = parts_to_multi_geometry([p for p in scena['parts'] if p.get('category') == 'stolarka'])
    pool_mg = parts_to_multi_geometry([p for p in scena['parts'] if p.get('category') == 'ogrod_woda'])

    # 4. Tworzenie pliku KML kompatybilnego z Google Earth Android oraz Google Earth Pro
    kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Dom i Ogród Kōyō · Częstochowa, ul. Gruszowa 60</name>
    <open>1</open>
    <description>Projekt domu jednorodzinnego i ogrodu Kōyō na działce 4/13 przy ul. Gruszowej 60 w Częstochowie (Kiedrzyn).</description>

    <!-- Styl ścian budynku (100% kryjący, jasny tynk) -->
    <Style id="houseExtrudeStyle">
      <LineStyle>
        <color>ff3a4b53</color>
        <width>2.0</width>
      </LineStyle>
      <PolyStyle>
        <color>ffeef3f6</color>
        <fill>1</fill>
        <outline>1</outline>
      </PolyStyle>
    </Style>

    <!-- Styl dachu i attyki (grafitowy, ciemnoszary dach kryjący) -->
    <Style id="roofStyle">
      <LineStyle>
        <color>ff1a1d20</color>
        <width>1.2</width>
      </LineStyle>
      <PolyStyle>
        <color>ff2d3238</color>
        <fill>1</fill>
        <outline>1</outline>
      </PolyStyle>
    </Style>

    <!-- Styl stolarki okiennej i przeszkleń (szkło) -->
    <Style id="windowStyle">
      <LineStyle>
        <color>ff251b12</color>
        <width>1.0</width>
      </LineStyle>
      <PolyStyle>
        <color>ffd59840</color>
        <fill>1</fill>
        <outline>1</outline>
      </PolyStyle>
    </Style>

    <!-- Styl basenu ogrodowego (błękitna woda) -->
    <Style id="poolStyle">
      <LineStyle>
        <color>ff996010</color>
        <width>1.5</width>
      </LineStyle>
      <PolyStyle>
        <color>ffdb941f</color>
        <fill>1</fill>
        <outline>1</outline>
      </PolyStyle>
    </Style>

    <!-- Styl granicy działki 4/13 -->
    <Style id="parcelStyle">
      <LineStyle>
        <color>ff1020e0</color>
        <width>3.5</width>
      </LineStyle>
      <PolyStyle>
        <color>151020e0</color>
      </PolyStyle>
    </Style>

    <!-- Pinezka adresowa -->
    <Placemark>
      <name>📍 Częstochowa, ul. Gruszowa 60 (dz. 4/13)</name>
      <description><![CDATA[
        <h3>Dom jednorodzinny i ogród Kōyō</h3>
        <p><b>Adres:</b> Częstochowa, ul. Gruszowa 60</p>
        <p><b>Działka:</b> 4/13, obręb 0430 Kiedrzyn</p>
        <p><b>Wymiary domu:</b> 28,30 m × 11,92 m, attyka H = 4,15 m</p>
      ]]></description>
      <Point>
        <coordinates>{lon0:.7f},{lat0:.7f},0</coordinates>
      </Point>
    </Placemark>

    <!-- Granica działki 4/13 (widoczna na telefonie Android) -->
    <Placemark>
      <name>Granica działki 4/13 EGiB</name>
      <styleUrl>#parcelStyle</styleUrl>
      <Polygon>
        <tessellate>1</tessellate>
        <altitudeMode>clampToGround</altitudeMode>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>{parcel_coords_str}</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>

    <!-- Ściany budynku - pełna, kryjąca bryła tynkowana (widoczna na Androidzie) -->
    <Placemark>
      <name>Ściany budynku (elewacja H = 4.15 m)</name>
      <styleUrl>#houseExtrudeStyle</styleUrl>
      <Polygon>
        <extrude>1</extrude>
        <altitudeMode>relativeToGround</altitudeMode>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>{house_coords_str}</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>

    <!-- Grafitowy dach płaski i attyka (widoczny na Androidzie) -->
    <Placemark>
      <name>Dach i attyka (grafit)</name>
      <styleUrl>#roofStyle</styleUrl>
      {roof_mg}
    </Placemark>

    <!-- Stolarka okienna i przeszklenia (widoczna na Androidzie) -->
    <Placemark>
      <name>Stolarka okienna i przeszklenia</name>
      <styleUrl>#windowStyle</styleUrl>
      {win_mg}
    </Placemark>

    <!-- Basen ogrodowy (widoczny na Androidzie) -->
    <Placemark>
      <name>Basen Polystone (woda)</name>
      <styleUrl>#poolStyle</styleUrl>
      {pool_mg}
    </Placemark>

    <!-- Pełny model 3D z fotorealistyczną siatką COLLADA (Google Earth Pro / Desktop) -->
    <Placemark>
      <name>Model 3D domu i ogrodu Kōyō (COLLADA)</name>
      <Model id="dom_koyo">
        <altitudeMode>clampToGround</altitudeMode>
        <Location>
          <longitude>{lon0:.7f}</longitude>
          <latitude>{lat0:.7f}</latitude>
          <altitude>0.0</altitude>
        </Location>
        <Orientation>
          <heading>{heading_deg:.2f}</heading>
          <tilt>0</tilt>
          <roll>0</roll>
        </Orientation>
        <Scale>
          <x>1.0</x>
          <y>1.0</y>
          <z>1.0</z>
        </Scale>
        <Link>
          <href>models/model.dae</href>
        </Link>
      </Model>
    </Placemark>
  </Document>
</kml>
"""

    # 5. Pakowanie do archiwum KMZ
    kmz_out = ROOT / 'dom_Gruszowa60.kmz'
    with zipfile.ZipFile(kmz_out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('doc.kml', kml_content.encode('utf-8'))
        zf.writestr('models/model.dae', dae_bytes)

    print(f"Zapisano pakiet KMZ: {kmz_out.name} ({kmz_out.stat().st_size / 1024 / 1024:.2f} MB)")
    print("Gotowe!")

if __name__ == '__main__':
    main()
