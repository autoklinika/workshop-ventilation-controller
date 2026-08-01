# ventilation-core Stage 1 — walidacja restartu usługi systemd

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Cel

Potwierdzić, że restart usługi `ventilation-core.service` nie powoduje niekontrolowanego uruchomienia fana oraz że rdzeń wraca do bezpiecznego stanu po ponownym starcie.

## Wynik

Po wykonaniu:

```text
sudo systemctl restart ventilation-core.service
```

potwierdzono:

- fan nie ruszył ani na moment,
- usługa wróciła do stanu `active (running)`,
- proces główny i odseparowany worker sprzętowy zostały uruchomione ponownie,
- lokalny socket został odtworzony,
- `mode: STOP`,
- `supply_voltage: 0.0`,
- `extract_voltage: 0.0`,
- `hardware_ready: true`.

## Wniosek

Restart usługi systemowej jest bezpieczny dla aktualnej konfiguracji. Rdzeń nie odtwarza poprzedniego niezweryfikowanego zadania i po starcie jawnie przejmuje DFR0971 w stanie `0 V / 0 V`.

Pełny restart CM5 pozostaje ostatnim testem uruchomieniowym Stage 1.
