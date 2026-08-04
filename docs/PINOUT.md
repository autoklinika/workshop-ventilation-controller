# Pinout

## Złącze RJ45 dla SEN55

Złącze wykorzystuje przewód i mechanikę RJ45, ale **nie jest interfejsem Ethernet/LAN**.

> **Uwaga:** na pinach 4 i 5 występuje napięcie +12 V. Nie wolno podłączać tego przewodu do routera, switcha, komputera ani żadnego urządzenia Ethernet.

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

### Podsumowanie

```text
1      RS-485 A
2      RS-485 B
3      wolny
4, 5   +12 V
6      wolny
7, 8   GND dla 12 V
```

Piny 4 i 5 są przeznaczone do równoległego prowadzenia zasilania +12 V. Piny 7 i 8 są przeznaczone do równoległego prowadzenia masy zasilania 12 V.
