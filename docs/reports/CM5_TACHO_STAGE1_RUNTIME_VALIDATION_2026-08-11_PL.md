# CM5 TACHO Stage 1 — walidacja runtime CoreState

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Host:** `wentylacja` / Raspberry Pi Compute Module 5  
**Gałąź:** `agent/cm5-tacho-stage1`  
**Status:** runtime STOP i RUN — PASS; końcowy timeout runtime i test odłączenia przewodu pozostają do wykonania.

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

`gpioinfo GPIO27` wskazało:

```text
input bias=disabled edges=rising consumer="ventilation-core-extract-tacho"
```

Wniosek: stały runtime poprawnie przejął zwalidowane wejście GPIO27 i publikuje prawidłowy stan STOP bez wpływu na DAC ani alarmy.

## 3. Runtime przy 5 V — PASS end-to-end

Po normalnej komendzie przez `ventilation_core.ctl`:

```text
supply=0.0 V
extract=5.0 V
```

oraz nominalnych 5 s stabilizacji `CoreState.tacho.extract` raportował kolejno:

```text
56.244 Hz -> 1124.9 RPM
65.423 Hz -> 1308.5 RPM
67.149 Hz -> 1343.0 RPM
67.721 Hz -> 1354.4 RPM
67.640 Hz -> 1352.8 RPM
```

W każdej próbce:

```text
mode=MANUAL
cmd=5.0 V
tacho.ready=true
tacho.extract.valid=true
sample_count=6
```

Potwierdzono pełną ścieżkę:

```text
ctl set -> DAC CH1/VOUT1 -> fizyczny wentylator -> TACHO -> GPIO27 -> libgpiod -> estimator -> CoreState.tacho.extract
```

## 4. Zachowanie bezpośrednio po STOP

Po wydaniu STOP i około 0,4 s od komendy stan był:

```text
mode=STOP
cmd=0.0 V
71.716 Hz
1434.3 RPM
age=0.2025 s
valid=true
```

To zachowanie jest prawidłowe. Estimator ma timeout `0.25 s`, a `age=0.2025 s` nadal znajduje się poniżej tego progu. Pomiar powinien pozostać ważny do czasu, aż od ostatniego rzeczywistego zbocza upłynie więcej niż 0,25 s.

Nie należy więc oceniać timeoutu na podstawie stałego czasu od wysłania komendy STOP. Trzeba obserwować `age_seconds` i rzeczywiste przejście `valid=true -> false`.

## 5. Czas stabilizacji wentylatora

Wartość tuż po STOP:

```text
71.716 Hz / 1434.3 RPM
```

jest bardzo bliska wcześniejszej referencji oscyloskopowej przy 5 V:

```text
71.937 Hz / 1438.7 RPM
```

Jednocześnie wcześniejsze próbki po nominalnych 5 s były jeszcze niższe. Oznacza to, że na tym stanowisku 5 s nie jest gwarantowanym czasem osiągnięcia prędkości ustalonej.

Dla przyszłej diagnostyki `command vs actual` trzeba przewidzieć osobny czas rozruchu/stabilizacji. Alarm under-speed nie powinien być oceniany natychmiast po zmianie setpointu.

## 6. Stan pozostałych podsystemów

Podczas runtime testu:

```text
hardware_ready=true
output_state_known=true
active_alarms=[]
sensor_bus_ready=true
tacho_ready=true
tacho_worker_alive=true
tacho_last_error=null
```

Nie zaobserwowano wpływu TACHO na ścieżkę sterowania DAC ani SENSOR BUS.

## 7. Pozostałe checkpointy Stage 1

Przed trwałym włączeniem TACHO w jednostce systemd pozostaje:

1. uruchomić EXTRACT = 5 V i zastosować dłuższą stabilizację około 12 s,
2. po STOP obserwować `age_seconds` aż do faktycznego przejścia `valid=true -> false`,
3. fizycznie odłączyć przewód TACHO przy pracującym wentylatorze,
4. potwierdzić, że brak impulsów zmienia tylko stan TACHO, a wentylator nadal pracuje na zadanym napięciu i nie powstaje alarm DAC,
5. dopiero po PASS włączyć `--enable-extract-tacho` w trwałej jednostce systemd.

Drugi kanał TACHO pozostaje poza bieżącą walidacją do czasu dostępności drugiego fizycznego wentylatora.
