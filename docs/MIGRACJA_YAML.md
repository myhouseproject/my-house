# Migracja konfiguracji do YAML

## Zasada

Od tej fazy edytujemy pliki w `modules/*/model.yaml`. Stare JSON-y w katalogu
głównym są snapshotami zgodności dla starszych narzędzi i nie powinny być
edytowane ręcznie.

Po zmianie YAML uruchom:

```bash
python scripts/project.py validate
python scripts/sync_legacy_config.py
```

Następnie uruchom generator właściwego modułu lub pełny rebuild.

## Mapa starych plików

| Stary plik | Nowe źródło |
| --- | --- |
| `geoportal_georef.json` | `modules/01_map/model.yaml` → `config` |
| `pzt_zagospodarowanie.json` | `modules/02_terrain/model.yaml` → `site` |
| `context_geometry_source.json` | `modules/02_terrain/model.yaml` → `context_geometry` |
| `dane_zrodlowe.json` | `modules/03_house_2d/model.yaml` → `source_data` |
| `obrys_dachu_z_pdf.json` | `modules/03_house_2d/model.yaml` → `roof` |
| `okna_projektowe.json` | `modules/03_house_2d/model.yaml` → `windows` |
| `stolarka_zewnetrzna.json` | `modules/03_house_2d/model.yaml` → `external_joinery` |
| `parametry_modelu.json` | `modules/04_house_3d/model.yaml` → `parameters` |
| `elewacje_materialy.json` | `modules/05_finishes/model.yaml` → `elevations` |
| `wnetrze_projekt.json` | `modules/06_interior/model.yaml` → `project` |

## Status modułów

Wszystkie moduły (`map`, `terrain`, `house_2d`, `house_3d`, `finishes`, `interior`, `garden`) mają status `declarative`. Parametry projektu, materiały, pozycje i receptury geometrii są w `model.yaml`; Python pozostaje interpreterem i generatorem.

## Dlaczego JSON-y nadal istnieją

Są jeszcze użyteczne dla starszych skryptów, zewnętrznych narzędzi i porównania
regresyjnego. `scripts/sync_legacy_config.py` odtwarza je z YAML. Test
`tests/test_declarative_sources.py` zatrzyma CI, jeżeli ktoś zmieni snapshot
ręcznie lub zapomni go zsynchronizować.
