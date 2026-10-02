# Decyzje i pomiary przed detalowaniem wnętrz

Stan odniesienia: audyt `main` z 2026-10-02, commit `71c9074`.
Prace porządkują model i jego kontrolę; nie tworzą brakującego pomiaru budynku.
Poniższe wartości pozostają jawne, dopóki nie otrzymają wiarygodnego źródła.
Identyfikatory odpowiadają [config/decisions.yaml](../config/decisions.yaml),
który zasila kontrolę i podgląd; ten dokument wyjaśnia potrzebne dane.

## Dane wymagające potwierdzenia

| ID | Zastany stan / dokumentacja | Potrzebna decyzja lub pomiar | Warunek zamknięcia |
| --- | --- | --- | --- |
| `D-CEILING` | W modelu sufit 2850 mm, mur 3100 mm, attyka 4150 mm; pochodzenie niepotwierdzone. Wnętrza s. 29, 31: zabudowy 2900 mm, s. 47: kuchnia 2600 mm. Budowlany s. 27–28: sufit 2600 mm + 300 mm przestrzeni instalacyjnej | Pomierzyć strop i gotowy sufit per pomieszczenie; uzgodnić obniżenia z wentylacją, oświetleniem i karniszami | Każda strefa ma źródło, zaakceptowany sufit i sprawdzone prześwity zabudowy |
| `D-GARAGE-DR03` | Garaż roboczo +238,462 mm, wyliczone jako 3100/13 z ustalenia o jednej warstwie | Pomiar obu gotowych posadzek, progu i górnej krawędzi DR03; ustalić stopień i kierunek otwierania | Otwór oraz dostępna wysokość od strony garażu zgodne z pomiarem |
| `D-FLOOR-BUILDUP` | Pakiet podłogi 290 mm i podest −290 mm z informacji inwestora; PDF ma 250 + 70 mm plus wykończenie | Potwierdzić, czego dotyczy 290 mm i rzeczywistą rzędną gotowego wejścia | Osobno zapisane zero posadzki, konstrukcja podłogi, podest i wykończenie |
| `D-JOINERY` | Gabaryty produktów okien, drzwi i bramy z ofert; montaż i luzy nie są nimi potwierdzone | Szerokość i wysokość każdego otworu, parapet/próg, głębokość osadzenia; osobno światło przejścia | Dane produktu, otworu i przejścia mają niezależne statusy i źródła |
| `D-FINISHES` | Tynk 15 mm w przekrojach budowlanych; brak kompletnego doboru okładzin każdej ściany | Potwierdzić tynki, płytki, kleje, panele i zabudowy przedścienne per lico | Szerokość zabudowy liczona pomiędzy gotowymi licami, z tolerancją montażu |
| `D-KITCHEN-UTILITIES` | Wyspa 2900 × 900 mm; przejścia 1000, 940 i 1300 mm w projekcie wnętrz | Sprawdzić przejścia przy odsuniętych hokerach i otwartych frontach; aktualne okno W11 i punkty wod-kan/zasilania (s. 48) | Zaakceptowany wariant aranżacji, sprzęt i rzeczywiste położenie przyłączy |
| `D-W05-W06` | Łazienkowe okna RU lewe i FIX bez pewnego przypisania do ścian | Potwierdzić, które okno zamontowano w której ścianie | Rzut i typ okna zgodne ze stanem wykonania |
| `D-DOOR-SWINGS` | Rzeczywiste światła i kierunki otwierania nie są kompletnie potwierdzone | Zawiasy, kierunek, szerokość skrzydła i światło każdego otworu | Sprawdzone strefy otwierania i przejścia |
| `D-ART-DR11` | Obraz ściany ART nachodzi o 420 mm na projektowe światło drzwi DR11 | Uzgodnić pozycję obrazu z aktualnym otworem; korekta do lica ściany nie rozstrzyga położenia wzdłuż ściany | Zaakceptowana lokalizacja obrazu bez kolizji z drzwiami |
| `D-SOURCE-REVISION` | Nazwa głównego PDF-u wskazuje 2024-02-01, okładka lipiec 2023 | Wskazać zatwierdzoną rewizję i zakres późniejszych zmian wykonawczych | Zapisana hierarchia wersji, bez wybierania nowszej daty z samej nazwy |

## Zasady już przyjęte w modelu

- Zachowujemy lokalne `Z=0` na gotowej posadzce części mieszkalnej. Rzędna
  projektu 254,00 m PL-EVRF2007-NH i korekta Google są odrębnymi pojęciami.
- Zachowujemy obrys wektorowy 28 297,4 × 11 920 mm; zaokrąglony opis 28 300 mm
  nie uzasadnia rozciągania modelu. Cyfry dziesiętne odczytu nie są tolerancją
  budowlaną.
- Dokumentację wnętrz traktujemy jako źródło aranżacji kuchni, salonu, spiżarni
  i wiatrołapu. Nie dopowiadamy szczegółowych projektów pozostałych pokoi.
- Konflikt źródeł otrzymuje jawny status; nie staje się „pomiarem” po zmianie
  koloru ostrzeżenia albo po pozytywnym teście oprogramowania.
- Dalsze dopracowanie ogrodu i Google ma mniejszy priorytet niż odbiór bryły.

## Jak uzupełnić pomiar

Dla każdej wartości zapisz: identyfikator pomieszczenia/elementu, co i między
jakimi punktami zmierzono, wynik w mm, datę, sposób pomiaru, źródło
(zdjęcie/szkic/protokół) i rozpoznaną niepewność. Przykład struktury opisu:

| Pole | Do wpisania |
| --- | --- |
| Element | np. `DR03`, jednoznacznie wskazany na rzucie |
| Wielkość | próg względem gotowej posadzki części mieszkalnej |
| Wynik, mm | — |
| Data i źródło | — |
| Niepewność / uwaga | — |
| Decyzja projektowa | przyjąć pomiar / odrzucić / wykonać ponownie |

Nie zamawiaj zabudowy na podstawie samej pozornej precyzji siatki. Odbiór bazy
wnętrza wymaga potwierdzenia gotowych lic, otworów, posadzek, sufitów i istotnych
przyłączy. Kontrole programu pokazują niespójności modelu, a nie stan budowy.

## Źródła i zakres historii

Główne dokumenty mają identyfikatory `architecture-primary` i `interior-design`
w [rejestrze źródeł](../sources/manifest.yaml). Odnotowane ustalenia z budowy są
osobnymi wpisami `user-*`. Historia rozmów dostępna podczas audytu była
częściowa; brak znalezionej wypowiedzi nie jest dowodem, że dana zmiana nigdy
nie została uzgodniona.
