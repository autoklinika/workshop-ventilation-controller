# Stage 2 — równoczesne otwarcie dwóch UART-ów na CM5

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Warunki

- aktywne overlaye `uart0-pi5` i `uart2-pi5`,
- `RS485_BUS_1`: `/dev/serial0` → `/dev/ttyAMA0`, GPIO14/15,
- `RS485_BUS_2`: `/dev/ttyAMA2`, GPIO4/5,
- zaciski RS-485 `A/B` obu DFR0845 pozostawały odłączone,
- test nie wykonywał transmisji danych.

## Polecenie

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl check-ports \
  --port /dev/serial0 \
  --port /dev/ttyAMA2
```

## Wynik

```json
{
  "ok": true,
  "ports": [
    {
      "port": "/dev/serial0",
      "ready": true
    },
    {
      "port": "/dev/ttyAMA2",
      "ready": true
    }
  ],
  "count": 2,
  "transmitted": false
}
```

## Potwierdzone zachowanie

- oba UART-y można otworzyć równocześnie,
- każdy port ma osobny proces `rs485-worker`,
- nie wystąpiła kolizja deskryptorów ani uprawnień,
- oba workery zgłosiły `ready: true`,
- nie wysłano żadnego bajtu przez UART ani RS-485,
- `ttyAMA10` pozostaje oddzielnym UART-em diagnostycznym i nie jest używany przez projekt.

## Granica wyniku

Test potwierdza warstwę systemową oraz procesową dwóch magistral. Nie potwierdza jeszcze:

- działania nadajników i odbiorników DFR0845,
- poprawności przewodów `T/R`,
- polaryzacji `A/B`,
- fizycznej transmisji RS-485,
- komunikacji Modbus z rzeczywistym urządzeniem.

## Następny krok

Połączenie obu DFR0845 krótkim odcinkiem magistrali i dwukierunkowy test pętli RS-485 pomiędzy `/dev/serial0` i `/dev/ttyAMA2`, bez udziału urządzeń docelowych.

Wynik: **PASS**.