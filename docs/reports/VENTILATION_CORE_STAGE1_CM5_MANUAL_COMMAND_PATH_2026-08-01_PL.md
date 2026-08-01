# ventilation-core Stage 1 — walidacja ręcznej ścieżki komend na CM5

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Cel

Potwierdzić pełną warstwową ścieżkę sterowania od lokalnego klienta `ventilationctl` do procesu sprzętowego obsługującego DFR0971.

## Wykonane komendy

```text
set --supply 2 --extract 0
stop
```

## Potwierdzony wynik programowy

Po komendzie `set` rdzeń zwrócił:

- `ok: true`,
- `mode: MANUAL`,
- `supply_voltage: 2.0`,
- `extract_voltage: 0.0`,
- `hardware_ready: true`.

Po komendzie `stop` rdzeń zwrócił:

- `ok: true`,
- `mode: STOP`,
- `supply_voltage: 0.0`,
- `extract_voltage: 0.0`,
- `hardware_ready: true`.

## Potwierdzony wynik fizyczny

Użytkownik potwierdził, że:

- wentylator podłączony do `VOUT0` uruchomił się po zadaniu `2,0 V`,
- wentylator pracował podczas stanu `MANUAL`,
- wentylator zatrzymał się po komendzie `stop`,
- kanał `VOUT1` pozostał niewykorzystany i zadany na `0 V`.

## Wniosek

Potwierdzono poprawne działanie pełnego toru programowo-sprzętowego:

```text
ventilationctl
    → Unix socket
    → runtime/server.py
    → application/service.py
    → domain
    → ProcessIsolatedActuator
    → osobny proces sprzętowy
    → DFR0971 / GP8403
    → wentylator EC 0–10 V
```

Stan autorytatywny został poprawnie przełączony z `STOP` do `MANUAL`, a następnie z powrotem do `STOP`. Proces sprzętowy zachował gotowość przez cały test, a rzeczywisty wentylator wykonał obie komendy zgodnie ze stanem rdzenia.

Stage 1 posiada więc pierwszy pozytywnie zwalidowany przypadek wykonawczy przechodzący przez wszystkie warstwy aplikacji.
