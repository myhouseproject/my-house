"""Convert surveyed Polish normal heights to Google's EGM96 altitude datum.

Google Maps 3D ABSOLUTE altitude uses EGM96, whereas the approved PZT uses
PL-EVRF2007-NH. This module requires the two bundled authoritative geoid grids;
it never substitutes a guessed height correction or a ballpark operation.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import math
from pathlib import Path

from pyproj import CRS, datadir
from pyproj.crs import CompoundCRS
from pyproj.transformer import TransformerGroup


GRID_DIRECTORY = Path(__file__).resolve().parent / "geodesy"
GRID_SOURCES = (
    {
        "file": "pl_gugik_geoid2021-PL-EVRF2007-NH.tif",
        "url": "https://cdn.proj.org/pl_gugik_geoid2021-PL-EVRF2007-NH.tif",
        "sha256": "8b806d084296c0b8070a9cc9ad6d28218141e089e3ff0573254870447f361788",
        "credit": "Główny Urząd Geodezji i Kartografii (GUGiK); PROJ GeoTIFF conversion",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "provenance_url": "https://cdn.proj.org/pl_gugik_README.txt",
    },
    {
        "file": "us_nga_egm96_15.tif",
        "url": "https://cdn.proj.org/us_nga_egm96_15.tif",
        "sha256": "db493027562c9b004d7220fa881f5603adada4e1c5029b933fa7de4547b0e78d",
        "credit": "US National Geospatial-Intelligence Agency (NGA); PROJ GeoTIFF conversion",
        "license": "Public Domain",
        "license_url": "https://cdn.proj.org/us_nga_README.txt",
        "provenance_url": "https://cdn.proj.org/us_nga_README.txt",
    },
)


@lru_cache(maxsize=1)
def _vertical_transformer():
    for grid in GRID_SOURCES:
        path = GRID_DIRECTORY / grid["file"]
        if not path.is_file():
            raise RuntimeError(f"Missing required vertical datum grid: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != grid["sha256"]:
            raise RuntimeError(f"Vertical datum grid checksum mismatch: {path}")

    datadir.append_data_dir(str(GRID_DIRECTORY))
    source = CompoundCRS(
        "Poland CS92 + PL-EVRF2007-NH",
        [CRS.from_epsg(2180), CRS.from_epsg(9651)],
    )
    group = TransformerGroup(
        source,
        CRS.from_epsg(9707),  # WGS 84 + EGM96 height
        always_xy=True,
        allow_ballpark=False,
    )
    if not group.best_available or not group.transformers:
        raise RuntimeError("Authoritative PL-EVRF2007-NH to EGM96 transformation unavailable")
    transformer = group.transformers[0]
    if any(grid["file"] not in transformer.definition for grid in GRID_SOURCES):
        raise RuntimeError("Vertical datum operation does not use both required geoid grids")
    return transformer


def source_to_google_altitude(easting: float, northing: float, elevation_m: float) -> float:
    """Return EGM96 height for EPSG:2180 E/N and PL-EVRF2007-NH elevation.

    Horizontal arguments use explicit easting, northing order. ``errcheck``
    prevents an out-of-grid coordinate from quietly becoming infinite.
    """
    coordinates = tuple(float(value) for value in (easting, northing, elevation_m))
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("Geodetic coordinates and elevation must be finite")
    _, _, altitude = _vertical_transformer().transform(*coordinates, errcheck=True)
    if not math.isfinite(altitude):
        raise RuntimeError("Vertical datum transformation returned a non-finite height")
    return float(altitude)


def google_vertical_provenance() -> dict:
    """Return serializable provenance for the export placement metadata."""
    transformer = _vertical_transformer()
    return {
        "source_horizontal_crs": "EPSG:2180",
        "source_vertical_crs": "EPSG:9651 / PL-EVRF2007-NH",
        "target_crs": "EPSG:9707 / WGS 84 + EGM96 height",
        "operation": transformer.description,
        "pipeline": transformer.definition,
        "declared_operation_accuracy_m": transformer.accuracy,
        "ballpark_allowed": False,
        "grids": [dict(grid) for grid in GRID_SOURCES],
        "google_altitude_reference": "https://developers.google.com/maps/documentation/javascript/3d/altitude-modes",
        "note": "The datum conversion preserves surveyed heights; Google terrain/photogrammetry can have independent elevation errors.",
    }
