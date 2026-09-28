# Kontrola poziomu zero domu - 28.09.2026

Poziom posadzki części mieszkalnej jest zgodny z projektem: **±0,00 =
254,00 m w PL-EVRF2007-NH**. Jego wysokość w Google, po przeliczeniu układu,
wynosi **253,726520 m EGM96**. Różnica −0,273480 m wynika z układów odniesienia;
nie jest obniżeniem budynku względem projektu.

Na życzenie inwestora widok Google ma osobną **korektę wizualną +1,00 m**
na start. Jego wyświetlane zero wynosi więc **254,726520 m EGM96**. Korektę
można ustawić w panelu **Sprawdź poziomy → Korekta Google (m)** w zakresie
−10 do +10 m; wybór jest zapamiętywany w przeglądarce. **Według projektu
(0 m)** przywraca widok bez przesunięcia. Dotyczy to wyłącznie umieszczenia
projektu domu i ogrodu w Google, wraz ze znacznikiem i celem kamery.
Geometria, rzędne źródłowe, pobierane GLB/KMZ i pozostałe widoki są niezmienione.

## Dokumentacja i bieżący model

Sprawdzono załączony „Projekt budowlany PZT_PAB_2024.02.01.pdf”. Numeracja
odnosi się do stron PDF, nie numerów drukowanych na arkuszu.

| Punkt odniesienia | Wysokość | Źródło |
| --- | --- | --- |
| Wejście / ±0,00 domu | 254,00 m PL-EVRF2007-NH | s. 15, L-AA-0-01; s. 16, C-RD-1-01 |
| Rzędna posadowienia | 252,60 m | s. 15; nie jest poziomem posadzki |
| Gotowa podłoga części mieszkalnej | ±0,00 | s. 26-28, rzut i przekroje |
| Nawierzchnia przy garażu | 253,98 m, przy budynku 254,00 m | s. 16 |
| Nawierzchnia przy wejściu | 253,70 m we wnęce, 253,58 m dalej od ściany | s. 16 |
| Nawierzchnia dalej na północ | 253,40 m, dalej 253,00 m | s. 16 |
| Garaż w bieżącym modelu | +0,238462 m względem części mieszkalnej | późniejsze ustalenie inwestora w `parametry_modelu.json` |

Garaż w pierwotnym rzucie ma 0,00, lecz model uwzględnia późniejsze ustalenie
o jednej warstwie pustaka różnicy. Wartość 238,462 mm jest oszacowaniem
3100 / 13, a nie pomiarem geodezyjnym. Zachowano tę zmianę. Podobnie późniejsza
wysokość attyki +4,15 m nie zmienia globalnego poziomu zero.

## Dlaczego podłoga może przecinać teren mapy

Sprawdzono oryginalne wysokości NMT GUGiK (pomiar 23.03.2022), zachowane w
`context_geometry_source.json`, przed modelowaną niwelacją. Punkty są w tej
samej lokalnej siatce EPSG:2180 co scena; obrys domu przekształcono macierzą PZT
jednokrotnie.

| Sprawdzenie NMT | Wynik PL-EVRF2007-NH |
| --- | --- |
| 69 wierzchołków eksportowanej siatki pod obrysem domu | 253,59-254,69 m |
| Wysokość w punkcie wstawienia domu, interpolowana w siatce | ok. 254,13 m |
| Punkt wstawienia EPSG:2180, E / N | 506159,6103 / 331679,0906 m |

To wartości istniejącego terenu GUGiK, **nie odczyt terenu Google**. Siatka
eksportu ma około 2 m rozstawu; źródłowy raster ma 1 m i deklarowany błąd
średni wysokości 0,20 m. Nie należy traktować interpolacji jako pomiaru progu.

`uaktualnij_teren_i_otoczenie.py` obniża wyższe fragmenty NMT pod domem i tarasem
do −0,28 m (253,72 m) i przechodzi do istniejącego terenu w pasie 2 m. W ten
sposób podgląd lokalny pokazuje modelowaną niwelację. Google używa własnego
terenu. Jego `FlattenerElement` usuwa obiekty powierzchniowe, ale publiczny
interfejs nie pozwala zadać projektowanej rzędnej niwelacji.

Dawny opis `nmt_at_model_center_m = 253,08` dotyczył środka obszaru pobrania
przy E=506165,061 / N=331710,593, około 32 m od punktu wstawienia domu.
Zmieniono nazwę na `nmt_at_fetch_center_m` i dodano współrzędne próbki.
Poprawiono też nieaktualny opis zera 253,5 m w modelu zastępczego terenu.

## Kontrola widocznego terenu Google

W widoku Google 3D przycisk **Sprawdź poziomy** pokazuje obie rzędne tego samego
zera. **Zmierz teren Google** tymczasowo ukrywa projekt. Po ustabilizowaniu
mapy należy kliknąć odkryty grunt przy elewacji. Wynik pokazuje wysokość
powierzchni Google i dwie różnice w tym samym układzie EGM96: względem
źródłowego zera projektu oraz względem zera po korekcie widoku Google.
Odczyt ma charakter przybliżony; kliknięcie dachu lub drzewa zmierzy jego
powierzchnię. Stan spłaszczenia jest podany przy wyniku.

Korekta widoku nie jest nowym pomiarem geodezyjnym. Dostępna przeglądarka
testowa nie renderuje WebGL2, więc nie ma jeszcze liczbowych próbek rzeczywistej
siatki Google przy progach. Panel korzysta z już działającej mapy i nie wymaga
włączenia osobnej usługi Elevation API.

Źródła API:

- [Układy i tryby wysokości Google](https://developers.google.com/maps/documentation/javascript/3d/altitude-modes)
- [Odczyt wysokości pod kursorem](https://developers.google.com/maps/documentation/javascript/reference/3d-map#LocationClickEvent)
- [Spłaszczanie siatki](https://developers.google.com/maps/documentation/javascript/reference/3d-map-draw#FlattenerElement)
