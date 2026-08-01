# Stage 2 — elektryczny test pętli dwóch DFR0845

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Cel

Potwierdzić rzeczywistą transmisję elektryczną przez dwa moduły DFR0845 i oba sprzętowe UART-y CM5 bez podłączania urządzeń docelowych.

Test przesyła stały wzorzec:

```text
57 56 43 32 2D 52 53 34 38 35
```

Jest to ASCII `WVC2-RS485`.

Transmisja wykonywana jest kolejno:

1. `/dev/serial0` → DFR0845 nr 1 → RS-485 → DFR0845 nr 2 → `/dev/ttyAMA2`,
2. `/dev/ttyAMA2` → DFR0845 nr 2 → RS-485 → DFR0845 nr 1 → `/dev/serial0`.

## Warunki bezpieczeństwa

- wyłączyć CM5 przed zmianą okablowania,
- oba DFR0845 pozostają zasilane po stronie Gravity z 5 V,
- nie podłączać zacisków `12V` ani `12V-IN`,
- nie podłączać żadnego SEN55, KAmod ani rekuperatora,
- terminację `120Ω` pozostawić początkowo `OFF` na obu modułach,
- użyć krótkiego przewodu testowego.

## Połączenie strony RS-485

Połączyć zielone listwy obu DFR0845:

| DFR0845 nr 1 | DFR0845 nr 2 |
|---|---|
| `A` | `A` |
| `B` | `B` |
| `GND` strony RS-485 | `GND` strony RS-485 |

Pozostawić niepodłączone:

- `RS485 12V`,
- `12V-IN 12V`,
- `12V-IN GND`.

Zalecany jest krótki skręcony przewód dla `A/B`. Dla pierwszej próby wystarczy kilkadziesiąt centymetrów.

## Aktualizacja i testy automatyczne

Po włączeniu CM5:

```bash
cd ~/workshop-ventilation-controller

git pull --ff-only origin agent/rs485-bringup-stage2

PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Oczekiwany wynik po dodaniu pętli:

```text
Ran 41 tests
OK
```

## Test elektryczny

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl loopback \
  --port-a /dev/serial0 \
  --port-b /dev/ttyAMA2 \
  --baudrate 9600 \
  --parity N \
  --stopbits 1 \
  --timeout 1.0
```

## Oczekiwany wynik

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

## Interpretacja

Wynik `PASS` potwierdza łącznie:

- poprawne piny UART obu DFR0845,
- poprawne połączenie `T/R` po stronie Gravity,
- działanie nadajnika i odbiornika obu DFR0845,
- poprawne połączenie `A/B/GND`,
- dwukierunkową transmisję przez RS-485,
- poprawne działanie dwóch niezależnych workerów podczas rzeczywistej transmisji.

## Diagnostyka błędu

Jeżeli wystąpi timeout:

1. wyłączyć CM5,
2. sprawdzić `A↔A`, `B↔B`, `GND↔GND`,
3. sprawdzić przewody Gravity:
   - niebieski `R` do TX CM5,
   - zielony `T` do RX CM5,
4. ponownie uruchomić test.

Dopiero jeśli okablowanie jest zgodne, a timeout pozostaje, wykonać kontrolowaną próbę z zamianą `A/B` tylko po jednej stronie. Nie zmieniać kilku elementów jednocześnie.

## Następny krok po PASS

Po zaliczeniu pętli oba DFR0845 są sprzętowo gotowe. Następnie do jednej magistrali podłączymy pierwsze rzeczywiste urządzenie i wykonamy bezpieczny odczyt Modbus funkcją `0x03` albo `0x04`.