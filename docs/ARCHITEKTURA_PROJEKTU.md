# Architektura projektu domu

## Cel

Repozytorium ma działać jak tekstowy, wersjonowany system CAD/BIM-lite. Człowiek
lub AI powinien móc zmienić parametr, odtworzyć zależne widoki i sprawdzić wynik.

```
input (PDF/JPG/pomiary/usługi)
        ↓
normalizacja / ekstrakcja
        ↓
deklaracja YAML + provenance
        ↓
walidacja zależności i geometrii
        ↓
generatory modułów
        ↓
2D / 3D / GLB / Google / portal / zestawienia
```

## Moduły

1. Mapa — układy współrzędnych, georeferencja, parcela, Google/Geoportal.
2. Teren — NMT, rzędne, nawierzchnie PZT, kontekst otoczenia.
3. Dom 2D — rzuty, elewacje, przekroje, osie, ściany i otwory.
4. Dom 3D — poziomy, ekstruzje, strop, dach i bryła.
5. Wykończenia — materiały, elewacje, stolarka i warstwy.
6. Wnętrze — pomieszczenia, zabudowy, meble, materiały i wyposażenie.
7. Ogród — nawierzchnie, rośliny, mała architektura, woda i oświetlenie.

Mapa jest przed terenem, bo georeferencja jest bazą dla NMT/ortofoto/Google.
Dom 2D jest równoległą bazą geometryczną dla domu 3D.

## Źródło prawdy

Migracja jest modułowa:
- legacy: źródłem prawdy jest stary kod/JSON,
- hybrid: YAML opisuje moduł, ale część parametrów nadal żyje w starych plikach,
- declarative: YAML jest jedynym edytowalnym źródłem prawdy.

Nie utrzymujemy dwóch równorzędnych kopii tego samego parametru.

## Provenance

Docelowy parametr powinien mieć: wartość + jednostkę, typ (measured/project/
ordered/assumed/derived), źródło (plik + strona/zdjęcie/pomiar), opcjonalną
tolerancję i wersję/datę. AI nie powinno zrównywać wymiaru projektowego,
zamówieniowego i pomiaru ze stanu wykonanego.

## Stan migracji

Wszystkie siedem modułów jest deklaratywnych. Stare JSON-y są generowanymi snapshotami zgodności, a kod Pythona interpretuje YAML i tworzy artefakty. Wnętrze pozostaje finalnym konsumentem stabilnej geometrii domu.

## Sterowanie

```bash
python -m pip install PyYAML
python scripts/project.py validate
python scripts/project.py status
python scripts/project.py plan interior
python scripts/project.py plan garden
```
