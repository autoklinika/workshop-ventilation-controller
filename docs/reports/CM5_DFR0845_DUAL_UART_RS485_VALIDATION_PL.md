# Walidacja CM5 + 2× DFR0845 — UART i RS-485

Data walidacji: 2026-08-04

Repozytorium:

```text
autoklinika/workshop-ventilation-controller
```

Pierwotna gałąź robocza:

```text
agent/cm5-sensor-bus-worker-stage1
```

Raport zachowany również na aktualnej gałęzi implementacyjnej:

```text
agent/cm5-sensor-bus-worker-stage1-refresh
```

## Cel

Zweryfikowanie dwóch niezależnych interfejsów UART Raspberry Pi CM5 oraz dwóch modułów:

```text
DFRobot DFR0845
Gravity: Active Isolated RS485 to UART Module
```

Docelowy podział:

```text
DFR0845 #1 -> SENSOR BUS
DFR0845 #2 -> AERO BUS
```

## Najważniejsza korekta pinoutu DFR0845

Oznaczenia `T` i `R` na stronie UART DFR0845 należy interpretować względem kontrolera:

```text
CM5 TX -> T DFR0845
CM5 RX <- R DFR0845
```

Połączeń `T/R` nie należy krzyżować.

Wcześniejsze połączenie:

```text
CM5 TX -> R
CM5 RX <- T
```

było nieprawidłowe i powodowało brak transmisji przez RS-485.

## Zasilanie użyte podczas walidacji

Oba DFR0845 były tymczasowo zasilane z dostępnego źródła 3,3 V pochodzącego z KAmod ESP32 POW RS485.

Zmierzona wartość na wejściu zasilania strony UART:

```text
3,28 V
```

Podczas testu nie zaobserwowano spadku napięcia po podłączeniu obu modułów.

Docelowo oba DFR0845 mają być zasilane z osobnego gotowego konwertera:

```text
DFRobot DFR0570
12 V -> 3,3 V
```

Nie wolno łączyć wyjścia zewnętrznego konwertera 3,3 V z szyną 3,3 V CM5. Wspólna pozostaje wyłącznie masa logiczna wymagana przez UART:

```text
CM5 GND
DFR0570 GND
DFR0845 #1 -
DFR0845 #2 -
```

Pomocnicze wyjście 12 V DFR0845 nie jest używane w projekcie.

## Konfiguracja UART CM5

Aktywne porty:

```text
/dev/ttyAMA0
/dev/ttyAMA4
```

Potwierdzony pinmux:

```text
GPIO14 = TXD0
GPIO15 = RXD0
GPIO12 = TXD4
GPIO13 = RXD4
```

## Docelowy pinout SENSOR BUS

Port systemowy i parametry:

```text
/dev/ttyAMA0
19200 bit/s
8N1
```

Połączenie strony UART:

| CM5 IO Board | GPIO | Funkcja | DFR0845 #1 |
|---|---:|---|---|
| pin 8 | GPIO14 | TXD0 | `T` |
| pin 10 | GPIO15 | RXD0 | `R` |
| GND | — | masa logiczna | `-` |
| zewnętrzne 3,3 V | — | zasilanie | `+` |

Połączenie strony RS-485:

```text
A   -> SENSOR BUS A
B   -> SENSOR BUS B
GND -> SENSOR BUS GND
12V -> niepodłączone
```

Urządzenia docelowe:

```text
KAmod + SEN55, slave 1
KAmod + SEN55, slave 2
```

Parametry Modbus RTU:

```text
19200 bit/s
8N1
FC04
mapa v1
19 Input Registers
```

## Docelowy pinout AERO BUS

Port systemowy i parametry:

```text
/dev/ttyAMA4
9600 bit/s
8N1
```

Połączenie strony UART:

| CM5 IO Board | GPIO | Funkcja | DFR0845 #2 |
|---|---:|---|---|
| pin 32 | GPIO12 | TXD4 | `T` |
| pin 33 | GPIO13 | RXD4 | `R` |
| GND | — | masa logiczna | `-` |
| zewnętrzne 3,3 V | — | zasilanie | `+` |

Połączenie strony RS-485:

```text
A   -> AERO BUS A
B   -> AERO BUS B
GND -> AERO BUS GND
12V -> niepodłączone
```

Urządzenie docelowe:

```text
NANO COLOR 2 / AERO 4A2
slave 44
FC03/FC06
```

## Walidacja bezpośrednia UART0 <-> UART4

DFR0845 zostały odłączone. UART-y CM5 połączono bezpośrednio:

```text
pin 8  / GPIO14 / TXD0 -> pin 33 / GPIO13 / RXD4
pin 32 / GPIO12 / TXD4 -> pin 10 / GPIO15 / RXD0
```

Polecenie:

```bash
python3 tools/cm5_dfr0845_dual_uart_loopback.py \
  --port-a /dev/ttyAMA0 \
  --port-b /dev/ttyAMA4 \
  --baud 19200 \
  --iterations 20 \
  --timeout 1
```

Wynik:

```text
A->B attempts=20 successes=20 failures=0
B->A attempts=20 successes=20 failures=0
```

Wniosek:

- UART0 działa poprawnie,
- UART4 działa poprawnie,
- GPIO12, GPIO13, GPIO14 i GPIO15 działają poprawnie,
- konfiguracja overlay i urządzeń `/dev/ttyAMA0`, `/dev/ttyAMA4` jest poprawna.

## Walidacja przez dwa DFR0845

Po poprawieniu pinoutu UART połączono oba moduły stroną RS-485:

```text
DFR0845 #1 A   <-> DFR0845 #2 A
DFR0845 #1 B   <-> DFR0845 #2 B
DFR0845 #1 GND <-> DFR0845 #2 GND
```

### Test 19200 bit/s

Polecenie:

```bash
python3 tools/cm5_dfr0845_dual_uart_loopback.py \
  --port-a /dev/ttyAMA0 \
  --port-b /dev/ttyAMA4 \
  --baud 19200 \
  --iterations 100 \
  --timeout 1
```

Wynik:

```text
A->B attempts=100 successes=100 failures=0
B->A attempts=100 successes=100 failures=0
```

### Test 9600 bit/s

Polecenie:

```bash
python3 tools/cm5_dfr0845_dual_uart_loopback.py \
  --port-a /dev/ttyAMA0 \
  --port-b /dev/ttyAMA4 \
  --baud 9600 \
  --iterations 100 \
  --timeout 1
```

Wynik:

```text
A->B attempts=100 successes=100 failures=0
B->A attempts=100 successes=100 failures=0
```

## Wynik końcowy

Walidacja sprzętowa została zaliczona.

Potwierdzono:

- oba kontrolery UART CM5,
- cztery używane linie GPIO,
- oba moduły DFR0845,
- automatyczne sterowanie kierunkiem transmisji DFR0845,
- dwukierunkową transmisję RS-485,
- stabilną pracę przy 19200 bit/s,
- stabilną pracę przy 9600 bit/s.

Autorytatywne przypisanie magistral:

```text
/dev/ttyAMA0 = SENSOR BUS = 19200 bit/s, 8N1
/dev/ttyAMA4 = AERO BUS   = 9600 bit/s, 8N1
```

Autorytatywne mapowanie strony UART DFR0845:

```text
TX kontrolera -> T DFR0845
RX kontrolera <- R DFR0845
```

## Następny krok po tej walidacji

Testowy mostek pomiędzy DFR0845 został zastąpiony docelowym połączeniem `/dev/ttyAMA0` z magistralą dwóch węzłów KAmod + SEN55. Następnym etapem jest walidacja produkcyjnego `sensor_bus_worker` na rzeczywistym CM5, w tym kontrolowane odłączanie i ponowne podłączanie każdego slave.
