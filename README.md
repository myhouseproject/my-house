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

Na telefonie **jeden palec obraca model**, a **dwa palce przesuwają i przybliżają**.
Przycisk zmiany gestu pozwala przesuwać model także jednym palcem.
**Punkt obrotu** → dotknij widocznego elementu, aby ustawić środek obracania.
**Spacer** włącza perspektywę z wysokości oczu: przeciągaj, aby się rozglądać,
przytrzymuj strzałki, aby iść. Na komputerze działają WASD i strzałki.
**Zakończ spacer** lub Escape przywraca poprzedni widok.
Ruch respektuje ściany, otwory drzwiowe, obrys domu i poziomy podłóg;
nie symuluje kolizji z meblami, szkłem ani skrzydłami drzwi.
Panel **Narzędzia** na małym ekranie rozwija pomiar i przekrój.

**Sypialnia** otwiera R08 od południa; adresy to `?view=bedroom` oraz
`?view=bedroom-top`. Odtworzono oliwkowy wariant z ujęć 1000053191/1000053190:
łóżko 180 × 200 cm, tapicerowany zagłówek, żurawie nad łóżkiem, wiszące szafki,
zasłonę przy HST, trzy pierścienie oświetlenia oraz toaletkę z pufem.
Zachowano otwory DR06, DR12 i DR13 oraz przeszklenie W07/W08; toaletka mieści
się pomiędzy drzwiami wejściowymi i drzwiami do łazienki. Geometria mebli i
tekstyliów jest koncepcyjna, zapisana w `modules/06_interior/extracts/bedroom.yaml`.
Tapeta z żurawiami jest interpretacją przygotowaną przez imagegen, widoczną
w portalu, przenośnym HTML, GLB i Cycles. Jej źródło to
`assets/textures/bedroom-cranes.jpg`; nie wskazuje konkretnego produktu.
Ujęcie 1000053189 pozostaje referencją alternatywnego, beżowego wykończenia.

Wybór **Pomieszczenie** udostępnia także autorskie propozycje umeblowania:

| Widok | Pomieszczenie | Wyposażenie |
|---|---|---|
| `?view=wardrobe` | R09 Garderoba | Zabudowa U, półki, drążki, szuflady, lustro i ławka |
| `?view=kids-room-1` | R04 Pokój dziecięcy 1 | Łóżko 90×200 cm, biurko 160×60 cm, szafa i regał; szałwia |
| `?view=kids-room-2` | R05 Pokój dziecięcy 2 | Lustrzany układ łóżka, biurka i szafy; zgaszony błękit |
| `?view=office` | R15 Gabinet | Biurko z bocznym światłem, fotel, sofa i przechowywanie |

Każdy adres ma wariant rzutu z końcówką `-top`. Nowe meble są koncepcją
`assumed`: projekt wnętrza na s.49 nie zawiera umeblowania tych pokoi.
Gabaryty pomieszczeń, aktywne otwory i poziomy pozostają zgodne z modelem.
Parametry zapisano w `wardrobe.yaml`, `kids-room-1.yaml`, `kids-room-2.yaml`
i `office.yaml` w katalogu `modules/06_interior/extracts`.

**Mała łazienka** otwiera wspólny widok R03 i pralni R02; adresy to
`?view=small-bathroom` oraz `?view=small-bathroom-top`. Od wejścia od wschodu
prysznic znajduje się po lewej, WC na istniejącej przegrodzie pralni, a szafka
z umywalką i okrągłym lustrem na prawej ścianie. W pralni odtworzono blat w L,
front żaluzjowy, grzejnik i suszarkę sufitową. Aktualna kolorystyka według
zdjęć 1000022855/1000022852 to jasny ciepły beton, ciemniejszy naturalny dąb
i chromowana armatura. Fronty mebli oraz drewnopodobna strefa prysznica
są utrzymane w tym samym brązie. Wcześniejsze ujęcia pozostają podstawą
układu, ryflowania i zabudowy pralni. Nie określono modeli ani
rozmieszczenia urządzeń schowanych za frontami, ponieważ zdjęcia ich nie pokazują.
Parametry wyposażenia i podwieszanego sufitu 2600 mm są koncepcyjne i znajdują
się w `modules/06_interior/extracts/small-bathroom.yaml`.

Przycisk **📷 Zdjęcie i render HQ** zapisuje PNG bieżącego podglądu albo ustawienia
kamery do Cycles. Zapis PNG jest obrazem lekkiego podglądu; nie oblicza nowego
oświetlenia. **Render HQ** kopiuje kamerę, proporcje, widoczne elementy i przekrój.
Na GitHub otwórz **Render wybranego widoku → Run workflow**, wklej dane w
`camera_json`, wybierz `preview` lub `final` i uruchom. Pusta kamera oznacza
domyślny widok łazienki od wejścia. Wynik PNG, plik `.blend` i manifest są w
paczce **Artifacts**, dostępnej przez 14 dni. Potrzebne jest konto z prawem zapisu
do repozytorium. Zadanie uruchamia się wyłącznie ręcznie, nie przy każdym wejściu
na stronę; portal nie przechowuje tokenów GitHub. Limit dłuższego boku to 2000 px,
proporcje kadru są zachowane; szybkie `preview` ma maksymalnie 1000 px i mniej próbek.
Render korzysta z aktualnej wersji projektu.

**Łazienka** otwiera wyposażoną łazienkę 7 od strony wejścia;
**Łazienka z góry** pokazuje jej rozmieszczenie z góry. Bezpośrednie adresy
to `?view=bathroom` i `?view=bathroom-top`. Układ odtwarza ujęcia referencyjne inwestora:
dwie umywalki i wisząca szafka na ścianie wschodniej, WC w płytkiej zabudowie
na zachodniej, a wanna i prysznic w tylnej strefie oddzielonej pełnym przeszkleniem
z parą środkowych drzwi przesuwnych. Dodatkowe ujęcia określają też położenie
baterii wanny przy oknie, grzejnika i wieszaków. Przedścianka prysznica wraz z wnęką
została usunięta na życzenie inwestora; płytki i armatura są przy właściwej ścianie.
Wariant jasny jest referencją dla baterii ściennych umywalek; ciemne ujęcia pokazują
alternatywne baterie nablatowe. Kolorystyka modelu pozostaje robocza.
Elementy są częścią sceny oraz eksportów wnętrza. Ich parametry znajdują się w
`modules/06_interior/extracts/bathroom.yaml`.
Gabaryty wyposażenia i materiały są roboczą koncepcją dopasowaną do R07;
nie wybrano jeszcze konkretnych produktów. Jasny wariant wykończenia obejmuje
płytki o umownym formacie 120×60 cm z fugą 2 mm, malowane ściany, kremowe fronty,
mosiężne detale, żaluzje i oświetlenie. Podział płytek jest geometrią modelu,
a wzór kamienia w renderze jest proceduralną propozycją, nie teksturą wybranego produktu.
Parametry zapisano w `modules/06_interior/extracts/bathroom-finishes.yaml`.
Przyłącza, odpływy oraz
kolizję otwieranego skrzydła narożnego okna trzeba potwierdzić przed wykonaniem.

Render łazienki w Blenderze/Cycles korzysta z tej samej sceny lokalnej, z rzeczywistym
szkłem, odbiciami luster, miękkim światłem i proceduralnymi materiałami. Lekki podgląd
WWW pokazuje geometrię i kolory, a Cycles służy do oceny wyglądu wykończenia.
Osobne środowisko renderowania nie jest wymagane do budowania modelu i strony:

```bash
python3.11 -m venv ../render-venv
../render-venv/bin/python -m pip install -r requirements_render.txt
python scripts/build.py --scope interior --test
../render-venv/bin/python scripts/render_bathroom.py \
  --scene build/current/scena_lokalna.json --camera entrance --quality final \
  --output ../renders/bathroom
```

`--quality preview` tworzy szybszą próbę; `--camera reverse` wybiera widok od strony
wanny. Wyniki to obraz PNG, edytowalna scena `.blend` oraz JSON z pochodzeniem
geometrii i ustawieniami. Materiały, kamery, światło i rozdzielczość można zmieniać w
`modules/06_interior/extracts/bathroom-render.yaml`. Renderowanie nie zmienia
geometrii źródłowej; wygładzanie i delikatne zaokrąglenia są modyfikatorami sceny renderującej.

Mała łazienka i pralnia mają osobną recepturę wykończenia, lamp i kamer:

```bash
../render-venv/bin/python scripts/render_bathroom.py \
  --scene build/current/scena_lokalna.json \
  --config modules/06_interior/extracts/small-bathroom-render.yaml \
  --camera entrance --quality final --output ../renders/small-bathroom
```

Kamera `laundry` pokazuje część pralnianą. Wzór kamienia i drewna jest
proceduralną interpretacją zdjęć, nie teksturą konkretnego wybranego produktu.

Sypialnia ma własny profil światła i kamer:

```bash
../render-venv/bin/python scripts/render_bathroom.py \
  --scene build/current/scena_lokalna.json \
  --config modules/06_interior/extracts/bedroom-render.yaml \
  --camera entrance --quality final --output ../renders/bedroom
```

Kamera `reverse` pokazuje toaletkę i przejścia z przeciwnej strony.

Garderoba, oba pokoje dziecięce i gabinet mają analogiczne profile
`wardrobe-render.yaml`, `kids-room-1-render.yaml`, `kids-room-2-render.yaml`
i `office-render.yaml`. W powyższym poleceniu wystarczy podmienić `--config`
i katalog `--output`. Ich materiały oraz światła są również rejestrowane
przy renderowaniu kadru wyeksportowanego z portalu (`--scope house`).

Własny kadr zapisany w portalu jako JSON można wyrenderować lokalnie:

```bash
../render-venv/bin/python scripts/render_bathroom.py \
  --scene build/current/scena_lokalna.json --camera-file kamera.json \
  --scope house --quality final --output ../renders/moj-kadr
```

Plik kamery zachowuje pozycję, kierunek, obrót, perspektywę lub skalę rzutu
ortogonalnego, proporcje i rozdzielczość obrazu. Jeśli zawiera listę widocznych
elementów oraz przekrój, renderer odtwarza również tę widoczność i cięcia.
Obrazy z podglądu WWW i Cycles mają różne światło i materiały; eksport kamery
nie zamienia zrzutu ekranu w render. Kadr należy łączyć z tą samą wersją sceny.
`--scope house` obejmuje geometrię domu bez przycinania do łazienki; dopracowane
materiały i lampy dotyczą obecnie R07, R02/R03 oraz sypialni R08. Pozostałe pomieszczenia korzystają z
kolorów/PBR modelu i światła otoczenia, więc wymagają dalszego opracowania.
`--scope bathroom` ogranicza scenę do pomieszczeń wskazanych w recepturze renderowania
i ich najbliższych ścian; domyślna receptura dotyczy R07.
Domyślnie pomijane są robocze bloki, symbole i powierzchnie referencyjne.
Jawna lista widocznych elementów w kadrze z portalu ma pierwszeństwo w trybie
`house`, również gdy pokazuje bazową podłogę lub bloki zamiast wykończenia.

`--validate-only` sprawdza scenę, kamerę i widoczność bez importowania Blendera.
`--save-only` zapisuje `.blend` z wybraną kamerą bez liczenia obrazu; ten plik
można otworzyć w Blenderze i uruchomić **Render → Render Image** (F12).
Wyniki własnego kadru mają nazwy `house-portal-final.png`, `.blend` i `.json`;
manifest zawiera skróty sceny, konfiguracji i wejściowego pliku kamery.

Kontrakt kamery v1: `schema_version: 1`, `kind: "dom-render-camera"`,
`coordinate_frame: "building_local"`, `units: "m"`, `up_axis: "Z"`, wektory
`eye`, `target`, `up`, `aspect_ratio` i `resolution: [szerokość, wysokość]`.
`projection: "perspective"` wymaga `vertical_fov_degrees`, a
`projection: "orthographic"` — `orthographic_height_m`. Opcjonalne pola to
`visible_part_names`, `section_height_m` (poziom Z budynku) i `clip_bounds_m`
(`[[minX,minY,minZ],[maxX,maxY,maxZ]]`, w tym samym układzie lokalnym).
Plik nie zawiera poleceń ani kodu wykonywalnego. Renderer odrzuca nieznane
ramy, nieprawidłowe wektory, nazwy spoza sceny i nadmierne rozdzielczości.

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
