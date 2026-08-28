# Control Engine V1 — Stage7D: fizyczna walidacja czasu potwierdzenia TACHO 4.0 s

**Data:** 2026-08-28  
**Projekt:** Workshop Ventilation Controller  
**Gałąź:** `agent/automation-v1-control-engine`  
**Zwalidowany SHA:** `f899f0589fb05bbb56c7df298ee6a268d85d7941`

## Cel

Fizycznie zwalidować na CM5, że wybrany po Stage7A–7C parametr:

`tacho_failure_confirmation_seconds = 4.0`

nie powoduje fałszywego potwierdzenia awarii podczas rzeczywistego rozruchu lokalnych wentylatorów EC przy najniższym zwalidowanym sterowaniu `1.0 V`.

Walidacja miała również potwierdzić persistence konfiguracji na izolowanej bazie testowej, brak aktywacji fallbacków TACHO oraz brak wpływu na produkcyjny `automation.sqlite3`.

## Założenia bezpieczeństwa

- Control Engine pozostaje SHADOW-only.
- `actuation_supported=false`.
- Test używa izolowanego `automation.sqlite3`.
- Produkcyjny rekord Control Engine nie może zostać zmieniony.
- Wszystkie fallbacki TACHO pozostają `null`.
- Fizyczne wentylatory są celowo uruchamiane wyłącznie na `1.0 V`, po czym test zawsze wraca do `STOP / 0 V`.
- host-power, RTC i boot state nie mogą się zmienić.

## Wynik konfiguracji

Izolowana konfiguracja wystartowała z:

- revision `1`,
- `tacho_failure_confirmation_seconds = null`.

Patcher zmienił wyłącznie ten jeden parametr:

- revision `1 -> 2`,
- `tacho_failure_confirmation_seconds = 4.0`,
- wszystkie inne pola zachowane 1:1.

Po restarcie branch core:

- revision nadal `2`,
- `tacho_failure_confirmation_seconds = 4.0`,
- wszystkie fallbacki TACHO nadal `null`.

Persistence: **PASS**.

## Fizyczny test 1.0 V

Po zadaniu obu lokalnych kanałów EC na `1.0 V` supervisor przeszedł przez oczekiwany stan `CONFIRMING`, a następnie oba kanały osiągnęły `HEALTHY` przed upływem 4.0 s.

Zmierzono:

- supply `CONFIRMING -> HEALTHY`: `1.458396639 s`, RPM `224.1`,
- extract `CONFIRMING -> HEALTHY`: `1.561972201 s`, RPM `226.1`.

Dodatkowo:

- `confirming_seen.supply = true`,
- `confirming_seen.extract = true`,
- `false_fault_seen = false`,
- `fallback_applied = false`,
- stabilne `HEALTHY` utrzymane przez `2.0 s`.

Wynik fizycznej walidacji: **PASS**.

## Wniosek

`tacho_failure_confirmation_seconds = 4.0 s` jest przyjęte jako **fizycznie zwalidowany parametr dla obecnego układu CM5 + lokalne wentylatory EC + obecny tor TACHO**.

Uzasadnienie:

- Stage7C worst-case przy `1.0 V` dał najwolniejsze pierwsze `HEALTHY` około `1.912 s`,
- Stage7D przy aktywnym supervisorze 4.0 s potwierdził rzeczywiste przejście `CONFIRMING -> HEALTHY` bez false trip,
- 4.0 s daje ponad dwukrotny margines względem najgorszego zaobserwowanego czasu detekcji,
- czas pełnego mechanicznego rozpędzenia nie jest kryterium tej diagnostyki; supervisor wykrywa obecność wiarygodnego feedbacku TACHO.

## Czego Stage7D NIE ustala

Stage7D nie ustala reakcji wykonawczej po potwierdzonej awarii TACHO.

Nadal pozostają jawnie niezdefiniowane i `null`:

- fallback dla `SUPPLY`,
- fallback dla `EXTRACT`,
- fallback dla `BOTH`.

Nie wolno ich dobierać przez zgadywanie ani kopiowanie między maskami awarii.

## Rollback i integralność produkcji

Po teście potwierdzono:

- `STOP / 0 V`,
- brak obserwowanego ruchu lokalnych wentylatorów,
- TACHO `NOT_REQUIRED` przy 0 V,
- Control Engine SHADOW-only,
- host-power bez zmian,
- RTC bez zmian,
- boot state bez zmian,
- produkcyjny Control Engine SQLite row **niezmieniony**.

## Status

**STAGE7D: PASS**

Parametr `tacho_failure_confirmation_seconds = 4.0 s` uznajemy za fizycznie zwalidowany. Fallbacki kanałowe pozostają otwarte i wymagają osobnej decyzji/polityki.
