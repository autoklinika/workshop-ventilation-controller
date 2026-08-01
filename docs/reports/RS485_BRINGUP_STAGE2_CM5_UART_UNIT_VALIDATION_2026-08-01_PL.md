# Stage 2 — walidacja testów po korekcie na DFR0845 / UART

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Zakres

Walidacja pełnego zestawu testów na docelowym CM5 po:

- przejściu z założenia USB–RS485 na DFR0845 UART ↔ RS-485,
- dodaniu obsługi UART-ów pokładowych,
- dodaniu obsługi dwóch niezależnych portów,
- korekcie dokumentacji zasilania DFR0845 na 5 V,
- korekcie kolorów przewodów Gravity: `R` niebieski, `T` zielony.

## Wynik

Użytkownik wykonał:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Wynik:

```text
Ran 34 tests in 0.005s
OK
```

## Potwierdzone obszary

- brak regresji sterowania DAC,
- brak regresji alarmu `DAC_COMMUNICATION_LOST`,
- poprawne CRC i ramki Modbus RTU,
- obsługa funkcji `0x03` i `0x04`,
- wykrywanie UART-ów pokładowych,
- klasyfikacja portów UART i USB,
- preferowanie aliasów `/dev/serial*`,
- otwieranie dwóch niezależnych workerów bez transmisji,
- odrzucanie duplikatu tego samego portu,
- kontrolowane timeouty transportu szeregowego.

## Obserwacja uruchomieniowa

Pierwsza próba:

```bash
python3 -m ventilation_core.rs485ctl check-ports --port PORT_1 --port PORT_2
```

zakończyła się `ModuleNotFoundError`, ponieważ repozytorium używa układu `src/` i pakiet nie został zainstalowany systemowo. Do uruchamiania bez instalacji należy używać:

```bash
PYTHONPATH=src python3 -m ventilation_core.rs485ctl ...
```

Nazwy `PORT_1` i `PORT_2` były placeholderami i muszą zostać zastąpione rzeczywistymi ścieżkami urządzeń Linux.

## Wniosek

Warstwa programowa Stage 2 po korekcie na DFR0845 / UART jest gotowa do pierwszej walidacji sprzętowego UART-u na CM5.

Wynik: **PASS**.
