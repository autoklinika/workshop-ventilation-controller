# Stage 2 — diagnostyka UART CM5 przed aktywacją overlayów

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Wynik testów

Po aktualizacji gałęzi użytkownik uruchomił pełny zestaw testów:

```text
Ran 34 tests
OK
```

Wynik: **PASS**.

## Stan konfiguracji systemu

Polecenie wyszukujące konfigurację UART w `/boot/firmware/config.txt` nie zwróciło żadnych wpisów. Oznacza to, że overlaye dla UART0 i UART2 na złączu 40-pinowym nie zostały jeszcze włączone.

Linia poleceń kernela zawiera:

```text
console=ttyAMA10,115200
```

Wykryte urządzenia:

```text
/dev/serial0 -> ttyAMA10
/dev/ttyAMA10
```

`rs485ctl ports` zwrócił tylko:

```json
{
  "path": "/dev/serial0",
  "resolved_path": "/dev/ttyAMA10",
  "interface_type": "onboard-uart"
}
```

## Interpretacja

`ttyAMA10` jest UART-em debug Raspberry Pi 5 i nie jest UART0 wyprowadzonym na GPIO14/15. Nie należy używać `/dev/serial0` ani `/dev/ttyAMA10` do obsługi DFR0845.

W wyniku diagnostyki poprawiono klasyfikację portów w kodzie:

- `ttyAMA10` jest teraz oznaczany jako `debug-uart`,
- otrzymuje `usable_for_rs485: false`,
- UART-y na złączu GPIO po aktywacji overlayów pozostaną oznaczane jako `onboard-uart` i `usable_for_rs485: true`.

## Dodatkowa obserwacja

Polecenie:

```text
pinctrl get 14 15
```

zwróciło `Too many arguments`. W następnej walidacji piny będą odczytywane osobnymi poleceniami.

## Następny krok

Aktywować w `/boot/firmware/config.txt`:

```ini
enable_uart=1
dtoverlay=uart0-pi5
dtoverlay=uart2-pi5
```

Po restarcie należy potwierdzić pojawienie się UART0 i UART2 oraz funkcje GPIO14, GPIO15, GPIO4 i GPIO5. Zaciski RS-485 A/B pozostają niepodłączone.