# CM5 AERO BUS — Stage 3B — raport końcowy i handoff

Data: 2026-08-11

## Status

Stage 3B zakończony funkcjonalnie i zwalidowany sprzętowo na docelowym CM5 oraz rekuperatorze COMPIT NANO COLOR 2 v6.30 / AERO 4A2.

Gałąź implementacyjna:

- `agent/cm5-aero-bus-stage3b-control`

Punkt bazowy Stage 3B:

- `main` @ `d88799bdb15b091ab58ac250fcb97ecf35295e9e`

Draft PR:

- `#19 CM5 AERO BUS Stage 3B: guarded production control`

## Cel Stage 3B

Dodać kontrolowane sterowanie rekuperatorem przez istniejący AERO BUS, bez naruszania niezależności DAC i SENSOR BUS.

Transport pozostaje zgodny ze Stage 3A:

- UART: `/dev/ttyAMA4`
- Modbus RTU
- 9600 bit/s
- 8N1
- slave 44

Stage 3B dodaje FC06 wyłącznie dla dwóch potwierdzonych rejestrów sterujących:

- ADR `1080` — bieg wentylacji: `0`, `1`, `2`, `3`
- ADR `1081` — airing/wietrzenie: `0`, `1`

## Architektura sterowania

### Jeden właściciel UART

`aero_bus_worker` pozostaje jedynym procesem otwierającym `/dev/ttyAMA4`.

Sterowanie nie tworzy drugiej ścieżki dostępu do RS485. Komendy trafiają do workera przez wewnętrzną kolejkę, a wykonanie FC06 odbywa się wyłącznie w procesie właściciela UART.

Kolejka sterowania ma pojemność 1. Równoległe polecenie jest odrzucane jako już oczekujące/wykonywane.

### Kontrakt bezpieczeństwa

Przed zapisem wykonywane są następujące kroki:

1. AERO BUS musi być `worker_alive=true`, `ready=true`, `online=true`, `usable=true`.
2. Odczytywana jest poprzednia wartość rejestru sterującego.
3. Poprzednia wartość musi należeć do znanego zakresu:
   - `1080`: `0..3`
   - `1081`: `0..1`
4. Odczytywana jest moc obu wentylatorów (`2033`, `2034`) jako baseline.
5. Wykonywany jest pojedynczy FC06.
6. Odpowiedź FC06 musi być dokładnym echem żądania.
7. Następnie wykonywany jest FC03 readback rejestru sterującego.
8. Fizyczne wykonanie jest potwierdzane osobno na podstawie zmiany mocy `2033/2034`.

ACK protokołu nie jest traktowany jako fizyczne wykonanie.

### Timeout i obserwacja fizyczna

- maksymalny czas potwierdzenia fizycznego: `60 s`
- interwał obserwacji: `2 s`

Jeżeli po zapisie wystąpi błąd protokołu, niepoprawny readback albo brak potwierdzenia fizycznego w limicie czasu, executor próbuje przywrócić poprzednią wartość rejestru i potwierdza rollback odczytem FC03.

### Stan runtime

`AeroBusState` raportuje dodatkowo:

- `control_busy`
- `last_control_result`

`last_control_result` zawiera m.in.:

- rodzaj komendy,
- adres rejestru,
- wartość docelową,
- poprzednią wartość,
- readback,
- baseline mocy,
- zaobserwowaną moc,
- `physical_confirmation`,
- `recovered`,
- błąd wykonania.

## CLI / Unix API

Dodane polecenia:

```bash
PYTHONPATH=src python3 -m ventilation_core.ctl aero-speed 0
PYTHONPATH=src python3 -m ventilation_core.ctl aero-speed 1
PYTHONPATH=src python3 -m ventilation_core.ctl aero-speed 2
PYTHONPATH=src python3 -m ventilation_core.ctl aero-speed 3

PYTHONPATH=src python3 -m ventilation_core.ctl aero-airing on
PYTHONPATH=src python3 -m ventilation_core.ctl aero-airing off
```

Wejścia spoza kontraktu są odrzucane przed workerem i nie generują FC06.

## Walidacja programowa

Końcowa walidacja CM5 po wszystkich poprawkach:

- HEAD przed raportem: `99129254d6330f60dbbc716e5940210f8d1ec12c`
- `python3 -m unittest discover -s tests`
- wynik: `Ran 138 tests ... OK`

GitHub Actions:

- `Ventilation Core Tests` — PASS na kolejnych checkpointach Stage 3B
- końcowy checkpoint przed raportem: run `#717` — SUCCESS

Testy obejmują m.in.:

- FC06 happy path,
- CRC i format odpowiedzi,
- Modbus exception response,
- exact echo mismatch,
- readback mismatch,
- timeout fizycznego wykonania,
- rollback poprzedniej wartości,
- niedozwolone adresy i wartości,
- nieznany stan poprzedni — odmowa bez FC06,
- AERO not-ready — odmowa bez FC06,
- pojedynczą kolejkę sterowania,
- `control_busy`,
- `last_control_result`,
- CLI/API dla speed i airing,
- rozłączenie klienta Unix socket bez tracebacku.

## Walidacja sprzętowa

Walidacja została wykonana na docelowym CM5 i docelowym rekuperatorze.

Panel NANO potwierdzał poprawną reakcję podczas całego testu.

### Bieg 1

Przejście:

- ADR `1080`: `0 -> 1`
- FC03 readback: `1`
- baseline: `fan_1=0%`, `fan_2=0%`
- observed: `fan_1=30%`, `fan_2=30%`
- `state=succeeded`
- `physical_confirmation=true`
- `recovered=false`
- `error=null`

Powrót:

- ADR `1080`: `1 -> 0`
- readback: `0`
- `30/30% -> 0/0%`
- PASS

### Bieg 2

Przejście:

- ADR `1080`: `0 -> 2`
- readback: `2`
- `0/0% -> 60/60%`
- `physical_confirmation=true`
- PASS

Powrót:

- `2 -> 0`
- `60/60% -> 0/0%`
- PASS

### Bieg 3

Przejście:

- ADR `1080`: `0 -> 3`
- readback: `3`
- `0/0% -> 90/90%`
- `physical_confirmation=true`
- PASS

Powrót:

- `3 -> 0`
- `90/90% -> 0/0%`
- PASS

### Airing

ON:

- ADR `1081`: `0 -> 1`
- readback: `1`
- `0/0% -> 100/100%`
- `physical_confirmation=true`
- PASS

OFF:

- ADR `1081`: `1 -> 0`
- readback: `0`
- `100/100% -> 0/0%`
- `physical_confirmation=true`
- PASS

## Końcowy stan po walidacji sprzętowej

AERO BUS:

- `ready=true`
- `worker_alive=true`
- `worker_restarts=0`
- `online=true`
- `usable=true`
- `control_busy=false`
- `fan_1_percent=0`
- `fan_2_percent=0`
- `communication_errors=0`
- `consecutive_failures=0`
- `invalid_samples=0`

SENSOR BUS:

- oba węzły online i usable
- `worker_restarts=0`
- oba węzły bez communication errors
- oba węzły bez invalid/stale measurements

Core/DAC:

- `mode=STOP`
- supply DAC: `0.0 V`
- extract DAC: `0.0 V`
- `hardware_ready=true`
- `output_state_known=true`
- `consecutive_hardware_failures=0`
- `active_alarms=[]`

Stage 3B nie naruszył domeny błędów SENSOR BUS ani DAC.

## Unix socket — poprawka po walidacji

Podczas intensywnego testu CLI w journalu pojawiały się tracebacki:

- `ConnectionResetError: Connection lost`
- `Unhandled exception in client_connected_cb`

Nie były związane z AERO/Modbus ani z wykonaniem FC06. Powodem było zamknięcie krótkiego połączenia klienta Unix socket podczas `writer.drain()` / zamykania odpowiedzi.

Obsługa klienta została poprawiona tak, aby reset/zerwanie klienta było normalnym zdarzeniem transportowym i nie generowało nieobsłużonego wyjątku.

Końcowy postcheck:

- wygenerowano wielokrotny ruch `aero`, `sensors`, `status`
- `ventilation-core.service`: active
- `PASS: no Unix socket traceback`
- journal po restarcie: czysty
- AERO: 3/3 successful polls, 0 communication errors
- SENSOR BUS: oba węzły 8/8 successful polls, 0 communication errors
- core: STOP / 0 V / brak alarmów

## Potwierdzone mapowanie mocy

Na tej konfiguracji NANO/AERO potwierdzono podczas Stage 3B:

- speed `0` -> `0% / 0%`
- speed `1` -> `30% / 30%`
- speed `2` -> `60% / 60%`
- speed `3` -> `90% / 90%`
- airing `1` -> `100% / 100%`

Jest to zaobserwowane zachowanie konkretnego docelowego zestawu i może być używane do diagnostyki oraz potwierdzania wykonania.

## Granice Stage 3B

Stage 3B daje produkcyjny, kontrolowany mechanizm wykonania pojedynczych poleceń AERO, ale nie dodaje automatycznej logiki jakości powietrza.

W szczególności Stage 3B nie uruchamia:

- automatycznego doboru biegu z PM/VOC/NOx,
- decyzji AI sterujących rekuperatorem,
- harmonogramów pracy,
- złożonych sekwencji wentylacji,
- sprzężenia AERO z DAC 0–10 V.

AI pozostaje warstwą advisory i nie ma bezpośredniej ścieżki do FC06.

## Handoff

Po scaleniu Stage 3B do `main` kolejne prace powinny traktować następujące elementy jako ustalony kontrakt:

1. `/dev/ttyAMA4` ma jednego właściciela — `aero_bus_worker`.
2. Produkcyjne zapisy AERO przechodzą tylko przez jego kolejkę.
3. Dozwolone FC06:
   - `1080` = `0..3`
   - `1081` = `0..1`
4. Każdy zapis wymaga:
   - exact echo,
   - FC03 readback,
   - osobnego fizycznego potwierdzenia.
5. Timeout fizycznego wykonania/powrotu: `60 s`.
6. Polling potwierdzenia: `2 s`.
7. Nieznany stan poprzedni oznacza odmowę bez zapisu.
8. Błąd AERO control nie może faultować DAC ani SENSOR BUS.
9. Core/DAC safety pozostaje niezależne i kończy walidację w `STOP / 0 V`.
10. Automatyka jakości powietrza jest osobnym, późniejszym etapem.

Stage 3B można uznać za zakończony po końcowym CI dla commitu zawierającego ten raport oraz po świadomej decyzji o oznaczeniu Draft PR #19 jako Ready/Merge.