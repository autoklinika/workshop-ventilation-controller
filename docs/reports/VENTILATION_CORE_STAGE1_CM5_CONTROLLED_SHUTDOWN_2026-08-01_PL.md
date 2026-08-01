# ventilation-core Stage 1 — walidacja kontrolowanego zamknięcia na CM5

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Wykonana operacja

Do działającego rdzenia wysłano komendę:

```text
shutdown
```

## Wynik programowy

Rdzeń zwrócił:

- `ok: true`,
- `mode: STOP`,
- `supply_voltage: 0.0`,
- `extract_voltage: 0.0`,
- `hardware_ready: true`.

## Wynik fizyczny

Użytkownik potwierdził, że wentylator pozostał zatrzymany po zamknięciu rdzenia.

## Wniosek

Kontrolowane zamknięcie `ventilation-core` działa zgodnie z założeniami:

1. warstwa aplikacyjna przechodzi do stanu `STOP`,
2. oba kanały DFR0971 są ustawiane na `0 V`,
3. proces sprzętowy kończy pracę dopiero po wykonaniu komendy zatrzymania,
4. fizyczny wentylator pozostaje zatrzymany,
5. nie zaobserwowano utraty kontroli nad DAC podczas zamykania.

Walidacja obejmuje kontrolowane zamknięcie procesu. Nie zastępuje osobnego testu nagłego przerwania procesu, awarii systemu ani zaniku komunikacji I²C.
