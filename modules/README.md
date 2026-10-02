# Moduły projektu

`project.yaml` określa zależności. `module.yaml` opisuje wejścia, status migracji
i wykonanie, a `model.yaml` zawiera edytowalne parametry. Duże ekstrakcje mogą
być wydzielone do lokalnych plików danych wskazanych w deklaracji. Źródła
identyfikuje [sources/manifest.yaml](../sources/manifest.yaml).

| Moduł | Odpowiedzialność | Główna zależność |
| --- | --- | --- |
| `01_map` | Układy współrzędnych, georeferencja i usługi | — |
| `02_terrain` | Teren, PZT i kontekst otoczenia | mapa |
| `03_house_2d` | Rzut, ściany, pomieszczenia, otwory, produkty stolarki | — |
| `04_house_3d` | Poziomy, sufity i bryła | dom 2D |
| `05_finishes` | Materiały oraz odniesienia do gotowych lic | dom 3D |
| `06_interior` | Zabudowy i warianty wyposażenia | dom 3D, wykończenia |
| `07_garden` | Ogród i nawierzchnie | mapa, teren, dom 3D |

Status `declarative` oznacza sterowanie przez YAML, nie pomiarową pewność
danych. Nie zmieniaj źródłowego odczytu PDF w celu ukrycia rozbieżności;
zapisz osobny parametr i jego status `project`, `measured`, `ordered`,
`assumed` lub `derived`. Wyliczone zależności powinny mieć jedno miejsce
obliczania. Dane produktu, otworu i światła przejścia są odrębne.

```bash
python scripts/project.py status
python scripts/project.py plan interior
python scripts/project.py validate
python scripts/build.py --scope interior
```

Snapshoty zgodności i eksporty są wynikami budowy. Nie stanowią drugiego,
równorzędnego miejsca edycji. [Migracja](../docs/MIGRACJA_YAML.md) opisuje
przejście ze starych plików.
