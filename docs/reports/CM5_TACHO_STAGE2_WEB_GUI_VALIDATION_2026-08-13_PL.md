# CM5 TACHO Stage 2 — walidacja Web GUI

Data: 2026-08-13

## Cel

Potwierdzić pełny tor prezentacji dla dwóch kanałów TACHO:

```text
SUPPLY TACHO -> GPIO17 -> ventilation-core Stage 2 -> Unix socket -> Web GUI PR #20
EXTRACT TACHO -> GPIO27 -> ventilation-core Stage 2 -> Unix socket -> Web GUI PR #20
```

## Konfiguracja testu

- Core: `agent/cm5-tacho-supply-stage2`
- Web GUI: `agent/web-gui-manual-control-stage1`
- testowy core socket: `/tmp/wvc-tacho-stage2.sock`
- testowe Web GUI: osobny port testowy
- AERO BUS: fizycznie odłączony, celowo pominięty w tym teście
- SENSOR BUS i DAC pozostają niezależne

## Wynik — PASS

Web GUI poprawnie prezentuje oba kanały TACHO jako osobne, read-only feedbacki RPM.

### Punkt pomiarowy 1 — 1.0 V

GUI pokazało:

```text
NAWIEW / SUPPLY
Sterowanie: 10%
Napięcie: 1.0 V
Obroty: 520 RPM
TACHO: sygnał OK
26.0 Hz · GPIO17

WYCIĄG / EXTRACT
Sterowanie: 10%
Napięcie: 1.0 V
Obroty: 511 RPM
TACHO: sygnał OK
25.6 Hz · GPIO27
```

Wartości są zgodne z kontraktem `3 imp/obrót` i `RPM = Hz * 20`.

### Punkt pomiarowy 2 — 10.0 V

GUI pokazało:

```text
NAWIEW / SUPPLY
Sterowanie: 100%
Napięcie: 10.0 V
Obroty: 2329 RPM
TACHO: sygnał OK
116.5 Hz · GPIO17

WYCIĄG / EXTRACT
Sterowanie: 100%
Napięcie: 10.0 V
Obroty: 2369 RPM
TACHO: sygnał OK
118.4 Hz · GPIO27
```

Oba kanały zachowują poprawne mapowanie GPIO i niezależny rzeczywisty odczyt RPM.

## Wnioski

Pełna ścieżka Stage 2 została zwalidowana:

```text
SUPPLY / GPIO17 -> core -> API -> GUI: PASS
EXTRACT / GPIO27 -> core -> API -> GUI: PASS
```

GUI nie oblicza RPM samodzielnie — prezentuje autorytatywne `state.tacho.<channel>.rpm` z `ventilation-core`.

Brak zmian w kontrakcie bezpieczeństwa:

- TACHO pozostaje read-only,
- brak sygnału TACHO nie zmienia setpointu DAC,
- brak sygnału TACHO nie ustawia FAULT,
- GUI nie uzyskuje bezpośredniego dostępu do GPIO.

## Status

Walidacja hardware/runtime SUPPLY TACHO: **PASS**.

Walidacja Web GUI SUPPLY + EXTRACT: **PASS**.

PR #22 pozostaje Draft do jawnej decyzji użytkownika o dalszym lifecycle / merge.
