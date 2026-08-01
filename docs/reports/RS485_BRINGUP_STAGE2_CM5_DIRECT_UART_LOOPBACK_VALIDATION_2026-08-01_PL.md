# Stage 2 — walidacja bezpośredniej pętli UART0 ↔ UART2 na CM5

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Cel

Sprawdzić elektryczną sprawność obu sprzętowych UART-ów CM5 po wcześniejszych próbach z modułami DFRobot DFR0845.

Test wykonano z całkowicie odłączonymi modułami DFR0845. UART0 i UART2 połączono bezpośrednio na poziomie logiki 3,3 V:

- GPIO14 / TXD0 (pin fizyczny 8) → GPIO5 / RXD2 (pin fizyczny 29),
- GPIO4 / TXD2 (pin fizyczny 7) → GPIO15 / RXD0 (pin fizyczny 10).

## Przygotowanie systemu

UART0 był początkowo zajęty przez `agetty`, przez co `/dev/ttyAMA0` miał uprawnienia `root:tty` i nie mógł zostać otwarty przez użytkownika `wentylacja`.

Po wyłączeniu login shell na porcie szeregowym przy zachowaniu włączonego sprzętowego UART-u:

- `/dev/serial0 -> /dev/ttyAMA0`,
- `/dev/ttyAMA0` ma właściciela `root:dialout` i prawa `0660`,
- `/dev/ttyAMA2` ma właściciela `root:dialout` i prawa `0660`,
- żaden proces nie zajmuje obu portów.

Użytkownik `wentylacja` należy do grupy `dialout`.

## Polecenie testowe

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl loopback \
  --port-a /dev/serial0 \
  --port-b /dev/ttyAMA2 \
  --baudrate 9600 \
  --parity N \
  --stopbits 1 \
  --timeout 1.0
```

## Wynik

Test zakończył się powodzeniem:

```json
{
  "ok": true,
  "ports": {
    "a": "/dev/serial0",
    "b": "/dev/ttyAMA2"
  },
  "settings": {
    "baudrate": 9600,
    "parity": "N",
    "stopbits": 1,
    "bytesize": 8,
    "timeout_seconds": 1.0
  },
  "payload_hex": "57 56 43 32 2d 52 53 34 38 35",
  "a_to_b": {
    "received_hex": "57 56 43 32 2d 52 53 34 38 35",
    "matched": true
  },
  "b_to_a": {
    "received_hex": "57 56 43 32 2d 52 53 34 38 35",
    "matched": true
  },
  "transmitted": true
}
```

## Wnioski

1. UART0 i UART2 na CM5 są elektrycznie sprawne.
2. Nadajniki i odbiorniki obu UART-ów działają w obu kierunkach.
3. GPIO14, GPIO15, GPIO4 i GPIO5 nie zostały uszkodzone podczas wcześniejszych prób.
4. Mechanizm `rs485ctl loopback` oraz synchronizacja operacji surowego odczytu i zapisu działają poprawnie na rzeczywistym sprzęcie.
5. Wcześniejszy brak transmisji przez dwa DFR0845 nie wynikał z awarii UART-ów CM5.
6. Dalsza diagnostyka musi objąć moduły DFR0845, ich zasilanie i poziomy logiczne oraz stronę A/B/GND.

## Decyzja bezpieczeństwa

Do czasu przygotowania zgodnego z CM5 zasilania/logiki 3,3 V moduły DFR0845 pozostają odłączone od UART-ów. Bezpośrednie podłączenie DFR0845 zasilanego z 5 V do wejść UART CM5 jest wycofane.
