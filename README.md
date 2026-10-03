# Dom — baza do projektu wnętrza

Parametryczny model domu, wnętrza i otoczenia. Parametry edytuje się w YAML;
geometrię, eksporty i portal generuje się wspólnie. Priorytetem jest lokalny,
wymiarowy model wnętrza. [Portal](https://rutkala.github.io/dom/) pokazuje
opublikowane wydanie.

Model pozostaje bazą projektową. Pochodzenie wysokości wykonawczych, osadzenie
stolarki, wykończenia i przejście do garażu wymagają potwierdzenia. Ich jawne
statusy oraz dane potrzebne do zamknięcia etapu są w
[rejestrze decyzji i pomiarów](docs/DECYZJE_I_POMIARY.md).

## Szybki start

Środowisko budowy: Python 3.12; opcja `--test` wymaga także Node.js
(w CI używana jest wersja 22).

```bash
python -m pip install -r requirements_portal.txt
python scripts/project.py validate
python scripts/build.py --scope interior
```

Budowa wnętrza korzysta z zapisanych źródeł i nie pobiera map. Pełne wydanie
z otoczeniem oraz kontrolami:

```bash
python scripts/build.py --scope full --test
```

Pełna budowa potrzebuje danych transformacji wysokości; wykorzystuje istniejącą
kopię, a brakujące dane może pobrać. Zestaw wyników powstaje w `build/current`;
`dist/` zawiera pliki przeznaczone do publikacji. Błąd budowy nie powinien
zastępować ostatniego poprawnego wydania. Nie edytuj ręcznie eksportów.

## Pliki do pracy

| Wynik | Przeznaczenie |
| --- | --- |
| `dom_powloka.glb` | Lokalne ściany, podłogi i stolarka, bez wyposażenia i dachu |
| `dom_wnetrze.glb` | Lokalny model z wizualnym wariantem wyposażenia |
| `dom_wnetrze_bloki.glb` | Lokalny model z blokami roboczymi wyposażenia |
| `dom_bryla.glb` | Pełny widok domu i otoczenia w wydaniu `full` |
| `scena_lokalna.json` | Kanoniczna lokalna geometria domu; metry, Z w górę |
| `dom_model.obj` + `dom_materialy.mtl` | Lokalny model z wyposażeniem; pliki należy zachować razem |
| `kontrola_modelu.json`, `lista_elementow.json` | Kontrole i lista elementów danego wydania |
| `build-manifest.json`, `sumy_sha256.txt` | Identyfikacja wejść oraz integralność wyników |
| `walidacja_projektu.json` | Błędy danych i otwarte decyzje, oddzielone od kontroli siatek |
| `index.html`, `podglad_3d.html` | Portal i samodzielny podgląd |

Warianty wnętrza eksportują bloki lub elementy wizualne, bez nałożenia obu
zestawów. GLB można otworzyć w Blenderze przez **File → Import → glTF 2.0**.
Profile, meble i okucia są uproszczoną reprezentacją, jeśli nie ma danych
produkcyjnych. Historyczny STEP i jego raport są w `archive/model-2026-09-24/`. Nie są
aktualnym eksportem tego modelu; nie należy porównywać starego raportu BREP
z bieżącą sceną siatkową.

Lokalne GLB pomijają sufity i referencyjne lica wykończeń, aby pozostawić
czytelne wnętrze. Te dane są zachowane w scenie lokalnej, podglądzie i imporcie
Blendera; odniesienie wykończeń nie oznacza zatwierdzonego pomiaru pokoju.

## Praca w podglądzie i Blenderze

Otwórz `build/current/podglad_3d.html`. Widok wnętrza jest domyślny;
**Rzut 2D** pokazuje wnętrze bez otoczenia. **Pomiar 2 punktów** mierzy odległość
XY w lokalnym rzucie i przyciąga do narożników. **Przekrój poziomy** pozwala
zmienić wysokość cięcia. Można wybrać pokój, odczytać modelową wysokość
oraz status danych, a zaznaczoną ścianę ukryć i później przywrócić.
Pomiar modelu nadal wymaga porównania ze stanem wykonanym.

**Łazienka** otwiera wyposażoną łazienkę 7 od strony wejścia;
**Łazienka z góry** pokazuje jej rozmieszczenie z góry. Bezpośrednie adresy
to `?view=bathroom` i `?view=bathroom-top`. Układ odtwarza ujęcia referencyjne inwestora:
dwie umywalki i wisząca szafka na ścianie wschodniej, WC w płytkiej zabudowie
na zachodniej, a wanna i prysznic w tylnej strefie oddzielonej pełnym przeszkleniem
z parą środkowych drzwi przesuwnych. Dodatkowe ujęcia określają też położenie
baterii wanny przy oknie, wnęki prysznicowej, grzejnika i wieszaków.
Wariant jasny jest referencją dla baterii ściennych umywalek; ciemne ujęcia pokazują
alternatywne baterie nablatowe. Kolorystyka modelu pozostaje robocza.
Elementy są częścią sceny oraz eksportów wnętrza. Ich parametry znajdują się w
`modules/06_interior/extracts/bathroom.yaml`.
Gabaryty wyposażenia i materiały są roboczą koncepcją dopasowaną do R07;
nie wybrano jeszcze konkretnych produktów ani płytek. Przyłącza, odpływy oraz
kolizję otwieranego skrzydła narożnego okna trzeba potwierdzić przed wykonaniem.

Opcjonalny zapis natywnego pliku Blendera po budowie:

```bash
blender --background --python utworz_scene_Blender.py -- --variant visual
```

Skrypt odczytuje `build/current/scena_lokalna.json` i zapisuje
`build/current/dom_wnetrze_visual.blend`. Opcja `--variant` przyjmuje
`shell`, `blocks` lub `visual`; nazwa wyniku uwzględnia wariant.
`--root` wskazuje inny katalog wydania. Istniejącego pliku nie nadpisuje
bez `--overwrite`. Wymaga zainstalowanego Blendera; sam import GLB
nie potrzebuje tego skryptu. Zapis `.blend` nie był uruchomiony podczas
weryfikacji tego etapu.

## Wymiary i źródła

YAML używa milimetrów. Lokalna scena JSON i OBJ używają metrów, z osią Z
w górę. GLB używa metrów i osi Y w górę: `(x, y, z) = (X, Z, -Y) / 1000`
dla wejścia w mm. Lokalny poziom `Z=0` to gotowa posadzka części mieszkalnej.
Transformacja do mapy jest wykonywana na kopii sceny; nie ustala wymiarów
lokalnego eksportu wnętrza.

[Rejestr źródeł](sources/manifest.yaml) rozróżnia dokumentację, dane produktów,
pomiary i założenia. Aktualne zamówienia stolarki nie potwierdzają wymiarów
otworów ani parapetów. Robocze 2850 mm sufitu, 3100 mm muru, 4150 mm attyki
i oszacowanie poziomu garażu nie są oznaczone jako pomiar.

## Struktura i dalsza praca

- `sources/` — dokumenty, zdjęcia i rejestr pochodzenia;
- `modules/` — siedem modułów z konfiguracją i ekstrakcjami;
- `config/` — wspólny rejestr nierozstrzygniętych decyzji;
- `data/` — zapisane wejście terenu i ortofotomapa;
- `scripts/` — polecenia walidacji i budowy;
- `tests/` — kontrole geometrii, eksportów i podglądu;
- `docs/` — architektura, decyzje, referencje i oznaczone archiwum;
- `build/`, `dist/` — odtwarzalne wyniki i publikacja.

Zacznij od [mapy modułów](modules/README.md) i
[architektury](docs/ARCHITEKTURA_PROJEKTU.md). Po zmianie YAML uruchom walidację
i budowę właściwego zakresu. Raport poprawności siatki i zielone testy nie
zastępują porównania z pomiarem budynku.
Zakres napraw opisuje [status realizacji audytu](docs/AUDYT_REALIZACJA.md).
