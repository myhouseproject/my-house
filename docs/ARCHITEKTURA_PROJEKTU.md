# Architektura projektu domu

Model ma jedną ścieżkę geometrii oraz osobne warianty eksportu. Edytowalne
parametry i źródła są oddzielone od wyników. Lokalna baza wnętrza nie zależy
od dostępności usług mapowych.

## Przebieg budowy

1. Rejestr źródeł i deklaracje siedmiu modułów identyfikują wejście.
2. Walidacja sprawdza kontrakt danych, zależności i źródła.
3. Generator tworzy lokalną scenę domu w metrach, z osią Z w górę.
4. Eksportery wybierają powłokę, bloki robocze albo wyposażenie wizualne.
5. Zakres `full` tworzy osobną scenę georeferencjonowaną z otoczeniem.
6. Raport i manifest wiążą konkretne źródła, konfigurację i wyniki.
7. Poprawne wydanie trafia do `build/current`, a pliki publikowane do `dist/`.

Wejściem eksportera CAD nie może być osobna, historyczna wersja domu.
Dotychczasowy STEP jest materiałem archiwalnym; aktualny przebieg budowy
sprawdza siatki i nie deklaruje wykonania kontroli BREP.

## Podział odpowiedzialności

| Warstwa | Źródło prawdy | Odpowiedzialność |
| --- | --- | --- |
| Dowody | `sources/manifest.yaml` oraz wskazane dokumenty | identyfikator, hash, dostępność i rodzaj źródła |
| Parametry | `modules/*/model.yaml` i wskazane ekstrakcje | jednostki, wartości, statusy i zależności |
| Model | wspólny generator geometrii | lokalna geometria oraz metadane elementów |
| Eksport | ten sam model, jawny wariant | GLB/OBJ, portal, kopia dla mapy |
| Wydanie | raport i manifest z przebiegu budowy | powiązanie wejść z wynikami i sumami plików |

`declarative` oznacza sposób sterowania modułem. Nie oznacza, że wszystkie
parametry odtworzonego domu są potwierdzone pomiarem.

## Układy współrzędnych

Deklaracje geometryczne są w mm. Lokalna scena jest w m, Z w górę;
GLB jest w m, Y w górę. Gotowa posadzka części mieszkalnej stanowi lokalne
±0,00. Położenie garażu jest osobnym parametrem i obecnie oszacowaniem.

Dopasowanie obrysu do PZT, transformacja wysokości i korekta prezentacji Google
nie mogą zmieniać lokalnego wymiaru mebla lub pokoju. Scena do mapy powstaje
z kopii lokalnej geometrii. Więcej o rzędnych w
[geodesy/LEVELS.md](../geodesy/LEVELS.md).

## Kontrola i ograniczenia

Sprawdzenie eksportu obejmuje właściwości, które rzeczywiście można sprawdzić:
jednostki, granice, elementy, wariant warstw, siatki i integralność plików.
Kontrola kolizji i prześwitów wskazuje konkretne relacje modelu; nie potwierdza
nośności ani zgodności wykonania z projektem.

Wysokość strefy, gotowe lico, gabaryt produktu, otwór i światło przejścia to
osobne dane. Brak danych nie jest zastępowany statusem `measured`.
Otwarte decyzje są w [DECYZJE_I_POMIARY.md](DECYZJE_I_POMIARY.md).

## Praca i publikacja

Podstawowe polecenia są w [README](../README.md). Pełny zestaw buduje
`scripts/build.py`. Starsze entrypointy mogą pozostawać jako zgodność, lecz
nie powinny wytwarzać konkurencyjnego modelu.

CI uruchamia kontrolę dla każdego PR i push do `main`, niezależnie od nazwy
gałęzi. Publikowany jest kompletny artefakt danego wydania. Nie należy ręcznie
podmieniać jednego GLB w innym wydaniu ani odświeżać HTML bez regeneracji
zależnej geometrii po zmianie YAML.
