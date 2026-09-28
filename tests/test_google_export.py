"""Independent checks of Google export artefacts, without calling the exporter.

Run after regenerating exports: python -m unittest discover -s tests -v
The tests decode GLB directly, compare mesh landmarks to source survey geometry,
and use geodesic bearings to distinguish grid north from true north.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from urllib.parse import urlsplit
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
from pyproj import Geod, Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXPORT_CATEGORIES = {
    "sciany", "uzupelnienia", "stolarka", "podlogi", "izolacja", "strop",
    "dach", "daszek", "elewacja", "nawierzchnie", "schody",
    "ogrod_nawierzchnie", "ogrod_woda", "ogrod_architektura",
    "ogrod_rosliny", "ogrod_oswietlenie",
}


def read_glb(path):
    """Small independent glTF reader for positions/normals/index accessors."""
    raw = path.read_bytes()
    magic, version, total = struct.unpack_from("<4sII", raw)
    if (magic, version, total) != (b"glTF", 2, len(raw)):
        raise AssertionError("Invalid GLB header")
    document = None
    binary = None
    offset = 12
    while offset < len(raw):
        size, kind = struct.unpack_from("<I4s", raw, offset)
        chunk = raw[offset + 8:offset + 8 + size]
        if kind == b"JSON":
            document = json.loads(chunk)
        elif kind == b"BIN\x00":
            binary = chunk
        offset += 8 + size
    if document is None or binary is None:
        raise AssertionError("GLB must contain JSON and binary chunks")

    def accessor(index):
        spec = document["accessors"][index]
        if "sparse" in spec:
            raise AssertionError("Unexpected sparse export accessor")
        view = document["bufferViews"][spec["bufferView"]]
        dtype = np.dtype({5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}[spec["componentType"]])
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[spec["type"]]
        start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
        stride = view.get("byteStride", width * dtype.itemsize)
        return np.ndarray((spec["count"], width), dtype=dtype, buffer=binary,
                          offset=start, strides=(stride, dtype.itemsize)).copy()

    def node_matrix(node):
        if "matrix" in node:
            return np.asarray(node["matrix"], dtype=float).reshape(4, 4).T
        x, y, z, w = node.get("rotation", [0, 0, 0, 1])
        rotation = np.array([
            [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
        ])
        matrix = np.eye(4)
        matrix[:3, :3] = rotation @ np.diag(node.get("scale", [1, 1, 1]))
        matrix[:3, 3] = node.get("translation", [0, 0, 0])
        return matrix

    primitives = []
    def visit(index, parent):
        node = document["nodes"][index]
        matrix = parent @ node_matrix(node)
        if "mesh" in node:
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                if primitive.get("mode", 4) != 4:
                    raise AssertionError("Only triangle meshes expected")
                positions = accessor(primitive["attributes"]["POSITION"])
                positions = (np.c_[positions, np.ones(len(positions))] @ matrix.T)[:, :3]
                normals = accessor(primitive["attributes"]["NORMAL"])
                normals = normals @ np.linalg.inv(matrix[:3, :3])
                indices = accessor(primitive["indices"]).reshape(-1, 3)
                primitives.append({"positions": positions, "normals": normals,
                                   "faces": indices, "material": primitive["material"]})
        for child in node.get("children", []):
            visit(child, matrix)
    for node in document["scenes"][document.get("scene", 0)]["nodes"]:
        visit(node, np.eye(4))
    return document, primitives


def google_model_enu(vertices, orientation):
    """Apply Google's documented clockwise roll(Y), tilt(X), heading(Z).

    Orientation3D uses a Z-up map frame, not glTF's Y-up frame:
    https://developers.google.com/maps/documentation/javascript/reference/coordinates#Orientation3D
    Keep this independent of the exporter so a valid GLB with a wrong runtime
    orientation cannot pass only because its stored geometry looks correct.
    """
    heading, tilt, roll = -np.radians([
        orientation.get("heading", 0), orientation.get("tilt", 0), orientation.get("roll", 0)])
    ch, sh = np.cos(heading), np.sin(heading)
    ct, st = np.cos(tilt), np.sin(tilt)
    cr, sr = np.cos(roll), np.sin(roll)
    rz = np.array([[ch, -sh, 0], [sh, ch, 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, ct, -st], [0, st, ct]])
    ry = np.array([[cr, 0, sr], [0, 1, 0], [-sr, 0, cr]])
    return np.asarray(vertices) @ (rz @ rx @ ry).T


class GoogleExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = json.loads((ROOT / "scena_modelu.json").read_text())
        cls.source = json.loads((ROOT / "dane_zrodlowe.json").read_text())
        cls.metadata = json.loads((ROOT / "google_model_georef.json").read_text())
        cls.document, cls.primitives = read_glb(ROOT / "dom_Gruszowa60.glb")
        cls.parts = [part for part in cls.scene["parts"] if part["category"] in EXPORT_CATEGORIES]
        cls.actual = np.concatenate([part["positions"] for part in cls.primitives])
        cls.tree = cKDTree(cls.actual)
        cls.to_wgs = Transformer.from_crs(2180, 4326, always_xy=True)
        cls.geod = Geod(ellps="WGS84")

    def expected_positions(self, vertices):
        """Derive independent geodesic E/N from the stored survey scene frame."""
        alignment = self.scene["geo_alignment"]
        grid = (vertices[:, :2]
                - np.asarray(alignment["geo_context_anchor_model_mm"]) / 1000
                + np.asarray(alignment["geo_context_center_epsg2180"]))
        lon, lat = self.to_wgs.transform(grid[:, 0], grid[:, 1])
        center = self.metadata["center"]
        azimuth, _, distance = self.geod.inv(
            np.full(len(vertices), center["lng"]), np.full(len(vertices), center["lat"]), lon, lat)
        bearing = np.radians(azimuth)
        return np.c_[distance * np.sin(bearing), vertices[:, 2], -distance * np.cos(bearing)]

    def test_survey_origin_and_vertical_datum(self):
        # Independently verified from the PDF survey grid, not copied from GLB.
        center = self.metadata["center"]
        self.assertAlmostEqual(center["lat"], 50.851992708222596, places=9)
        self.assertAlmostEqual(center["lng"], 19.087529928942267, places=9)
        self.assertAlmostEqual(center["altitude"], 253.72652018461613, places=6)
        self.assertEqual(self.metadata["altitude_mode"], "absolute")
        self.assertEqual(self.metadata["orientation"], {"heading": 0, "tilt": 270, "roll": 0})
        self.assertEqual(self.metadata["source"]["model_zero_elevation_m"], 254)
        self.assertEqual(self.metadata["source"]["vertical_crs"], "PL-EVRF2007-NH")

    def test_google_model_url_keeps_glb_suffix_and_identifies_shipped_bytes(self):
        # Google's native loader chooses its GLB path using a literal URL suffix
        # check. A successful HTTP fetch of "model.glb?v=..." is insufficient:
        # that URL never reaches the native GLB decoder.
        model_url = self.metadata["model_url"]
        url = urlsplit(model_url)
        self.assertEqual(url.scheme, "")
        self.assertEqual(url.netloc, "")
        self.assertEqual(url.query, "", "Google's model URL cannot use query-string versioning")
        self.assertEqual(url.fragment, "", "Google's model URL must end literally in .glb")
        self.assertTrue(model_url.endswith(".glb"))

        raw = (ROOT / "dom_Gruszowa60.glb").read_bytes()
        digest = hashlib.sha256(raw).hexdigest()[:16]
        self.assertEqual(model_url, f"google_models/dom_Gruszowa60.{digest}.glb")
        versioned_path = ROOT / model_url
        self.assertTrue(versioned_path.is_file(), "The versioned Google model must be included in deployment")
        self.assertEqual(versioned_path.read_bytes(), raw,
                         "Google and the downloadable GLB must contain the same geometry")

    def test_house_and_garden_landmarks_share_one_frame(self):
        samples = []
        for part in self.parts:
            # Referenced vertices survive unmerging/batching; unused ones need not.
            referenced = np.unique(np.asarray(part["faces"]).ravel())
            chosen = referenced[np.unique(np.linspace(0, len(referenced)-1, min(5, len(referenced)), dtype=int))]
            samples.append(np.asarray(part["positions_m"])[chosen])
        expected = self.expected_positions(np.concatenate(samples))
        error, _ = self.tree.query(expected)
        self.assertLess(float(error.max()), 1e-4, "A source landmark moved or used the wrong coordinate frame")

    def test_extent_axes_and_complete_selected_topology(self):
        # Detect Z-up GLB, duplicate project rotation, missing garden, extra context.
        source = np.concatenate([np.asarray(part["positions_m"])[np.unique(np.asarray(part["faces"]).ravel())]
                                 for part in self.parts])
        expected = self.expected_positions(source)
        np.testing.assert_allclose(self.actual.min(axis=0), expected.min(axis=0), atol=1e-4, rtol=0)
        np.testing.assert_allclose(self.actual.max(axis=0), expected.max(axis=0), atol=1e-4, rtol=0)
        self.assertEqual(sum(len(primitive["faces"]) for primitive in self.primitives),
                         sum(len(part["faces"]) for part in self.parts))
        self.assertLess(np.ptp(self.actual[:, 1]), 20, "Vertical dimension must be house/tree height")
        self.assertGreater(np.ptp(self.actual[:, 2]), 100, "Garden length belongs to horizontal −Z")

    def test_google_runtime_orientation_preserves_east_north_up_and_roof_height(self):
        orientation = self.metadata["orientation"]
        # Three physical directions expressed in the exported glTF E/U/-N frame.
        gltf_east_north_up = np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])
        np.testing.assert_allclose(
            google_model_enu(gltf_east_north_up, orientation), np.eye(3), atol=1e-12,
            err_msg="Google must receive east/north/up, not a house rotated onto its side")

        roof = np.concatenate([primitive["positions"] for primitive in self.primitives
                               if self.document["materials"][primitive["material"]]["name"] == "dach"])
        source_roof = np.concatenate([part["positions_m"] for part in self.parts
                                      if part["category"] == "dach" and part.get("material", "dach") == "dach"])
        rendered_roof = google_model_enu(roof, orientation)
        anchor_altitude = self.metadata["center"]["altitude"]
        np.testing.assert_allclose(
            [rendered_roof[:, 2].min()+anchor_altitude, rendered_roof[:, 2].max()+anchor_altitude],
            [source_roof[:, 2].min()+anchor_altitude, source_roof[:, 2].max()+anchor_altitude],
            atol=1e-5, rtol=0, err_msg="Roof height must remain vertical after the Google transform")
        self.assertGreater(float(rendered_roof[:, 2].min()), 3.)
        # The long garden must remain horizontal; identity orientation buries it
        # by treating its northward distance (negative glTF Z) as elevation.
        rendered = google_model_enu(self.actual, orientation)
        self.assertGreater(np.ptp(rendered[:, 1]), 100)
        self.assertLess(np.ptp(rendered[:, 2]), 20)

    def test_true_north_convergence_and_scale_are_applied(self):
        # 100 m in CS92 north is not exactly 100 m in true geodesic north.
        anchor = np.asarray(self.metadata["source"]["anchor_scene_xy_m"])
        probe = np.array([[anchor[0], anchor[1]+100, 0.]])
        expected = self.expected_positions(probe)[0]
        np.testing.assert_allclose(expected, [.118558413, 0, -100.069932136], atol=1e-5, rtol=0)
        # Far garden landmarks would drift >10 cm without convergence correction.
        garden = max((part for part in self.parts if part["category"].startswith("ogrod_")),
                     key=lambda part: max(v[1] for v in part["positions_m"]))
        vertices = np.asarray(garden["positions_m"])
        expected = self.expected_positions(vertices)
        errors, _ = self.tree.query(expected)
        self.assertLess(float(errors.max()), 1e-4)

    def test_flattener_footprint_matches_original_pzt_and_house(self):
        # Use the original PZT/PL-2000 affine, not the exporter's intermediate
        # project -> scene -> CS92 route. This detects wrong/double rotations.
        alignment = self.scene["geo_alignment"]
        outline = np.asarray(self.source["facade_reference_outline"]["polygon_mm"])
        pzt_affine = np.asarray(alignment["house_calibration"]["model_to_epsg2177_affine_derived"])
        pzt = np.c_[outline, np.ones(len(outline))] @ pzt_affine.T
        to_cs92 = Transformer.from_crs(2177, 2180, always_xy=True)
        expected = np.column_stack(to_cs92.transform(pzt[:, 0], pzt[:, 1]))

        footprint = self.metadata["house_footprint"]
        self.assertGreaterEqual(len(footprint), 3)
        from_wgs = Transformer.from_crs(4326, 2180, always_xy=True)
        actual = np.column_stack(from_wgs.transform(
            [point["lng"] for point in footprint], [point["lat"] for point in footprint]))
        self.assertTrue(np.isfinite(actual).all())
        polygon = Polygon(actual)
        self.assertTrue(polygon.is_valid, "Flattener ring must not cross itself")
        self.assertFalse(polygon.is_empty)
        # Flattener closes the ring implicitly, so either closure spelling is OK.
        self.assertLess(polygon.hausdorff_distance(Polygon(expected)), .001)
        self.assertAlmostEqual(polygon.area, Polygon(expected).area, places=3)

        # The ring must clear this house, not a correctly shaped neighbouring site.
        walls = np.concatenate([part["positions_m"] for part in self.parts
                                if part["category"] in {"sciany", "elewacja"}])
        wall_grid = (walls[:, :2]
                     - np.asarray(alignment["geo_context_anchor_model_mm"]) / 1000
                     + np.asarray(alignment["geo_context_center_epsg2180"]))
        distance, _ = cKDTree(wall_grid).query(actual)
        self.assertLess(float(distance.max()), .001, "Footprint corners must meet the model facade")

    def test_camera_aims_inside_house_and_keeps_house_in_frame(self):
        camera = self.metadata["camera"]
        center = self.metadata["center"]
        target = camera["center"]
        footprint = Polygon([(point["lng"], point["lat"])
                             for point in self.metadata["house_footprint"]])
        self.assertTrue(footprint.contains(Point(target["lng"], target["lat"])))
        house = np.concatenate([part["positions_m"] for part in self.parts
                                if part["category"] in {"sciany", "elewacja", "strop", "dach"}])
        target_height = target["altitude"] - center["altitude"]
        self.assertGreaterEqual(target_height, float(house[:, 2].min()))
        self.assertLessEqual(target_height, float(house[:, 2].max()),
                             "Camera must aim at the house, not the sky above it")

        # Project the source house using Google's documented heading/tilt/range
        # meanings and default vertical FOV=35 degrees. Use a 3:4 viewport so
        # this also catches horizontal cropping in a typical portrait map pane.
        azimuth, _, distance = self.geod.inv(center["lng"], center["lat"], target["lng"], target["lat"])
        bearing = np.radians(azimuth)
        target_enu = np.array([distance*np.sin(bearing), distance*np.cos(bearing), target_height])
        heading, tilt = np.radians([camera["heading"], camera["tilt"]])
        forward = np.array([np.sin(heading)*np.sin(tilt), np.cos(heading)*np.sin(tilt), -np.cos(tilt)])
        right = np.array([np.cos(heading), -np.sin(heading), 0.])
        up = np.cross(right, forward)
        eye = target_enu - float(camera["range"]) * forward
        gltf = self.expected_positions(house)
        rays = google_model_enu(gltf, self.metadata["orientation"]) - eye
        depth = rays @ forward
        self.assertGreater(float(depth.min()), 0, "House must be in front of the camera")
        tangent = np.tan(np.radians(camera.get("fov", 35)) / 2)
        horizontal = np.abs(rays @ right) / (depth * tangent * .75)
        vertical = np.abs(rays @ up) / (depth * tangent)
        self.assertLess(float(horizontal.max()), .95, "House must fit the portrait viewport with margin")
        self.assertLess(float(vertical.max()), .95, "House must fit the vertical field of view with margin")

    def test_materials_and_flat_normals(self):
        materials = self.document["materials"]
        self.assertTrue(materials)
        self.assertLess(len(materials), len(self.parts), "Materials should be batched")
        self.assertFalse(self.document.get("extensionsRequired"), "Google supports core glTF PBR only")
        for material in materials:
            pbr = material["pbrMetallicRoughness"]
            self.assertEqual(pbr["metallicFactor"], 0)
            self.assertGreater(pbr["roughnessFactor"], .5)
            alpha = pbr["baseColorFactor"][3]
            self.assertEqual(material.get("alphaMode", "OPAQUE"), "BLEND" if alpha < .999 else "OPAQUE")
        exported_colors = np.asarray([material["pbrMetallicRoughness"]["baseColorFactor"] for material in materials])
        for part in self.parts:
            self.assertLessEqual(float(np.abs(exported_colors-np.asarray(part["color"])).max(axis=1).min()), 1/255 + 1e-8)
        for primitive in self.primitives:
            positions, normals, faces = (primitive[key] for key in ("positions", "normals", "faces"))
            self.assertTrue(np.isfinite(positions).all())
            self.assertTrue(np.isfinite(normals).all())
            triangles = positions[faces]
            face_normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
            lengths = np.linalg.norm(face_normals, axis=1)
            edge_lengths = np.linalg.norm(triangles-np.roll(triangles, 1, axis=1), axis=2)
            # Sub-0.1 mm edges lose directional precision in GLB float32. Still
            # verify their flat vertex normals, but avoid an unstable cross product.
            np.testing.assert_allclose(normals[faces][:, 1], normals[faces][:, 0], atol=1e-6)
            np.testing.assert_allclose(normals[faces][:, 2], normals[faces][:, 0], atol=1e-6)
            valid = (lengths > 1e-6) & (edge_lengths.min(axis=1) > 1e-4)
            face_normals = face_normals[valid] / lengths[valid, None]
            # Triangle-flat shading avoids blended normals across facade corners.
            dots = (normals[faces[valid]] * face_normals[:, None, :]).sum(axis=2)
            self.assertGreater(float(dots.min()), .995)

    def test_kmz_origin_matches_glb_and_collada_is_z_up(self):
        with zipfile.ZipFile(ROOT / "dom_Gruszowa60.kmz") as archive:
            kml = ET.fromstring(archive.read("doc.kml"))
            dae = ET.fromstring(archive.read("models/model.dae"))
        ns = {"k": "http://www.opengis.net/kml/2.2", "d": "http://www.collada.org/2005/11/COLLADASchema"}
        model = kml.find(".//k:Model", ns)
        self.assertEqual(model.findtext("k:altitudeMode", namespaces=ns), "absolute")
        for xml_name, metadata_name in [("longitude", "lng"), ("latitude", "lat"), ("altitude", "altitude")]:
            self.assertAlmostEqual(float(model.findtext("k:Location/k:"+xml_name, namespaces=ns)),
                                   self.metadata["center"][metadata_name], places=9)
        for axis in ["heading", "tilt", "roll"]:
            self.assertEqual(float(model.findtext("k:Orientation/k:"+axis, namespaces=ns)), 0)
        self.assertEqual(dae.findtext("d:asset/d:up_axis", namespaces=ns), "Z_UP")

    def test_authoritative_vertical_grids_and_no_silent_fallback(self):
        from google_geodesy import GRID_SOURCES, google_vertical_provenance, source_to_google_altitude
        provenance = google_vertical_provenance()
        self.assertFalse(provenance["ballpark_allowed"])
        for grid in GRID_SOURCES:
            self.assertEqual(hashlib.sha256((ROOT/"geodesy"/grid["file"]).read_bytes()).hexdigest(), grid["sha256"])
        easting, northing = self.metadata["source"]["anchor_epsg2180"]
        result = source_to_google_altitude(easting, northing, 254.)
        self.assertAlmostEqual(result, self.metadata["center"]["altitude"], places=7)
        with self.assertRaises(ValueError):
            source_to_google_altitude(easting, northing, float("nan"))


if __name__ == "__main__":
    unittest.main()
