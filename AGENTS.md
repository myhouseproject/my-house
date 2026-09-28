# Zasady pracy człowieka i AI

Przed zmianą przeczytaj `project.yaml` i `module.yaml` wybranego modułu.

1. Input (PDF/JPG/pomiary/usługi) jest dowodem, nie kodem.
2. Po migracji modułu nowy parametr trafia najpierw do YAML.
3. Nie edytuj ręcznie artefaktów generowanych: GLB, KMZ, duże JSON-y sceny i HTML.
4. Nie zgaduj brakujących danych. Oznaczaj: project / measured / ordered / assumed / derived.
5. Geometria deklaratywna używa domyślnie mm; scena runtime metrów.
6. Respektuj zależności z `project.yaml`.
7. Status `legacy`, `hybrid`, `declarative` mówi, gdzie aktualnie jest źródło prawdy.
8. Ukryte stałe geometryczne i materiałowe w generatorach są długiem migracyjnym.
9. Zmiana parametru nie może wymagać ręcznej korekty wygenerowanego modelu.
10. Przed PR-em uruchom `python scripts/project.py validate` i testy zmienionego modułu.

Preferowany cykl AI: wybierz moduł → przeczytaj input i deklarację → zmień YAML →
waliduj → wygeneruj → uruchom testy → zapisz artefakty.
