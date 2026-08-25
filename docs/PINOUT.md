# Pinout

## Podłączenie DAC DFR0971 do CM5

Moduł:

```text
DFRobot DFR0971
GP8403, 2 kanały 0–10 V
I²C1, adres 0x58
```

| DFR0971 | CM5 IO Board | GPIO / funkcja | Pin fizyczny CM5 |
|---|---|---|---:|
| `VCC` | 3,3 V | zasilanie logiki DAC | 1 |
| `GND` | GND | masa logiczna | 6 |
| `SDA` | GPIO2 | SDA1 | 3 |
| `SCL` | GPIO3 | SCL1 | 5 |

Przełączniki adresowe DFR0971:

```text
A0 = 0
A1 = 0
A2 = 0
adres I²C = 0x58
port systemowy = /dev/i2c-1
```

Wyjścia analogowe DAC:

```text
VOUT0 -> DB9 pin 1
VOUT1 -> DB9 pin 5
GND   -> DB9 pin 3
```

> DFR0971 jest zasilany z szyny 3,3 V CM5. Poziomy I²C muszą pozostać zgodne z logiką 3,3 V CM5.

## DFR0473 — odcinanie domeny 12 V

Moduł:

```text
DFRobot DFR0473
Gravity: Digital 10A Relay Module
```

Podłączenie strony sterującej, fizycznie zwalidowane 2026-08-25:

| DFR0473 | CM5 IO Board | GPIO / funkcja | Pin fizyczny CM5 |
|---|---|---|---:|
| `+` / VCC | 3,3 V | zasilanie modułu przekaźnika | 1 |
| `-` / GND | GND | wspólna masa logiczna | 9 lub inny GND |
| `D` | GPIO22 | `POWER_DOMAIN_12V_ENABLE` | 15 |

Sterowanie:

```text
GPIO22 LOW / Hi-Z -> DFR0473 OFF -> COM-NO rozwarte -> 12 V OFF
GPIO22 HIGH 3,3 V -> DFR0473 ON  -> COM-NO zwarte  -> 12 V ON
```

Strona mocy:

```text
+12 V z zasilacza -> COM
NO                -> +12 V SWITCHED do domeny peryferiów
NC                -> niepodłączone
GND 12 V          -> nieprzełączane, bezpośrednio do odbiorników
```

Fizyczny test `LOW -> HIGH -> LOW` na GPIO22 zakończony PASS.

> DFR0473 odcina domenę +12 V. Nie odcina zasilania DFR0971, ponieważ DAC jest zasilany z 3,3 V CM5. `DFR0473 OFF` nie jest potwierdzeniem 0 V na VOUT0/VOUT1 DAC.

## Podłączenie modułów DFR0845 RS-485 do CM5

Moduły:

```text
DFRobot DFR0845
Gravity: Active Isolated RS485 to UART Module
```

Najważniejsze mapowanie strony UART:

```text
CM5 TX -> T DFR0845
CM5 RX <- R DFR0845
```

Oznaczeń `T` i `R` nie należy krzyżować.

### DFR0845 #1 — SENSOR BUS

```text
port systemowy: /dev/ttyAMA0
parametry:       19200 bit/s, 8N1
```

| DFR0845 #1 | CM5 IO Board | GPIO / funkcja | Pin fizyczny CM5 |
|---|---|---|---:|
| `T` | GPIO14 | TXD0 | 8 |
| `R` | GPIO15 | RXD0 | 10 |
| `-` | wspólna masa logiczna | GND CM5 / DFR0570 | dowolny pin GND CM5 |
| `+` | zewnętrzne 3,3 V | wyjście DFR0570 | nie łączyć z 3,3 V CM5 |

Strona izolowana RS-485:

```text
A   -> SENSOR BUS A -> RJ45 pin 1
B   -> SENSOR BUS B -> RJ45 pin 2
GND -> SENSOR BUS GND / GND 12 V -> RJ45 piny 7 i 8
12V OUT -> niepodłączone
```

Urządzenia docelowe:

```text
KAmod + SEN55, slave 1
KAmod + SEN55, slave 2
```

### DFR0845 #2 — AERO BUS

```text
port systemowy: /dev/ttyAMA4
parametry:       9600 bit/s, 8N1
```

| DFR0845 #2 | CM5 IO Board | GPIO / funkcja | Pin fizyczny CM5 |
|---|---|---|---:|
| `T` | GPIO12 | TXD4 | 32 |
| `R` | GPIO13 | RXD4 | 33 |
| `-` | wspólna masa logiczna | GND CM5 / DFR0570 | dowolny pin GND CM5 |
| `+` | zewnętrzne 3,3 V | wyjście DFR0570 | nie łączyć z 3,3 V CM5 |

Strona izolowana RS-485:

```text
A   -> AERO BUS A -> RJ45 pin 1
B   -> AERO BUS B -> RJ45 pin 2
GND -> AERO BUS GND / GND 12 V -> RJ45 piny 7 i 8
12V OUT -> niepodłączone
```

Urządzenie docelowe:

```text
NANO COLOR 2 / AERO 4A2
slave 44
```

### Zasilanie i masy DFR0845

Docelowo oba DFR0845 są zasilane ze wspólnego, zewnętrznego konwertera:

```text
DFRobot DFR0570
12 V -> 3,3 V
```

Po stronie logicznej wspólne są:

```text
CM5 GND
DFR0570 GND
DFR0845 #1 -
DFR0845 #2 -
```

Nie wolno łączyć wyjścia 3,3 V DFR0570 z pinami 3,3 V CM5.

> `-` po stronie UART DFR0845 jest masą logiczną. `GND` przy zaciskach `A/B` znajduje się po izolowanej stronie RS-485. Nie należy zwierać tych dwóch mas lokalnie przy module DFR0845.

## Wejścia TACHO wentylatorów EC

Dwa wolne wejścia z 40-pinowego złącza CM5 IO Board pozostają zarezerwowane dla dwóch torów TACHO:

| Funkcja | GPIO | Pin fizyczny CM5 | Kierunek | Status |
|---|---:|---:|---|---|
| `TACHO_INPUT_1` | GPIO17 | 11 | wejście | wolny drugi kanał, niezwalidowany z osobnym wentylatorem |
| `FAN_EXTRACT_TACHO` | GPIO27 | 13 | wejście | dynamicznie zwalidowany z laboratoryjnym wentylatorem na CH1/VOUT1; test STOP na finalnym GPIO27 pozostaje do wykonania |

Przydział nie koliduje z aktualnie używanymi liniami I²C1 (GPIO2/3), SENSOR BUS UART0 (GPIO14/15), AERO BUS UART4 (GPIO12/13) ani POWER DOMAIN (GPIO22).

### Aktualne stanowisko jednego wentylatora

W laboratorium dostępny jest obecnie jeden fizyczny wentylator. Dla dalszej walidacji Stage 1 przyjmujemy jednoznacznie:

```text
sterowanie wentylatora: EXTRACT / DAC CH1 / VOUT1 / DB9 pin 5
pomiar TACHO:           GPIO27 / pin 13
```

Wcześniejszy test tego samego wentylatora na GPIO17 potwierdził sam mechanizm pomiaru TACHO, ale nie jest już traktowany jako docelowe przypisanie kanału. Po fizycznym przepięciu przewodu TACHO do GPIO27 dalsze testy należy wykonywać na parze `EXTRACT + GPIO27`.

Na GPIO27 przy `extract=5.0 V` uzyskano średnio około `70.575 Hz / 1411.5 RPM` z 14 stabilnych próbek, czyli około `-1.89%` względem wcześniejszego punktu oscyloskopowego `71.937 Hz / 1438.7 RPM`.

GPIO17 pozostaje zarezerwowany dla drugiego wentylatora, którego nie ma obecnie na stanowisku. Jego ostateczne przypisanie `SUPPLY` zostanie potwierdzone dopiero po walidacji z drugim fizycznym wentylatorem.

Tor wejściowy każdego TACHO:

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

Założenia potwierdzone pomiarami z 2026-08-11:

- wyjście TACHO typu open-collector,
- pull-up 10 kΩ do 3,3 V,
- 1 kΩ szeregowo przed GPIO,
- 1 nF ceramiczny do GND,
- 3 impulsy na obrót,
- `RPM = TACHO_HZ * 20`.

Do testu jednego wentylatora po przepięciu TACHO na GPIO27 używać:

```bash
PYTHONPATH=src python3 tools/hardware/tacho_cli.py \
  --chip /dev/gpiochip0 \
  --only extract
```

## Złącza RJ45 dla magistral

Złącza RJ45 w projekcie wykorzystują przewód i mechanikę RJ45, ale **nie są interfejsami Ethernet/LAN**.

> **Uwaga:** na pinach 4 i 5 występuje napięcie +12 V. Nie wolno podłączać tych przewodów do routera, switcha, komputera ani żadnego urządzenia Ethernet.

## Złącze RJ45 dla SEN55

| Pin RJ45 | Funkcja |
|---:|---|
| 1 | RS-485 A |
| 2 | RS-485 B |
| 3 | wolny |
| 4 | +12 V |
| 5 | +12 V |
| 6 | wolny |
| 7 | GND zasilania 12 V |
| 8 | GND zasilania 12 V |

### Podsumowanie SEN55

```text
1      RS-485 A
2      RS-485 B
3      wolny
4, 5   +12 V
6      wolny
7, 8   GND dla 12 V
```

## Złącze RJ45 dla AERO

Pinout złącza AERO jest identyczny jak dla SEN55.

| Pin RJ45 | Funkcja |
|---:|---|
| 1 | RS-485 A |
| 2 | RS-485 B |
| 3 | wolny |
| 4 | +12 V |
| 5 | +12 V |
| 6 | wolny |
| 7 | GND zasilania 12 V |
| 8 | GND zasilania 12 V |

### Podsumowanie AERO

```text
1      RS-485 A
2      RS-485 B
3      wolny
4, 5   +12 V
6      wolny
7, 8   GND dla 12 V
```

## Wspólne zasady prowadzenia zasilania RJ45

Piny 4 i 5 są przeznaczone do równoległego prowadzenia zasilania +12 V. Piny 7 i 8 są przeznaczone do równoległego prowadzenia masy zasilania 12 V.

## Złącze DB9 przewodu połączeniowego CM5 ↔ BOX wykonawczy

To złącze jest pinoutem przewodu sygnałowego łączącego CM5 z BOX-em wykonawczym. Nie należy go mylić z osobnym złączem DB9 BOX-u służącym do sterowania wentylatorami.

| Pin DB9 | Pin fizyczny CM5 | GPIO / funkcja CM5 | Sygnał w przewodzie |
|---:|---:|---|---|
| 1 | 32 | GPIO12 / TXD4 | `T` UART dla RS-485 rekuperatora / AERO BUS |
| 2 | 33 | GPIO13 / RXD4 | `R` UART dla RS-485 rekuperatora / AERO BUS |
| 3 | 8 | GPIO14 / TXD0 | `T` UART dla RS-485 SENSOR BUS / SEN55 |
| 4 | 10 | GPIO15 / RXD0 | `R` UART dla RS-485 SENSOR BUS / SEN55 |
| 5 | 6 | GND | wspólna masa logiczna |
| 6 | 3 | GPIO2 / SDA1 | SDA / dane DAC DFR0971 |
| 7 | 5 | GPIO3 / SCL1 | SCL / zegar DAC DFR0971 |
| 8 | 11 | GPIO17 | TACHO dla Vout0 |
| 9 | 13 | GPIO27 | TACHO dla Vout1 |

### Podsumowanie przewodu CM5 ↔ BOX wykonawczy

```text
DB9 1 -> CM5 pin 32 -> GPIO12 / TXD4 -> T UART RS-485 rekuperator / AERO BUS
DB9 2 -> CM5 pin 33 -> GPIO13 / RXD4 -> R UART RS-485 rekuperator / AERO BUS
DB9 3 -> CM5 pin 8  -> GPIO14 / TXD0 -> T UART RS-485 SENSOR BUS / SEN55
DB9 4 -> CM5 pin 10 -> GPIO15 / RXD0 -> R UART RS-485 SENSOR BUS / SEN55
DB9 5 -> CM5 pin 6  -> GND            -> wspólna masa logiczna
DB9 6 -> CM5 pin 3  -> GPIO2 / SDA1   -> DAC SDA
DB9 7 -> CM5 pin 5  -> GPIO3 / SCL1   -> DAC SCL
DB9 8 -> CM5 pin 11 -> GPIO17         -> TACHO dla Vout0
DB9 9 -> CM5 pin 13 -> GPIO27         -> TACHO dla Vout1
```

> Linie `T`/`R` w tym przewodzie są liniami UART po stronie logicznej modułów DFR0845. Nie są to linie `A`/`B` magistrali RS-485.

## Złącze DB9 sterowania wentylatorami

| Pin DB9 | Funkcja |
|---:|---|
| 1 | Vout0 |
| 2 | Tacho dla Vout0 |
| 3 | GND |
| 4 | Tacho dla Vout1 |
| 5 | Vout1 |
| 6 | wolny |
| 7 | wolny |
| 8 | wolny |
| 9 | wolny |

### Podsumowanie DB9

```text
1          Vout0
2          Tacho dla Vout0
3          GND
4          Tacho dla Vout1
5          Vout1
6, 7, 8, 9 wolne
```
