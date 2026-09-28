#!/usr/bin/env python3
"""Google export from already georeferenced EPSG:2180 scene vertices.

Only the source facade polygon uses project->survey transformation. Scene vertices
already have east/north coordinates; never transform them by that matrix again.
"""
import json
import hashlib
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import trimesh
from pyproj import Geod, Transformer
from google_geodesy import source_to_google_altitude, google_vertical_provenance
from project_config import load_house_2d_model

ROOT = Path(__file__).resolve().parent
PROJECT_CATEGORIES = {
    'sciany', 'uzupelnienia', 'stolarka', 'podlogi', 'izolacja', 'strop',
    'dach', 'daszek', 'elewacja', 'nawierzchnie', 'schody',
    'ogrod_nawierzchnie', 'ogrod_woda', 'ogrod_architektura',
    'ogrod_rosliny', 'ogrod_oswietlenie',
}
# Keep the house independent from site/garden geometry so the Google viewer can
# reproduce the as-built raised zero without moving the driveway or garden.
BUILDING_CATEGORIES = {
    'sciany', 'uzupelnienia', 'stolarka', 'podlogi', 'izolacja', 'strop',
    'dach', 'daszek', 'elewacja',
}
SITE_CATEGORIES = PROJECT_CATEGORIES - BUILDING_CATEGORIES
GEOD = Geod(ellps='WGS84')
TO_WGS = Transformer.from_crs(2180, 4326, always_xy=True)


class SurveyFrame:
    def __init__(self, scene, source):
        if scene.get('up_axis') != 'Z' or scene.get('units') != 'm':
            raise ValueError('Expected a georeferenced metre / Z-up scene')
        a = scene['geo_alignment']
        self.project_matrix = np.array(a['house_calibration']['model_to_geo_local_affine_mm'])
        self.grid_origin = np.array(a['geo_context_center_epsg2180'])
        self.local_origin = np.array(a['geo_context_anchor_model_mm']) / 1000
        self.zero_elevation = float(a['model_zero_elevation_m'])
        project_center = np.mean(source['facade_reference_outline']['polygon_mm'], axis=0)
        self.anchor_xy = (self.project_matrix @ [*project_center, 1])[:2] / 1000
        self.lon, self.lat = self.wgs84(self.anchor_xy[None, :])[0]
        e, n = self.grid(self.anchor_xy)
        self.google_elevation = source_to_google_altitude(e, n, self.zero_elevation)

    def grid(self, xy):
        return np.asarray(xy) - self.local_origin + self.grid_origin

    def wgs84(self, xy):
        grid = self.grid(xy)
        lon, lat = TO_WGS.transform(grid[:, 0], grid[:, 1])
        return np.column_stack((lon, lat))

    def enu(self, vertices):
        """True east/north metres, including grid convergence and map scale."""
        vertices = np.asarray(vertices, dtype=float)
        ll = self.wgs84(vertices[:, :2])
        az, _, distance = GEOD.inv(np.full(len(ll), self.lon), np.full(len(ll), self.lat), ll[:, 0], ll[:, 1])
        az = np.radians(az)
        return np.column_stack((distance * np.sin(az), distance * np.cos(az), vertices[:, 2]))


def google_meshes(scene, frame, categories=PROJECT_CATEGORIES):
    """Batch compatible materials while preserving alpha and flat normals."""
    groups = defaultdict(list)
    prototypes = {}
    for part in scene['parts']:
        if part['category'] not in categories:
            continue
        key = (part.get('material', part['category']), tuple(part['color']))
        mesh = trimesh.Trimesh(vertices=frame.enu(part['positions_m']), faces=part['faces'], process=False)
        groups[key].append(mesh)
        prototypes[key] = part
    meshes = []
    for key, items in groups.items():
        part = prototypes[key]
        mesh = trimesh.util.concatenate(items)
        mesh.unmerge_vertices()
        # Concatenation can carry averaged normals from the original meshes.
        # Each triangle has its own vertices after unmerge: retain sharp edges.
        mesh.vertex_normals = np.repeat(mesh.face_normals, 3, axis=0)
        rgba = np.round(np.array(part['color']) * 255).astype(np.uint8)
        material = trimesh.visual.material.PBRMaterial(
            name=key[0], baseColorFactor=rgba, metallicFactor=0.0,
            roughnessFactor=0.82, alphaMode='BLEND' if part['color'][3] < .999 else 'OPAQUE',
            doubleSided=True,
        )
        mesh.visual = trimesh.visual.TextureVisuals(material=material)
        meshes.append(mesh)
    return meshes


def export_glb(meshes):
    """Export one Google model layer in glTF Y-up coordinates."""
    gltf = trimesh.Scene()
    y_up = np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]])
    for index, mesh in enumerate(meshes):
        converted = mesh.copy()
        converted.apply_transform(y_up)
        gltf.add_geometry(converted, node_name=f'material_{index:03d}', geom_name=f'material_{index:03d}')
    return trimesh.exchange.gltf.export_glb(gltf, include_normals=True)


def write_versioned_google_model(glb_bytes, stem):
    digest = hashlib.sha256(glb_bytes).hexdigest()[:16]
    relative_path = Path('google_models') / f'{stem}.{digest}.glb'
    (ROOT/relative_path).parent.mkdir(exist_ok=True)
    (ROOT/relative_path).write_bytes(glb_bytes)
    return relative_path


def write_kmz(scene, terrain, frame, meshes):
    ns = 'http://www.opengis.net/kml/2.2'
    ET.register_namespace('', ns)
    def child(parent, name, text=None):
        node = ET.SubElement(parent, '{'+ns+'}'+name)
        if text is not None:
            node.text = str(text)
        return node
    root = ET.Element('{'+ns+'}kml')
    doc = child(root, 'Document')
    child(doc, 'name', 'Dom i ogród · georeferencja PZT')
    child(doc, 'description', 'PZT / PL-EVRF2007-NH przeliczone do EGM96. Położenie mapy Google może różnić się od pomiaru geodezyjnego.')
    pm = child(doc, 'Placemark'); child(pm, 'name', 'Dom i ogród 3D (COLLADA)')
    model = child(pm, 'Model'); child(model, 'altitudeMode', 'absolute')
    location = child(model, 'Location')
    for name, value in [('longitude', frame.lon), ('latitude', frame.lat), ('altitude', frame.google_elevation)]:
        child(location, name, value)
    orientation = child(model, 'Orientation')
    for name in ('heading', 'tilt', 'roll'):
        child(orientation, name, 0)
    child(child(model, 'Link'), 'href', 'models/model.dae')

    # Optional mobile fallback, hidden to avoid overlapping faces on desktop.
    native = child(doc, 'Folder')
    child(native, 'name', 'Bryła uproszczona — włącz, jeśli brak modelu COLLADA')
    child(native, 'visibility', 0)
    for cat, title in [('sciany','Ściany'), ('dach','Dach'), ('daszek','Daszek'), ('stolarka','Stolarka'), ('ogrod_woda','Basen')]:
        parts = [p for p in scene['parts'] if p['category'] == cat]
        if not parts:
            continue
        pm = child(native, 'Placemark'); child(pm, 'name', title); child(pm, 'visibility', 0)
        color = np.round(np.array(parts[0]['color']) * 255).astype(int)
        style = child(pm, 'Style'); ps = child(style, 'PolyStyle')
        child(ps, 'color', ''.join(f'{v:02x}' for v in color[[3,2,1,0]])); child(ps, 'outline', 0)
        geometry = child(pm, 'MultiGeometry')
        for part in parts:
            v = np.asarray(part['positions_m']); ll = frame.wgs84(v[:, :2])
            alt = v[:, 2] + frame.google_elevation
            for face in part['faces']:
                polygon = child(geometry, 'Polygon'); child(polygon, 'altitudeMode', 'absolute')
                ring = child(child(polygon, 'outerBoundaryIs'), 'LinearRing')
                child(ring, 'coordinates', ' '.join(f'{ll[i,0]:.9f},{ll[i,1]:.9f},{alt[i]:.5f}' for i in [*face,face[0]]))

    boundary = child(doc, 'Placemark'); child(boundary, 'name', 'Granica działki ULDK')
    line = child(child(boundary, 'Style'), 'LineStyle')
    child(line, 'color', 'ff007aff'); child(line, 'width', 2)
    mg = child(boundary, 'MultiGeometry')
    for part in terrain['parts']:
        if part['category'] != 'granica_dzialki':
            continue
        v = np.asarray(part['positions_m'])
        if len(v) != 4:
            raise ValueError('Expected original ULDK boundary ribbons')
        ll = frame.wgs84(np.array([(v[0,:2]+v[1,:2])/2, (v[2,:2]+v[3,:2])/2]))
        line = child(mg, 'LineString'); child(line, 'tessellate', 1); child(line, 'altitudeMode', 'clampToGround')
        child(line, 'coordinates', ' '.join(f'{lon:.9f},{lat:.9f},0' for lon,lat in ll))

    # COLLADA declares Z_UP; GLB below follows glTF's Y_UP convention.
    dae = trimesh.exchange.dae.export_collada(meshes)
    dae_root = ET.fromstring(dae)
    dns = '{http://www.collada.org/2005/11/COLLADASchema}'
    asset = dae_root.find(dns+'asset')
    up = asset.find(dns+'up_axis')
    if up is None:
        up = ET.SubElement(asset, dns+'up_axis')
    up.text = 'Z_UP'
    # Stable zip timestamps make repeat builds comparable.
    with zipfile.ZipFile(ROOT/'dom_Gruszowa60.kmz', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in [('doc.kml', ET.tostring(root, encoding='utf-8', xml_declaration=True)),
                              ('models/model.dae', ET.tostring(dae_root, encoding='utf-8', xml_declaration=True))]:
            info = zipfile.ZipInfo(name, date_time=(2026,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info, content)


def main():
    scene = json.loads((ROOT/'scena_modelu.json').read_text(encoding='utf-8'))
    source = load_house_2d_model()['source_data']
    terrain = json.loads((ROOT/'geoportal_teren.json').read_text(encoding='utf-8'))
    frame = SurveyFrame(scene, source)
    meshes = google_meshes(scene, frame)
    building_meshes = google_meshes(scene, frame, BUILDING_CATEGORIES)
    site_meshes = google_meshes(scene, frame, SITE_CATEGORIES)
    if not building_meshes or not site_meshes:
        raise ValueError('Google export requires both building and site layers')
    # The Google photogrammetric building must not hide the design occupying
    # the same space. Use the surveyed facade outline, without guessed offsets.
    outline = np.array(source['facade_reference_outline']['polygon_mm'])
    outline_homogeneous = np.column_stack((outline, np.ones(len(outline))))
    outline_geo = (outline_homogeneous @ frame.project_matrix.T)[:, :2] / 1000
    footprint = [{'lat': float(lat), 'lng': float(lon)} for lon, lat in frame.wgs84(outline_geo)]
    glb_bytes = export_glb(meshes)
    building_glb_bytes = export_glb(building_meshes)
    site_glb_bytes = export_glb(site_meshes)
    (ROOT/'dom_Gruszowa60.glb').write_bytes(glb_bytes)
    # Google's native model loader tests the literal URL suffix before fetching
    # it. A query such as .glb?v=hash passes our HTTP preflight but is discarded
    # by that loader. Version each filename instead, keeping the .glb suffix.
    model_relative_path = write_versioned_google_model(glb_bytes, 'dom_Gruszowa60')
    building_model_relative_path = write_versioned_google_model(building_glb_bytes, 'dom_Gruszowa60_building')
    site_model_relative_path = write_versioned_google_model(site_glb_bytes, 'dom_Gruszowa60_site')
    # Keep the download standards-compliant (glTF is Y-up), but explicitly
    # map it to Model3DElement's local Z-up frame. Google's clockwise X tilt
    # of 270 degrees turns (east, up, -north) into (east, north, up).
    # Orientation3D: https://developers.google.com/maps/documentation/javascript/reference/coordinates#Orientation3D
    # The official Y-up windmill sample also uses tilt=270:
    # https://developers.google.com/maps/documentation/javascript/3d/models
    metadata = {
        'schema_version': 2, 'model_url': model_relative_path.as_posix(),
        'building_model_url': building_model_relative_path.as_posix(),
        'site_model_url': site_model_relative_path.as_posix(),
        'building_categories': sorted(BUILDING_CATEGORIES),
        'site_categories': sorted(SITE_CATEGORIES),
        'center': {'lat': float(frame.lat), 'lng': float(frame.lon), 'altitude': float(frame.google_elevation)},
        'altitude_mode': 'absolute', 'orientation': {'heading': 0, 'tilt': 270, 'roll': 0},
        'camera': {'center': {'lat': float(frame.lat), 'lng': float(frame.lon), 'altitude': float(frame.google_elevation+2)}, 'heading': 280, 'tilt': 65, 'range': 90},
        'house_footprint': footprint,
        'source': {'horizontal_crs': 'EPSG:2180', 'vertical_crs': 'PL-EVRF2007-NH',
                   'model_zero_elevation_m': frame.zero_elevation,
                   'anchor_scene_xy_m': frame.anchor_xy.tolist(),
                   'anchor_epsg2180': frame.grid(frame.anchor_xy).tolist()},
        'axes': 'glTF: +X true east, +Y up, -Z true north; metres; Google tilt=270 maps glTF to +X east, +Y north, +Z up',
        'vertical_datum': google_vertical_provenance(),
        'vertical_note': 'Official GUGiK geoid2021 + NGA EGM96 conversion; see geodesy/README.md. Google terrain is not survey-grade.',
    }
    (ROOT/'google_model_georef.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write_kmz(scene, terrain, frame, meshes)
    print(f'Google export: {len(meshes)} materials ({len(building_meshes)} building, {len(site_meshes)} site); '
          f'{frame.lat:.9f}, {frame.lon:.9f}; EGM96 {frame.google_elevation:.3f} m; heading 0')


if __name__ == '__main__':
    main()
