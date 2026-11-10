# WVC AUTO V1 — awaria wejść → MANUAL bez blokowania operatora

Status: przygotowane w osobnej gałęzi. Do wdrożenia po bezpiecznym restarcie Core; nie oznacza dopuszczenia fizycznego AUTO.

## Przy utracie SEN55 lub AERO

1. Utrata SEN55 nr 1, nr 2, obu lub nieważny odczyt PM/VOC/NOx powoduje trwały HOLD i zmianę trybu na MANUAL.
2. Utrata dostępności AERO również powoduje MANUAL.
3. Core NIE wysyła nastaw zastępczych do EC ani AERO; pozostawia obecne wyjścia. Operator ustawia prędkości sam, bez PIN-u i bez blokady ręcznych nastaw i STOP.
4. Poprawa odczytu nie wznawia AUTO samoczynnie. Powrót do AUTO wymaga jawnego działania operatora i pełnego preflightu obu SEN55, AERO i TACHO.

## Zachowane zabezpieczenia

- Awaria TACHO lub krytyczna awaria sprzętowa: Core najpierw zatrzymuje oba EC, przechodzi w MANUAL i zapisuje błąd. Ręczne sterowanie pozostaje dostępne. Potwierdzenie takiej awarii wymagane jest do powrotu do AUTO, nie do ręcznych regulatorów.
- MANUAL nie oznacza gwarancji bezpiecznej wentylacji. Jeśli brak informacji o jakości powietrza, operator powinien przerwać procesy emisyjne do czasu sprawdzenia wentylacji.
- Nie można obejść sprzętowych błędów ani automatycznie włączyć AUTO bez zatwierdzonego commissioning; wszystkie dotychczasowe zabezpieczenia pozostają.

## Weryfikacja

- Testy jednostkowe: brak SEN55 1/2/obu, awaria AERO, zachowanie nastaw HIGH/MAX, trwały HOLD po restarcie, ręczne zmiany i STOP po awarii TACHO oraz brak samowznowienia.
- Testy nie wykonują poleceń do fizycznych urządzeń.
- Przed wdrożeniem wymagany bezpieczny moment na restart samego Core; nie należy przerywać bieżącej ręcznie ustawionej wentylacji.
