# Control Engine V1 — Stage 4–6 CM5 non-actuating validation

Data: 2026-08-28

Repozytorium: `autoklinika/workshop-ventilation-controller`

Branch: `agent/automation-v1-control-engine`

Zwalidowany kod: `a25ef8772be19532b4333fc4f1bb522070b616ba`

GitHub Actions dla zwalidowanego kodu: `33162940890` — SUCCESS (`compile` PASS, `unit tests` PASS).

## Cel

Fizycznie potwierdzić na docelowym CM5 granice bezpieczeństwa Stage 4–6 bez uruchamiania wentylatorów i bez aktuacji Control Engine.

Validator:

`tools/install_validate_control_engine_stage4_6_cm5.sh`

Test był wykonywany przy zastanym rzeczywistym wyjściu EC `0 V` i bez obserwowanego ruchu lokalnych wentylatorów.

## Wynik

**PASS — Stage 4–6 CM5 non-actuating validation.**

### Preflight produkcji

Potwierdzono:

- EC supply = `0 V`,
- EC extract = `0 V`,
- brak obserwowanego ruchu lokalnych wentylatorów,
- niezmieniony boot ID,
- ten sam proces i stan `wvc-host-power`,
- niezmieniony RTC wakealarm.

### Start brancha testowego

Branch został uruchomiony z izolowanego worktree na dokładnym SHA:

`a25ef8772be19532b4333fc4f1bb522070b616ba`

Potwierdzono:

- branch core aktywny,
- scheduled shutdown pozostaje wyłączony,
- fizyczne wyjścia EC nadal `0 V`,
- brak ruchu lokalnych wentylatorów,
- `SHADOW-only`,
- supply TACHO = `NOT_REQUIRED`,
- extract TACHO = `NOT_REQUIRED`,
- operator = `AUTO`, revision `0`,
- operator intent jest volatile i nie posiada authority do aktuacji,
- boot/host-power/RTC bez zmian.

### AUTO -> MANUAL

Wprowadzono wyłącznie logiczny operator intent SHADOW:

- supply = `37%`,
- extract = `43%`,
- AERO speed = `2`.

Potwierdzono:

- operator = `MANUAL`, revision `1`,
- MANUAL jest widoczny w autorytatywnej telemetrii SHADOW,
- fizyczne wyjścia EC pozostały `0 V`,
- brak ruchu lokalnych wentylatorów,
- oba kanały TACHO nadal `NOT_REQUIRED`,
- Control Engine nie uzyskał authority do aktuacji,
- boot/host-power/RTC bez zmian.

### MANUAL -> AUTO

Potwierdzono:

- operator = `AUTO`, revision `2`,
- EC nadal `0 V`,
- oba TACHO nadal `NOT_REQUIRED`,
- brak aktuacji,
- boot/host-power/RTC bez zmian.

### Restart ventilation-core

Po restarcie core potwierdzono:

- branch core ponownie aktywny,
- scheduled shutdown nadal wyłączony,
- operator automatycznie wrócił do `AUTO`, revision `0`,
- MANUAL nie przetrwał restartu,
- EC nadal `0 V`,
- brak ruchu lokalnych wentylatorów,
- oba kanały TACHO = `NOT_REQUIRED`,
- boot ID bez zmian,
- proces/stan host-power bez zmian,
- RTC wakealarm bez zmian.

## Potwierdzone kontrakty Stage 4–6

1. `MANUAL` jest core-owned, volatile i SHADOW-only.
2. Restart core resetuje operator intent do `AUTO`, revision `0`.
3. Calendar nie został użyty do ustawiania MANUAL.
4. Control Engine nie zmienił fizycznych wyjść podczas całego testu.
5. Przy rzeczywistym `0 V` brak impulsów TACHO jest prawidłowo klasyfikowany jako `NOT_REQUIRED`, nie jako fault.
6. `actuation_supported=false` pozostaje skuteczną granicą runtime.
7. `proposed_supply_voltage` i `proposed_extract_voltage` nie stają się fizycznymi poleceniami.
8. Test nie zmienił RTC ani host-power i nie wykonał shutdown/reboot.
9. Scheduled shutdown pozostaje wyłączony.
10. Validator zakończył się poprawnie i wykonał rollback do produkcyjnego runtime.

## Czego ten test NIE waliduje

Ten test celowo nie uruchamiał wentylatorów. Nie waliduje jeszcze:

- czasu `tacho_failure_confirmation_seconds` na realnym rozpędzającym się wentylatorze,
- realnego przejścia `HEALTHY -> CONFIRMING -> FEEDBACK_MISSING_CONFIRMED`,
- zachowania przy fizycznej utracie tylko supply TACHO,
- zachowania przy fizycznej utracie tylko extract TACHO,
- zachowania przy fizycznej utracie obu TACHO,
- produkcyjnych wartości fallback SUPPLY / EXTRACT / BOTH,
- fizycznej automatycznej aktuacji Control Engine.

Te elementy pozostają oddzielnym etapem walidacji sprzętowej. Produkcyjne wartości fallback nadal pozostają `None` i nie wolno ich zgadywać.

## Status końcowy

**Stage 4–6 non-actuating CM5 validation: PASS.**

Zwalidowany kod pozostaje dokładnie:

`a25ef8772be19532b4333fc4f1bb522070b616ba`

Raportowy commit nie zmienia semantyki zwalidowanego kodu.
