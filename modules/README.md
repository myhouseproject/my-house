# Moduły projektu

Docelowy kontrakt każdego modułu:

```
input/        źródła i manifest provenance
module.yaml   pełna deklaracja parametrów
src/          interpreter/generator
output/       artefakty generowane
```

Pierwszy etap migracji nie przenosi jeszcze dużych plików. `module.yaml` wskazuje
dotychczasowe źródła prawdy i entrypointy, aby najpierw ustabilizować granice i
zależności bez psucia działającego portalu.

Statusy: `legacy` = parametry głównie w kodzie/starych plikach; `hybrid` =
stan częściowo deklaratywny; `declarative` = YAML jest źródłem prawdy.
