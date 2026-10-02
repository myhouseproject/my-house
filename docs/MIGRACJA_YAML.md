# Konfiguracja i migracja starych plików

Parametry zmieniamy w `modules/*/model.yaml` lub wskazanej przez niego
wydzielonej ekstrakcji. `module.yaml` opisuje kontrakt modułu. Źródła dokumentów
są wskazywane przez `source_id` z `sources/manifest.yaml`.

## Mapa danych zgodności

| Dawny snapshot | Moduł / sekcja źródłowa |
| --- | --- |
| `geoportal_georef.json` | `01_map` → `config` |
| `pzt_zagospodarowanie.json` | `02_terrain` → `site` |
| `context_geometry_source.json` | `02_terrain` → `context_geometry` |
| `dane_zrodlowe.json` | `03_house_2d` → `source_data` |
| `obrys_dachu_z_pdf.json` | `03_house_2d` → `roof` |
| `okna_projektowe.json` | `03_house_2d` → `windows` |
| `stolarka_zewnetrzna.json` | `03_house_2d` → `external_joinery` |
| `parametry_modelu.json` | `04_house_3d` → `parameters` |
| `elewacje_materialy.json` | `05_finishes` → `elevations` |
| `wnetrze_projekt.json` | `06_interior` → `project` |

Mapa wskazuje logiczne sekcje: obszerne listy współrzędnych mogą znajdować się
w wydzielonych plikach YAML dołączanych przez model modułu. Nie przenoś ręcznej
poprawki do JSON-u zgodności, bo kolejna budowa go odtworzy.

## Zmiana parametru

1. Przeczytaj `project.yaml`, właściwy `module.yaml` i wskazane źródła.
2. Zmień pojedyncze miejsce definicji w YAML; zachowaj źródło i status.
3. Uruchom `python scripts/project.py validate`.
4. Uruchom `python scripts/build.py --scope interior` dla bryły i wnętrza
   albo `--scope full --test` dla wydania obejmującego otoczenie.
5. Sprawdź raport i podgląd z tego samego wydania, szczególnie wymiary
   oraz ostrzeżenia zmienionego elementu.

Synchronizacja snapshotów sama nie przebudowuje geometrii. Ręczne odświeżenie
podglądu również nie zastępuje budowy po zmianie YAML.

## Co oznacza porządkowanie po audycie

- Źródłowe PDF-y i zdjęcia już obecne w Git są w `sources/documents/`
  i `sources/photos/`. Główny załączony PDF budowlany pozostaje zewnętrzny;
  jego SHA-256 identyfikuje ekstrakcję.
- Aktualne zasady, decyzje i referencje są w `docs/`. Poprzednie opisy stanu
  modelu w `docs/archive/` pozostają historią, nie instrukcją budowania.
- Generowanie domu oraz warianty eksportu mają wspólną geometrię.
  Historyczny STEP i stare raporty są w `archive/model-2026-09-24/`,
  poza bieżącym wydaniem.
- Wyniki bieżącej budowy znajdują się w `build/current`; publikacja korzysta
  z `dist/`, bez dokumentów źródłowych i archiwalnych eksportów.

Nie usuwamy gałęzi zdalnych wyłącznie na podstawie ich wieku lub nazwy.
Porządek w plikach nie rozstrzyga, czy dana gałąź zawiera niescalone ustalenia.
