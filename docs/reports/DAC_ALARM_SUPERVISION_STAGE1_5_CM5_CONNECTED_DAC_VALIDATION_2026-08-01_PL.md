# Stage 1.5 — walidacja startu z podłączonym DAC na CM5

Data: 2026-08-01

Gałąź: `agent/dac-alarm-supervision-stage1-5`

## Zakres

Walidacja nowej wersji `ventilation-core` zawierającej alarmy i nadzór komunikacji z DFRobot DFR0971 / GP8403 przy normalnie podłączonym DAC.

## Wynik

Użytkownik potwierdził, że etap uruchomienia nowej wersji zakończył się poprawnie.

Potwierdzone zachowanie:

- kod Stage 1.5 został uruchomiony na docelowym CM5,
- DAC był podłączony,
- usługa uruchomiła się poprawnie,
- fan nie uruchomił się podczas startu,
- system pozostał gotowy do następnego testu: kontrolowanego odłączenia DAC przy 0 V.

## Następny test

Kontrolowane odłączenie przewodu I2C / Gravity od DFR0971 przy zatrzymanym fanie i obu kanałach ustawionych na 0 V.

Oczekiwane po co najmniej 4 sekundach:

- `mode: FAULT`,
- `hardware_ready: false`,
- `output_state_known: false`,
- `consecutive_hardware_failures >= 3`,
- aktywny alarm `DAC_COMMUNICATION_LOST`,
- usługa `ventilation-core.service` nadal `active (running)`,
- fan pozostaje zatrzymany.
