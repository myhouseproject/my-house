# Źródła modelu

[`manifest.yaml`](manifest.yaml) nadaje źródłom stabilne identyfikatory i zapisuje
SHA-256 plików. Moduły odwołują się do `source_id`, a nie do przypadkowej nazwy
załącznika. Numery stron odnoszą się do stron PDF, licząc od 1.

| Katalog / wpis | Zawartość |
| --- | --- |
| `documents/` | Dokumenty już wcześniej śledzone w repozytorium, przeniesione bez zmiany zawartości |
| `photos/` | Zdjęcia już wcześniej śledzone w repozytorium |
| `architecture-primary` | Zewnętrzny projekt budowlany, 31 stron; identyfikowany przez hash, bez publikacji załącznika |
| `user-*` | Ustalenia odnotowane w historii projektu; nie są protokołem pomiarowym |
| `model-legacy-heights` | Zastane wysokości bez potwierdzonego pochodzenia |

Status `project` oznacza dokumentację projektową, `ordered` dane produktu
z zamówienia/oferty, `measured` udokumentowany pomiar, `assumed` założenie,
a `derived` wynik obliczenia. Status źródła nie przechodzi automatycznie na
wszystkie parametry elementu: zamówiona szerokość okna nie potwierdza jego
położenia, parapetu ani luzu montażowego.

`availability: external` oznacza źródło poza repozytorium. Brak lokalnego PDF-u
nie blokuje budowy z zapisanej ekstrakcji, ale jego ponowne odczytanie wymaga
dostarczenia pliku o zgodnym SHA-256. `unavailable` przy ustaleniu historycznym
oznacza brak odrębnego dokumentu źródłowego do kontroli; opis pozostaje jawny.

Nie ustala się pierwszeństwa dokumentów na podstawie nazwy pliku. Dla
`architecture-primary` nazwa zawiera datę 2024-02-01, a okładka lipiec 2023.
Rozbieżności rozstrzyga potwierdzona rewizja lub pomiar zapisany w
[rejestrze decyzji](../docs/DECYZJE_I_POMIARY.md).

Obecne porządkowanie nie dodaje nowych prywatnych dokumentów do publicznego
repozytorium i nie usuwa wcześniejszych kopii z historii Git. Decyzja o zakresie
publicznych źródeł oraz ewentualnej zmianie historii jest odrębna od organizacji
katalogów.
