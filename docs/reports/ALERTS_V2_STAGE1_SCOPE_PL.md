# Alerty V2 — Stage 1

## Cel

Przebudować warstwę operatorską zakładki **ALERTY** bez przenoszenia logiki diagnostycznej z `ventilation-core` do GUI.

## Granica architektoniczna

`ventilation-core` pozostaje jedynym źródłem prawdy dla:

- wykrywania i klasyfikacji alertów,
- poziomu ważności,
- cyklu życia aktywny / potwierdzony / zakończony,
- liczby wystąpień,
- trwałej historii SQLite.

GUI V2 tylko prezentuje dane z `/api/v1/alerts` i zapisuje potwierdzenie przez `/api/v1/alerts/ack`.

## Stage 1 — zakres UI

- czytelniejszy nagłówek i stan połączenia z rejestrem alertów,
- podsumowanie: aktywne, niepotwierdzone, historia,
- duże karty aktywnych alertów z priorytetem wizualnym,
- operator-friendly opis źródła bez zmiany klasyfikacji core,
- uporządkowana historia z filtrowaniem po stanie/ważności,
- zachowanie globalnego modala dla aktywnych niepotwierdzonych alertów,
- brak zmian w logice sterowania, sprzęcie i automatyce,
- zachowanie globalnego watchdoga komunikacji CM5.

## Zasady bezpieczeństwa

- brak generowania nowych alertów po stronie GUI,
- brak oceny `sensor_bus`, `aero_bus`, TACHO itp. w JS,
- brak automatycznego potwierdzania,
- przy braku komunikacji CM5 nadrzędny jest pełnoekranowy watchdog komunikacji,
- nie zmieniamy `ventilation-core` w tym etapie.
