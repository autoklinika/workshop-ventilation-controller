# CM5 TACHO Stage 1 — walidacja runtime CoreState

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Host:** `wentylacja` / Raspberry Pi Compute Module 5  
**Gałąź:** `agent/cm5-tacho-stage1`  
**Status:** runtime STOP, RUN, timeout i odłączenie TACHO — PASS; pozostaje test odzyskania sygnału po ponownym podłączeniu oraz trwałe włączenie monitora.

## 1. Konfiguracja stanowiska

```text
sterowanie: EXTRACT / DAC CH1 / VOUT1 / DB9 pin 5
TACHO:      GPIO27 / physical pin 13 / gpiochip0 offset 27
```

`ventilation-core` uruchomiono z tymczasowym drop-inem systemd w `/run/systemd/system/ventilation-core.service.d/90-tacho-validation.conf` i argumentem `--enable-extract-tacho`. Trwały plik jednostki w `/etc/systemd/system` nie został jeszcze zmieniony.

## 2. Runtime przy STOP — PASS

Po restarcie potwierdzono:

```text
mode=STOP
extract_voltage=0.0
hardware_ready=true
active_alarms=[]
tacho.ready=true
tacho.worker_alive=true
tacho.last_error=null
tacho.extract.valid=false
tacho.extract.frequency_hz=0.0
tacho.extract.rpm=0.0
```

`gpioinfo GPIO27`:

```text
input bias=disabled edges=rising consumer="ventilation-core-extract-tacho"
```

Stały runtime poprawnie przejął zwalidowane wejście GPIO27 i publikuje prawidłowy stan STOP bez wpływu na DAC ani alarmy.

## 3. Runtime przy 5 V — PASS end-to-end

Po normalnej komendzie przez `ventilation_core.ctl`:

```text
supply=0.0 V
extract=5.0 V
```

potwierdzono pełną ścieżkę:

```text
ctl set -> DAC CH1/VOUT1 -> fizyczny wentylator -> TACHO -> GPIO27 -> libgpiod -> estimator -> CoreState.tacho.extract
```

Pierwszy przebieg po nominalnych 5 s stabilizacji pokazał poprawne `valid=true`, lecz wentylator nadal dochodził do prędkości ustalonej. Tuż po późniejszym STOP estimator zarejestrował `71.716 Hz / 1434.3 RPM`, bardzo blisko wcześniejszej referencji oscyloskopowej `71.937 Hz / 1438.7 RPM`.

## 4. Dłuższy przebieg 12 s

Po 12 s stabilizacji i kolejnych pięciu odczytach 1 s otrzymano:

```text
67.895 Hz -> 1357.9 RPM
67.617 Hz -> 1352.3 RPM
67.803 Hz -> 1356.1 RPM
67.979 Hz -> 1359.6 RPM
68.122 Hz -> 1362.4 RPM
```

Średnio około:

```text
67.883 Hz
1357.7 RPM
```

Wszystkie odczyty były `valid=true`, `sample_count=6` i miały małe `age_seconds`. Bieżący przebieg był wolniejszy od wcześniejszej referencji oscyloskopowej o około 5,6%, ale nie wskazuje to na błąd zliczania impulsów: częstotliwość była stabilna, przelicznik RPM pozostaje zgodny z 3 impulsami/obrót, a rzeczywista prędkość wentylatora może różnić się pomiędzy przebiegami. Kalibracja `command voltage -> expected RPM` nie jest częścią Stage 1 i wymaga osobnej charakterystyki produkcyjnej.

## 5. Runtime timeout po STOP — PASS

Po komendzie STOP odczyty były:

```text
mode=STOP cmd=0.0V valid=True  Hz=68.145 RPM=1362.9 age=0.006s
mode=STOP cmd=0.0V valid=True  Hz=69.395 RPM=1387.9 age=0.058s
mode=STOP cmd=0.0V valid=False Hz=0.000  RPM=0.0    age=0.314s
```

Następnie `valid=false`, `0 Hz / 0 RPM` utrzymywało się do końca obserwacji, a `age_seconds` wzrosło monotonicznie do około `5.966 s`.

To jednoznacznie potwierdza działanie timeoutu `0.25 s`:

- poniżej progu (`age=0.058 s`) odczyt pozostaje ważny,
- po przekroczeniu progu (`age=0.314 s`) odczyt staje się nieważny,
- brak fałszywego powrotu do `valid=true` po zaniku impulsów.

## 6. Odłączenie sygnału TACHO przy zachowaniu sterowania — PASS

W celu sprawdzenia separacji failure-domain odłączono fizycznie wyłącznie przewód sygnałowy TACHO. Zasilanie wentylatora, wspólna masa i sterowanie 0–10 V pozostały bez zmian.

Przed startem, przy odłączonym TACHO:

```text
mode=STOP
extract_voltage=0.0
tacho_valid=false
tacho_rpm=0.0
hardware_ready=true
active_alarms=[]
```

Następnie wydano:

```text
supply=0.0 V
extract=5.0 V
```

Użytkownik potwierdził fizycznie, że wentylator normalnie pracował.

Po około 8 s runtime raportował:

```text
mode=MANUAL
extract_voltage=5.0
hardware_ready=true
output_state_known=true
active_alarms=[]
sensor_bus_ready=true
tacho_ready=true
tacho_worker_alive=true
tacho_last_error=null
tacho_valid=false
tacho_hz=0.0
tacho_rpm=0.0
tacho_age=585.274 s
```

Długi `tacho_age` jest poprawny: pole oznacza wiek ostatniego rzeczywistego zbocza, a nie czas od momentu fizycznego odłączenia przewodu. Po odłączeniu monitor nie generuje sztucznych impulsów i pozostaje żywy.

### Wniosek

Utrata sygnału TACHO jest poprawnie odseparowana od sterowania:

- wentylator nadal pracuje na zadanym 5 V,
- DAC pozostaje gotowy,
- `output_state_known=true`,
- nie powstaje alarm,
- tryb pozostaje `MANUAL`,
- SENSOR BUS pozostaje gotowy,
- worker TACHO pozostaje `ready/worker_alive`,
- jedynym skutkiem jest brak ważnego feedbacku: `valid=false`, `0 Hz`, `0 RPM`.

To potwierdza wymaganą dla Stage 1 zasadę: TACHO jest read-only feedbackiem i jego brak nie może samodzielnie zatrzymywać wentylatora ani wymuszać `FAULT`.

## 7. Zbiorczy wynik Stage 1 dla kanału EXTRACT

Zwalidowano:

- sprzętowy tor wejściowy GPIO27,
- odbiór realnych zboczy TACHO,
- 3 impulsy/obrót i `RPM = Hz * 20`,
- brak fałszywych zboczy przy STOP,
- poprawny timeout `0.25 s`,
- poprawną publikację `CoreState.tacho.extract`,
- pełną ścieżkę end-to-end DAC -> wentylator -> TACHO -> CoreState,
- niezależność TACHO od DAC, SENSOR BUS i trybu sterowania,
- bezpieczne zachowanie po fizycznej utracie sygnału TACHO.

Kanał EXTRACT / GPIO27 spełnia wymagania Stage 1 dla read-only feedbacku.

## 8. Ostatni krok przed trwałym włączeniem

Przed zmianą trwałej jednostki systemd należy jeszcze wykonać krótki test odzyskania sygnału:

1. przy zatrzymanym wentylatorze ponownie podłączyć przewód TACHO do GPIO27,
2. uruchomić EXTRACT = 5 V,
3. potwierdzić, że ten sam istniejący worker bez restartu przechodzi z `valid=false` do `valid=true` i ponownie raportuje Hz/RPM,
4. wykonać STOP,
5. po PASS włączyć `--enable-extract-tacho` w trwałej jednostce systemd i usunąć tymczasowy drop-in z `/run`.

Drugi kanał TACHO pozostaje poza bieżącą walidacją do czasu dostępności drugiego fizycznego wentylatora.
