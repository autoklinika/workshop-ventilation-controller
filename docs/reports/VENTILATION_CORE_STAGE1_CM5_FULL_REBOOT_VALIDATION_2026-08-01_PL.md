# ventilation-core Stage 1 — walidacja pełnego restartu CM5

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Cel

Potwierdzić, że po pełnym restarcie Raspberry Pi Compute Module 5 usługa `ventilation-core` uruchamia się automatycznie, przejmuje DFR0971 i zachowuje bezpieczny stan wyjść.

## Przebieg

Wykonano pełny restart systemu poleceniem:

```text
sudo reboot
```

Po ponownym uruchomieniu zweryfikowano:

- stan jednostki `systemd`,
- stan aplikacyjny przez `ventilationctl`,
- fizyczne zachowanie fana podłączonego do kanału 0.

## Wynik

Jednostka systemowa:

- `Loaded: loaded`,
- `enabled`,
- `Active: active (running)`,
- uruchomiona automatycznie podczas startu systemu.

Stan rdzenia po restarcie:

- `mode: STOP`,
- `supply_voltage: 0.0`,
- `extract_voltage: 0.0`,
- `hardware_ready: true`.

Potwierdzenie fizyczne użytkownika:

- fan nie ruszył podczas restartu ani po uruchomieniu usługi.

## Wniosek

Pełny tor startowy działa poprawnie:

```text
boot CM5
    → systemd
    → ventilation-core
    → osobny worker sprzętowy
    → DFR0971 / GP8403
    → oba kanały 0 V
```

Walidacja potwierdza, że `ventilation-core` Stage 1 jest gotowy do stałej pracy jako usługa systemowa dla pierwszego kanału fana EC.

## Status Stage 1

Stage 1 uznaje się za zakończony. Potwierdzono:

- 9/9 testów jednostkowych,
- ręczny start rdzenia,
- lokalne API przez Unix socket,
- pełną warstwową ścieżkę komend,
- fizyczne uruchomienie i zatrzymanie fana,
- kontrolowane zamknięcie,
- bezpieczny restart usługi,
- automatyczny i bezpieczny start po pełnym restarcie CM5.
