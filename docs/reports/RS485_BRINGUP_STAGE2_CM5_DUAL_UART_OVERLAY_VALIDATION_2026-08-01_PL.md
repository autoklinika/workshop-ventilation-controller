# Stage 2 — walidacja aktywacji dwóch UART-ów CM5

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Zakres

Walidacja konfiguracji dwóch sprzętowych UART-ów CM5 przeznaczonych dla dwóch izolowanych konwerterów DFRobot DFR0845.

W `/boot/firmware/config.txt` aktywowano:

```ini
enable_uart=1
dtoverlay=uart0-pi5
dtoverlay=uart2-pi5
```

## Wynik urządzeń Linux

Po restarcie system udostępnił:

```text
/dev/serial0 -> ttyAMA0
/dev/ttyAMA0
/dev/ttyAMA2
/dev/ttyAMA10
```

Interpretacja:

- `/dev/serial0` wskazuje na `/dev/ttyAMA0` i odpowiada UART0 na GPIO14/15,
- `/dev/ttyAMA2` odpowiada UART2 na GPIO4/5,
- `/dev/ttyAMA10` pozostaje UART-em diagnostycznym Raspberry Pi 5 i nie jest używany przez RS-485.

## Walidacja funkcji pinów

```text
GPIO14 = TXD0
GPIO15 = RXD0
GPIO4  = TXD2
GPIO5  = RXD2
```

Potwierdza to poprawne przypisanie pinów:

- RS485_BUS_1: GPIO14/15,
- RS485_BUS_2: GPIO4/5.

## Wynik `rs485ctl ports`

Narzędzie zwróciło:

```json
{
  "ok": true,
  "ports": [
    {
      "path": "/dev/serial0",
      "resolved_path": "/dev/ttyAMA0",
      "stable_path": false,
      "interface_type": "onboard-uart",
      "usable_for_rs485": true
    },
    {
      "path": "/dev/ttyAMA10",
      "resolved_path": "/dev/ttyAMA10",
      "stable_path": false,
      "interface_type": "debug-uart",
      "usable_for_rs485": false
    },
    {
      "path": "/dev/ttyAMA2",
      "resolved_path": "/dev/ttyAMA2",
      "stable_path": false,
      "interface_type": "onboard-uart",
      "usable_for_rs485": true
    }
  ],
  "count": 3
}
```

## Wniosek

Aktywacja dwóch UART-ów zakończyła się wynikiem **PASS**.

Do dalszej walidacji używamy:

- `/dev/serial0` dla pierwszego DFR0845,
- `/dev/ttyAMA2` dla drugiego DFR0845.

`/dev/ttyAMA10` nie może być używany do komunikacji RS-485.

Następny krok: otwarcie pierwszego UART-u w osobnym `rs485-worker` bez transmisji danych, a następnie analogiczna walidacja drugiego portu.