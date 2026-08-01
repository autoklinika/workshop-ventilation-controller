# Stage 2 — walidacja otwarcia pierwszego UART-u na CM5

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Warunki

- aktywny overlay `uart0-pi5`,
- `/dev/serial0` wskazuje na `/dev/ttyAMA0`,
- pierwszy DFR0845 jest podłączony po stronie UART,
- zaciski A/B pozostają odłączone,
- terminacja 120 Ω pozostaje wyłączona,
- test wykonywany bez transmisji danych.

## Polecenie

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl check-ports \
  --port /dev/serial0
```

## Wynik

```json
{
  "ok": true,
  "ports": [
    {
      "port": "/dev/serial0",
      "ready": true
    }
  ],
  "count": 1,
  "transmitted": false
}
```

## Potwierdzone zachowanie

- użytkownik ma uprawnienia do otwarcia portu,
- `pyserial` poprawnie otwiera `/dev/serial0`,
- osobny proces `rs485-worker` uruchamia się poprawnie,
- lokalny ping procesu przechodzi,
- test nie wysłał żadnych bajtów na UART,
- port został poprawnie zamknięty po zakończeniu testu.

Wynik: **PASS**.

## Następny krok

Powtórzyć identyczny test dla drugiego sprzętowego UART-u `/dev/ttyAMA2`, nadal bez podłączania A/B i bez transmisji.
