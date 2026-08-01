# Stage 1.5 — walidacja wykrycia odłączenia DAC na CM5

Data: 2026-08-01

Gałąź: `agent/dac-alarm-supervision-stage1-5`

## Warunki testu

- `ventilation-core` uruchomiony jako usługa `systemd`,
- stan początkowy `STOP`,
- oba kanały zadane na 0 V,
- fan zatrzymany,
- DFR0971 odłączony od magistrali I²C podczas pracy rdzenia.

## Wynik

Po odłączeniu DFR0971 i odczekaniu kilku cykli health-checku rdzeń pozostał dostępny przez Unix socket i zwrócił:

```json
{
  "ok": true,
  "state": {
    "mode": "FAULT",
    "setpoints": {
      "supply_voltage": 0.0,
      "extract_voltage": 0.0
    },
    "hardware_ready": false,
    "output_state_known": false,
    "consecutive_hardware_failures": 10,
    "active_alarms": [
      {
        "code": "DAC_COMMUNICATION_LOST",
        "severity": "critical",
        "message": "Brak komunikacji z DAC DFR0971",
        "active_since": "2026-08-01T09:37:28.684251+00:00",
        "last_error": "No response from GP8403 at 0x58: [Errno 121] Remote I/O error",
        "occurrences": 10
      }
    ]
  }
}
```

## Potwierdzone zachowanie

- rdzeń nie zakończył procesu po utracie komunikacji,
- status pozostał dostępny,
- tryb przeszedł do `FAULT`,
- `hardware_ready` przyjął `false`,
- stan wyjść został jawnie oznaczony jako nieznany,
- aktywowany został krytyczny alarm `DAC_COMMUNICATION_LOST`,
- licznik kolejnych błędów zwiększał się zgodnie z cyklem health-checku,
- błąd systemowy został poprawnie rozpoznany jako `Errno 121 Remote I/O error`,
- fan pozostał zatrzymany, ponieważ test rozpoczęto przy 0 V.

## Wniosek

Mechanizm wykrywania braku komunikacji z DFR0971 działa poprawnie na docelowym CM5. Kolejnym testem jest ponowne podłączenie DAC i potwierdzenie automatycznego, bezpiecznego odzyskania do `STOP / 0 V / 0 V` bez samoczynnego uruchomienia fana.
