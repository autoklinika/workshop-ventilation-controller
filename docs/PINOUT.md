# Pinout

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

## Wspólne zasady prowadzenia zasilania

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
