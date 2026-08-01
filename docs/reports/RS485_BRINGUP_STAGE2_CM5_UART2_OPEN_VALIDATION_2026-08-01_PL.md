# Stage 2 — walidacja otwarcia drugiego UART-u na CM5

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Zakres

Sprawdzenie drugiego sprzętowego UART-u przeznaczonego dla `RS485_BUS_2`, bez podłączonych linii A/B i bez wysyłania danych.

## Polecenie

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl check-ports \
  --port /dev/ttyAMA2
```

## Wynik

```json
{
  "ok": true,
  "ports": [
    {
      "port": "/dev/ttyAMA2",
      "ready": true
    }
  ],
  "count": 1,
  "transmitted": false
}
```

## Potwierdzone zachowanie

- `/dev/ttyAMA2` otwiera się poprawnie,
- użytkownik ma wymagane uprawnienia do portu,
- osobny `rs485-worker` uruchamia się i odpowiada na lokalny ping,
- test nie wysłał żadnych bajtów przez UART,
- test nie potwierdza jeszcze elektrycznej komunikacji przez DFR0845 ani magistralę RS-485.

## Wniosek

Drugi UART CM5 przeznaczony dla DFR0845 został zwalidowany programowo. Następny krok to jednoczesne otwarcie `/dev/serial0` i `/dev/ttyAMA2`, nadal bez transmisji, aby potwierdzić niezależne działanie dwóch workerów.

Wynik: **PASS**.
