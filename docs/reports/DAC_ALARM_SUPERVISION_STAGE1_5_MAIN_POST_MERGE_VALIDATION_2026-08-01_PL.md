# Stage 1.5 — walidacja po integracji do main

Data: 2026-08-01

## Zakres

Końcowa walidacja `ventilation-core` na docelowym CM5 po scaleniu PR #2 i przełączeniu lokalnego repozytorium na gałąź `main`.

## Potwierdzony commit

```text
798478b Merge DAC alarm supervision Stage 1.5
```

Lokalny stan repozytorium:

```text
HEAD -> main
origin/main
origin/HEAD
```

## Potwierdzony stan runtime

Odczyt przez lokalny Unix socket zwrócił:

```json
{
  "ok": true,
  "state": {
    "mode": "STOP",
    "setpoints": {
      "supply_voltage": 0.0,
      "extract_voltage": 0.0
    },
    "hardware_ready": true,
    "output_state_known": true,
    "consecutive_hardware_failures": 0,
    "active_alarms": []
  }
}
```

## Wniosek

- CM5 pracuje z aktualnym `main`,
- usługa uruchomiła się poprawnie po integracji,
- DAC jest dostępny,
- stan wyjść jest znany,
- oba kanały pozostają zadane na 0 V,
- brak aktywnych alarmów,
- licznik błędów komunikacji jest wyzerowany,
- Stage 1.5 jest stabilną bazą do rozpoczęcia Stage 2 — RS-485 bring-up.

Wynik: **PASS**.
