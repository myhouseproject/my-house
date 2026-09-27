# Vertical datum grids

The approved PZT and the Polish NMT use **PL-EVRF2007-NH** (EPSG:9651).
Google Maps 3D `ABSOLUTE` altitude uses **EGM96** (EPSG:5773), as documented
in the [Google altitude guide](https://developers.google.com/maps/documentation/javascript/3d/altitude-modes).

Run `python prepare_geodesy.py` after installing `requirements.txt` and before
running the Google exporter. The script downloads only the two pinned files below,
verifies their SHA-256 checksums, and reuses already verified local files. The
downloaded `.tif` files are reproducible build inputs and are not committed to git.

`google_geodesy.py` uses these local grids through PROJ's authoritative compound
CRS operation from EPSG:2180 + EPSG:9651 to EPSG:9707. Both grid checksums are
verified before use; missing grids or unavailable operations stop the export.
Ballpark transformations are disabled. No visual height adjustment is applied.

| File | Source and attribution | License | SHA-256 |
| --- | --- | --- | --- |
| `pl_gugik_geoid2021-PL-EVRF2007-NH.tif` | [PROJ download](https://cdn.proj.org/pl_gugik_geoid2021-PL-EVRF2007-NH.tif); © Główny Urząd Geodezji i Kartografii (GUGiK), GeoTIFF conversion by PROJ | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); [source provenance](https://cdn.proj.org/pl_gugik_README.txt) | `8b806d084296c0b8070a9cc9ad6d28218141e089e3ff0573254870447f361788` |
| `us_nga_egm96_15.tif` | [PROJ download](https://cdn.proj.org/us_nga_egm96_15.tif); US National Geospatial-Intelligence Agency (NGA), GeoTIFF conversion by PROJ | Public Domain; [source provenance](https://cdn.proj.org/us_nga_README.txt) | `db493027562c9b004d7220fa881f5603adada4e1c5029b933fa7de4547b0e78d` |

Downloaded unchanged on 2026-09-27. The GUGiK grid converts normal heights to
ellipsoidal heights; the inverse NGA grid converts ellipsoidal heights to EGM96.
The registered combined operation reports 2.02 m accuracy, which must not be
confused with a guarantee for Google's terrain or photogrammetric mesh.

At the house export origin (EPSG:2180 E=506159.61026812,
N=331679.09057524), PZT level 254.0 m transforms to EGM96 **253.72652018 m**.
Across the current house and garden, variation of the datum correction is below
0.0003 m. Keeping the rigid model's relative Z coordinates and applying the
converted origin is therefore adequate without changing its geometry.
