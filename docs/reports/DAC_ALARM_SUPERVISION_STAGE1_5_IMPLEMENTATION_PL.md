# Stage 1.5 — alarmy i nadzór komunikacji z DAC

Data: 2026-08-01

Gałąź: `agent/dac-alarm-supervision-stage1-5`

Baza: `main` po integracji PR #1, commit `54e61c4756a7bf73a8f9d838490ea22372d4b325`.

## Cel

Dodać do `ventilation-core` rzeczywisty nadzór komunikacji I²C z DFRobot DFR0971 / GP8403 oraz jawny, bezpieczny stan awaryjny dostępny dla przyszłego GUI, historii zdarzeń i integracji zewnętrznych.

## Najważniejsza zmiana względem Stage 1

Dotychczasowy okresowy `ping` sprawdzał wyłącznie, czy osobny proces sprzętowy odpowiada. Nie wykonywał żadnej transakcji I²C z DAC, dlatego odłączenie DFR0971 podczas bezczynności nie było wykrywane.

Stage 1.5 zastępuje ten test prawdziwym `probe()` urządzenia pod adresem `0x58`.

## Model stanu

Do stanu rdzenia dodano:

- tryb `FAULT`,
- `output_state_known`,
- `consecutive_hardware_failures`,
- `active_alarms`,
- alarm `DAC_COMMUNICATION_LOST` o poziomie `critical`,
- czas aktywacji alarmu,
- ostatni komunikat błędu,
- liczbę kolejnych wystąpień.

## Polityka wykrywania

### Okresowy health-check

- wykonywany domyślnie co 1 sekundę,
- wykonuje rzeczywisty odczyt I²C z GP8403,
- po pierwszym błędzie natychmiast ustawia `output_state_known: false`,
- blokuje nowe nastawy do czasu bezpiecznego odzyskania,
- alarm krytyczny aktywuje po 3 kolejnych nieudanych próbach.

### Błąd komendy wykonawczej

Błąd podczas `set` lub `stop` jest traktowany jako bezpośrednia awaria wykonawcza i aktywuje alarm natychmiast, bez oczekiwania na trzy cykle.

## Zachowanie podczas awarii

- rdzeń nie twierdzi, że wyjścia mają 0 V,
- ostatnie zadane napięcia pozostają jedynie ostatnim poleceniem, nie potwierdzonym stanem fizycznym,
- `output_state_known` przyjmuje `false`,
- nowe komendy nastaw są odrzucane,
- po osiągnięciu progu tryb przechodzi w `FAULT`,
- usługa oraz proces sprzętowy pozostają uruchomione, aby móc wykryć powrót urządzenia.

## Bezpieczne odzyskanie

Po ponownym wykryciu DAC system:

1. ponownie sonduje GP8403,
2. ponownie ustawia zakres 10 V,
3. bezwarunkowo zapisuje 0 V na obu kanałach,
4. ustawia stan `STOP`,
5. nie przywraca poprzednich napięć,
6. czyści aktywny alarm,
7. ustawia `output_state_known: true` i `hardware_ready: true`.

## Brak DAC podczas startu

Brak odpowiedzi z DAC nie kończy już procesu `ventilation-core`. Proces sprzętowy pozostaje aktywny, a rdzeń startuje w stanie `FAULT` z alarmem `DAC_COMMUNICATION_LOST`. Po podłączeniu urządzenia następuje automatyczna procedura bezpiecznego odzyskania do 0 V / 0 V.

## Restart workera sprzętowego

Restart osobnego procesu sprzętowego nie może pozostać niewidoczny dla warstwy aplikacyjnej. Po wykryciu ponownego uruchomienia workera zwykłe komendy są odrzucane, a rdzeń musi przejść przez bezpieczne odzyskanie. Zapobiega to sytuacji, w której DAC został już wyzerowany przez nowy worker, ale aplikacja nadal raportowałaby wcześniejszy tryb `MANUAL`.

## Testy automatyczne

Lokalna walidacja implementacji:

```text
Ran 18 tests
OK
```

Dodatkowo wszystkie moduły `src` przechodzą `python3 -m compileall`.

Testy obejmują m.in.:

- rzeczywisty odczyt magistrali w `probe()`,
- mapowanie błędu I²C na wyjątek GP8403,
- stan nieznany po pierwszym błędzie,
- alarm po trzech błędach okresowych,
- natychmiastowy alarm po błędzie komendy,
- blokadę nastaw podczas awarii,
- start bez dostępnego DAC,
- odzyskanie zawsze do `STOP`,
- brak automatycznego przywrócenia wcześniejszej nastawy,
- odrzucenie zwykłej komendy po restarcie workera do czasu bezpiecznego odzyskania.

## Świadome ograniczenie fizyczne

Jeżeli komunikacja I²C zostanie utracona przy niezerowym wyjściu, oprogramowanie nie ma możliwości wymuszenia 0 V. DAC może utrzymać poprzednią wartość, dopóki jest zasilany. Dlatego stan jest oznaczany jako nieznany i wymagane jest późniejsze bezpieczne odzyskanie.

Pełne sprzętowe fail-safe dla takiego przypadku wymagałoby dodatkowego elementu elektrycznego odcinającego lub zerującego sygnał 0–10 V niezależnie od GP8403.

## Kolejność dalszych etapów

1. Stage 1.5 — walidacja alarmów i nadzoru DAC na CM5.
2. Stage 2 — RS-485 bring-up i osobny proces komunikacyjny.
3. Stage 3 — wspólny model alarmów urządzeń RS-485, oparty na fundamencie Stage 1.5.

## Kryterium zakończenia Stage 1.5

Etap można zakończyć po fizycznym potwierdzeniu na CM5:

- wykrycia odłączenia DAC,
- widocznego alarmu i trybu `FAULT`,
- pozostania usługi w stanie `active (running)`,
- automatycznego odzyskania po podłączeniu,
- wymuszenia `STOP / 0 V / 0 V`,
- braku samoczynnego uruchomienia fana.
