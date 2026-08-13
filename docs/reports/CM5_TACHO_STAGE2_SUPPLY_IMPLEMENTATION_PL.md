# CM5 TACHO Stage 2 — SUPPLY / VOUT0

Data: 2026-08-13

## Cel

Rozszerzyć zwalidowany wcześniej read-only pomiar TACHO kanału EXTRACT o drugi kanał dla wentylatora nawiewnego SUPPLY.

## Docelowe mapowanie

```text
SUPPLY control: DAC CH0 / VOUT0
SUPPLY TACHO:   GPIO17 / physical pin 11

EXTRACT control: DAC CH1 / VOUT1
EXTRACT TACHO:   GPIO27 / physical pin 13
```

Przewód CM5 <-> BOX wykonawczy:

```text
DB9 pin 8 -> GPIO17 -> TACHO dla VOUT0 / SUPPLY
DB9 pin 9 -> GPIO27 -> TACHO dla VOUT1 / EXTRACT
```

DB9 sterowania wentylatorami:

```text
pin 1 -> VOUT0
pin 2 -> TACHO dla VOUT0
pin 3 -> GND
pin 4 -> TACHO dla VOUT1
pin 5 -> VOUT1
```

## Tor wejściowy

Dla obu kanałów obowiązuje ten sam zwalidowany tor wejściowy:

```text
                      +3.3 V
                         |
                       10 kΩ
                         |
TACHO FAN --------------+
                         |
                        1 kΩ
                         |
                         +---------- GPIO CM5
                         |
                        1 nF
                         |
                        GND
```

Założenia pomiaru:

- wyjście TACHO open-collector,
- pull-up 10 kΩ do 3,3 V,
- rezystor szeregowy 1 kΩ,
- kondensator 1 nF do GND,
- zbocze narastające,
- 3 impulsy/obrót,
- `RPM = frequency_hz * 20`.

## Implementacja

Dotychczasowy jednokanałowy `ExtractTachoMonitor` został rozszerzony do monitora dwóch niezależnych kanałów GPIO.

Każdy kanał ma osobny worker libgpiod:

```text
SUPPLY  -> consumer ventilation-core-supply-tacho  -> GPIO17
EXTRACT -> consumer ventilation-core-extract-tacho -> GPIO27
```

Dzięki temu oba wejścia są obsługiwane niezależnie na poziomie zbierania impulsów.

Nowe argumenty runtime:

```text
--enable-supply-tacho
--supply-tacho-line GPIO17
```

Zachowane argumenty EXTRACT:

```text
--enable-extract-tacho
--extract-tacho-line GPIO27
```

Produkcyjny plik `deploy/systemd/ventilation-core.service` w tej gałęzi włącza oba kanały.

## Kontrakt CoreState

Nie zmienia się struktura API. Istniejące pole:

```text
state.tacho.supply
```

przestaje być `null` po włączeniu SUPPLY i publikuje:

```text
line_name
line_offset
frequency_hz
rpm
sample_count
age_seconds
valid
```

`state.tacho.extract` pozostaje bez zmian.

Web GUI z PR #20 już obsługuje oba pola i nie wymaga dodatkowego endpointu ani obliczania RPM po stronie przeglądarki.

## Bezpieczeństwo

TACHO pozostaje wyłącznie read-only.

Brak sygnału lub awaria monitora TACHO:

- nie zmienia nastawy DAC,
- nie zatrzymuje wentylatora,
- nie ustawia trybu FAULT,
- nie tworzy alarmu DAC,
- nie jest interpretowana jako potwierdzone `0 RPM`.

`valid=false` oznacza wyłącznie brak aktualnego, poprawnego feedbacku TACHO.

## Walidacja programowa

Na docelowym CM5, z osobnego worktree `workshop-ventilation-tacho-supply-stage2`, wykonano pełny lokalny zestaw testów:

```text
Ran 162 tests in 0.119s
OK
```

`compileall` również zakończył się PASS. Produkcyjny `ventilation-core.service` pozostał aktywny podczas testów.

GitHub Actions run #862 nie uruchomił testów z powodu blokady billing/spending limit konta GitHub; czerwony status nie wynikał z błędu testów ani implementacji.

## Walidacja sprzętowa SUPPLY / GPIO17 — PASS

Data: 2026-08-13

Zweryfikowano fizyczny drugi wentylator nawiewny na docelowym torze:

```text
SUPPLY control -> DAC CH0 / VOUT0
SUPPLY TACHO   -> GPIO17 / physical pin 11
```

Przed testem:

```text
GPIO17: input, bez właściciela
ventilation-core.service: active
```

### STOP / baseline

Przy:

```text
mode=STOP
supply_voltage=0.0
extract_voltage=0.0
hardware_ready=True
active_alarms=[]
```

przez 5 s nie zarejestrowano żadnych fałszywych impulsów:

```text
SUPPLY   NO VALID TACHO
```

### SUPPLY = 5.0 V

Po ustawieniu:

```text
mode=MANUAL
supply_voltage=5.0
extract_voltage=0.0
hardware_ready=True
active_alarms=[]
```

GPIO17 rozpoczął stabilny odczyt TACHO. Początkowy rozbieg wentylatora:

```text
58.296 Hz -> 1165.9 RPM
67.063 Hz -> 1341.3 RPM
68.467 Hz -> 1369.3 RPM
```

Stan ustalony był około:

```text
69.0 Hz -> około 1380 RPM
```

Końcowa próbka:

```text
69.423 Hz -> 1388.5 RPM
samples=6
age=0.006 s
```

Wynik jest spójny z kontraktem 3 impulsy/obrót i `RPM = Hz * 20`.

### Końcowy STOP

Po teście potwierdzono:

```text
mode=STOP
supply_voltage=0.0
extract_voltage=0.0
hardware_ready=True
active_alarms=[]
```

## Dwukanałowy runtime SUPPLY + EXTRACT — PASS

Na osobnym testowym socketcie uruchomiono core z gałęzi Stage 2 z oboma wejściami TACHO aktywnymi jednocześnie:

```text
SUPPLY  -> GPIO17
EXTRACT -> GPIO27
```

Produkcjny `ventilation-core.service` został wcześniej bezpiecznie zatrzymany po wymuszeniu STOP. Początkowy stan testowego core:

```text
mode=STOP
hardware_ready=True
active_alarms=[]
SUPPLY valid=False / 0 RPM
EXTRACT valid=False / 0 RPM
SENSOR BUS: slave 1 i 2 online/usable
```

Po ustawieniu:

```text
supply=5.0 V
extract=5.0 V
```

uzyskano pięć kolejnych próbek z jednoczesnym poprawnym feedbackiem obu kanałów:

```text
SUPPLY  69.996 Hz / 1399.9 RPM | EXTRACT 70.138 Hz / 1402.8 RPM
SUPPLY  71.087 Hz / 1421.7 RPM | EXTRACT 72.368 Hz / 1447.4 RPM
SUPPLY  70.590 Hz / 1411.8 RPM | EXTRACT 72.742 Hz / 1454.8 RPM
SUPPLY  70.373 Hz / 1407.5 RPM | EXTRACT 72.948 Hz / 1459.0 RPM
SUPPLY  71.282 Hz / 1425.6 RPM | EXTRACT 72.908 Hz / 1458.2 RPM
```

Dla wszystkich próbek:

```text
mode=MANUAL
SUPPLY valid=True
EXTRACT valid=True
active_alarms=[]
```

SENSOR BUS pozostał zdrowy podczas pracy obu wentylatorów:

```text
slave 1: online=True, usable=True, consecutive_failures=0
slave 2: online=True, usable=True, consecutive_failures=0
```

Po poleceniu STOP testowy core wrócił do:

```text
mode=STOP
supply=0.0 V
extract=0.0 V
hardware_ready=True
active_alarms=[]
```

Następnie testowy proces został zamknięty, produkcyjny `ventilation-core.service` uruchomiony ponownie i ponownie potwierdzono STOP / 0.0 V / 0.0 V.

### AERO BUS podczas testu

Podczas tego konkretnego uruchomienia testowego core AERO BUS zgłaszał:

```text
online=False
usable=False
last_error=No response or incomplete Modbus header
consecutive_failures=7
```

Jednocześnie TACHO, DAC i SENSOR BUS działały poprawnie. Potwierdza to izolację AERO BUS od pozostałych torów, ale ponieważ AERO było wcześniej fizycznie naprawione i zwalidowane jako online/usable, należy osobno potwierdzić stan AERO po powrocie produkcyjnego core. Tego wyniku nie klasyfikujemy jako błąd TACHO Stage 2.

## Pozostała walidacja sprzętowa

Przed merge nadal wymagane jest potwierdzenie:

1. fizyczne odłączenie wyłącznie SUPPLY TACHO nie zmienia setpointu SUPPLY ani trybu core,
2. ponowne podłączenie SUPPLY TACHO odzyskuje `valid=true` bez restartu core,
3. stan AERO BUS po powrocie produkcyjnego core,
4. integracja odczytu `state.tacho.supply` w Web GUI,
5. końcowy stan DAC po pełnej walidacji: STOP / 0.0 V / 0.0 V.

PR pozostaje Draft do zakończenia walidacji sprzętowej i jawnej decyzji użytkownika o Ready/Merge.
