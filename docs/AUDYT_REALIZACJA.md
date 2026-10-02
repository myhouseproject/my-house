# Realizacja audytu z 2026-10-02

Audyt dotyczył `main` na `71c9074`. Poniżej zapisano zakres wprowadzonych
zmian, sprawdzony wobec zintegrowanego kodu tej aktualizacji. Identyfikator
rzeczywiście zbudowanego i opublikowanego wydania jest w `build-manifest.json`.
Ten dokument nie zastępuje raportu danego wydania ani odbioru na budowie.

| Ustalenie audytu | Zmiana techniczna | Co pozostaje |
| --- | --- | --- |
| A1. Dwa konkurencyjne generatory | Jeden generator geometrii; `generuj_model.py` kieruje do niego. Historyczny generator CAD jest wyłączonym archiwum | Nowy, dokładny eksport BREP/STEP nie jest dostępny; archiwalny STEP nie jest publikowany jako aktualny |
| A2. Nieaktualne raporty i sumy | Raport siatek, lista elementów, manifest wejść i sumy wyników powstają razem w izolowanej budowie | Raport siatek nie potwierdza pomiarów, kolizji wszystkich elementów ani konstrukcji |
| A3. Mapa skaluje wnętrze | `scena_lokalna.json` i lokalne GLB/OBJ powstają przed transformacją mapową. Kopia georeferencjonowana jest osobną sceną | Dopasowanie Google wymaga niezależnej oceny widoku; nie wolno z niego odczytywać wymiarów wnętrza |
| A4. Zabudowy 2900 mm, sufity 2850 mm | Polityki posadzki i sufitu dla każdego pokoju; statusy i decyzja widoczne w podglądzie | `D-CEILING`: uzgodnić wysokości i obniżenia; nie dokonano zbiorczego przycięcia mebli |
| A5. Obraz częściowo w murze | Poprawiono położenie względem lica; okładzina ściany uwzględnia otwór drzwiowy | `D-ART-DR11`: obraz nadal wymaga decyzji o lokalizacji wobec światła drzwi |
| A6. Brak gotowych lic i danych montażowych | Osobne referencje wykończeń, z zachowaniem otwartych granic pomieszczeń; niezależne statusy produktu, otworu, montażu i światła | `D-FINISHES`, `D-JOINERY`: pomierzyć lica oraz otwory. Referencyjne 15 mm tynku nie jest inwentaryzacją |
| A7. Bloki i wyposażenie nakładają się w eksporcie | Trzy osobne warianty GLB: powłoka, bloki, wyposażenie. Usunięte powtórne generowanie wskazanych elementów | Detal produktów pozostaje uproszczony, jeżeli brak danych producenta |
| A8. Nieuprawnione etykiety BREP i pewności | Metadane opisują rzeczywiste sprawdzenie siatek; brakujące dane montażowe mają jawny status | Zmiana statusu na pomiar wymaga nowego źródła |
| A9. Powielone parametry i niepełna przebudowa | Zależności liczone w jednym miejscu; ścisły odczyt YAML; budowa wnętrza bez map; wspólny zestaw zależności | Poprawność deklaracji nadal nie rozstrzyga rozbieżności dokumentacji |
| A10. Przejście z garażu | Odrębna polityka otworu i rejestr decyzji | `D-GARAGE-DR03`: potwierdzić obie posadzki, próg i wysokość. Stopień nie został wymyślony |

## Porządek, publikacja i narzędzia

- Źródła mają stabilne identyfikatory i hashe; istniejące PDF-y/zdjęcia są
  w `sources/`. Główny załączony PDF budowlany pozostał poza publicznym Git.
- Obszerne ekstrakcje są oddzielone od parametrów. Dawne sceny, eksporty i HTML
  nie są ręcznie utrzymywanymi źródłami; aktualne wyniki trafiają do `build/`.
- CI obejmuje każdy PR i push do `main`, budując oraz testując wnętrze i pełne
  wydanie. Pages otrzymuje tylko przygotowaną zawartość `dist/`.
- Rzut wnętrza, pomiar XY, przekrój poziomy, ukrywanie ścian i informacje
  o pomieszczeniu służą pracy nad lokalnym modelem.
- Zapis `.blend` korzysta z tej samej lokalnej sceny i jawnego wariantu
  wyposażenia. Weryfikacja tego etapu nie obejmowała uruchomienia Blendera.

Gałęzie zdalne i historia publicznego repozytorium nie zostały usunięte.
Przeniesienie plików nie usuwa historycznych kopii dokumentów z Git.

## Odbiór kolejnego wydania

Sprawdź łącznie `build-manifest.json`, `kontrola_modelu.json` oraz
`walidacja_projektu.json`. Pierwszy wiąże wejścia i pliki, drugi kontroluje
siatki, trzeci pokazuje stan danych i otwarte decyzje. Status poprawnej budowy
może współistnieć z `ready_for_fabrication: false`.

Dziesięć nierozstrzygniętych decyzji jest w
[config/decisions.yaml](../config/decisions.yaml), a potrzebne pomiary
opisuje [DECYZJE_I_POMIARY.md](DECYZJE_I_POMIARY.md). Następny etap to
potwierdzenie tej bazy, następnie warianty kuchni, salonu, spiżarni i wiatrołapu.
