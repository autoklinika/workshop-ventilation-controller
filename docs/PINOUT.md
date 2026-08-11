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

Po sprawdzeniu aktualnego przydziału GPIO w repozytorium zarezerwowano dwa wolne wejścia z 40-pinowego złącza CM5 IO Board. Do czasu zakończenia fizycznej identyfikacji obu wentylatorów używamy neutralnych nazw wejść:

| Funkcja robocza | GPIO | Pin fizyczny CM5 | Kierunek |
|---|---:|---:|---|
| `TACHO_INPUT_1` | GPIO17 | 11 | wejście |
| `TACHO_INPUT_2` | GPIO27 | 13 | wejście |

Przydział nie koliduje z aktualnie używanymi liniami I²C1 (GPIO2/3), SENSOR BUS UART0 (GPIO14/15) ani AERO BUS UART4 (GPIO12/13).

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

Walidacja na docelowym CM5 potwierdziła obie linie jako wejścia `gpiochip0` oraz poprawny dynamiczny pomiar na GPIO17. Jednocześnie pierwszy test fizyczny wykazał, że wentylator sterowany aktualnie przez `EXTRACT / CH1 / VOUT1` publikuje TACHO na GPIO17. Dlatego przypisania funkcjonalne `SUPPLY`/`EXTRACT` do GPIO17/GPIO27 pozostają **nieustalone** do czasu identyfikacji obu fizycznych wentylatorów i przewodów. Nie należy traktować neutralnych nazw `TACHO_INPUT_1/2` jako finalnej semantyki instalacji.

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

## Złącze DB9 sterowania wentylatorami

| Pin DB9 | Funkcja |
|---:|---|
| 1 | Vout0 |
| 2 | wolny |
| 3 | GND |
| 4 | wolny |
| 5 | Vout1 |
| 6 | wolny |
| 7 | wolny |
| 8 | wolny |
| 9 | wolny |

### Podsumowanie DB9

```text
1          Vout0
2          wolny
3          GND
4          wolny
5          Vout1
6, 7, 8, 9 wolne
```
