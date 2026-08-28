# Control Engine V1 — Stage7C: fizyczna charakterystyka TACHO przy 1,0 V

**Data:** 2026-08-28  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/automation-v1-control-engine`  
**Zwalidowany SHA:** `6025f29d48f62f28964b022fbf2ac9859c6c81a1`

## Wynik

**PASS — fizyczna charakterystyka low-speed TACHO na CM5 zakończona poprawnie.**

Test wykonał 3 niezależne cykle:

- `STOP / 0 V`,
- oba lokalne wentylatory EC: `1,0 V` przez `20 s`,
- pełny pomiar TACHO podczas rozruchu i pracy ustalonej,
- powrót do `STOP / 0 V`,
- `3 s` postoju między cyklami.

Control Engine przez cały test pozostał SHADOW-only.

## Czas do pierwszego wiarygodnego TACHO

| Cykl | Supply | Extract |
|---|---:|---:|
| 1 | 1,623 s | 1,623 s |
| 2 | 1,912 s | 1,386 s |
| 3 | 1,488 s | 1,593 s |

Najgorszy zaobserwowany czas:

- supply: **1,912 s**,
- extract: **1,623 s**.

Wartość `1,912 s` jest aktualnym fizycznie zmierzonym worst-case dla pojawienia się poprawnego feedbacku TACHO przy najniższym legalnym sterowaniu EC `1,0 V`.

## Praca ustalona przy 1,0 V

Średnie RPM z końcowego 7-sekundowego okna:

| Cykl | Supply | Extract |
|---|---:|---:|
| 1 | 404,16 RPM | 411,61 RPM |
| 2 | 406,92 RPM | 415,11 RPM |
| 3 | 408,42 RPM | 408,80 RPM |

Średnia z trzech cykli:

- supply: **406,50 RPM**,
- extract: **411,84 RPM**.

Rozrzut w końcowym oknie był mały — maksymalnie ok. `5,21 RPM` supply i `5,04 RPM` extract w cyklu 3.

Wynik jest zgodny z wcześniejszą sprzętową charakterystyką, w której przy `1,0 V` otrzymano ok. `399 RPM`.

## Wniosek dla czasu potwierdzenia awarii TACHO

Nie należy używać czasu pełnego mechanicznego rozpędzenia wentylatora jako czasu detekcji awarii TACHO. Supervisor potrzebuje jedynie czasu, w którym zdrowy, rzeczywiście uruchomiony wentylator powinien wygenerować wiarygodny feedback.

Na podstawie Stage7A–7C przyjmujemy do dalszej walidacji:

`TACHO failure confirmation candidate = 4,0 s`

Uzasadnienie:

- najgorszy zmierzony `first HEALTHY`: `1,912 s`,
- `4,0 s` daje ponad dwukrotny zapas względem worst-case,
- nie opóźnia wykrycia rzeczywistej awarii o kilkanaście sekund,
- parametr dotyczy tylko kanału fizycznie wysterowanego `>0 V`,
- przy `0 V` TACHO pozostaje `NOT_REQUIRED`.

**4,0 s nie jest jeszcze cichym/globalnym defaultem.** Ma zostać zastosowane jawnie jako zwalidowany parametr sprzętowy i następnie sprawdzone w runtime z rzeczywistym rozruchem 1,0 V.

## Granice i bezpieczeństwo

Podczas Stage7C potwierdzono:

- po każdym cyklu `STOP / 0 V`,
- brak obserwowanego ruchu po cleanup,
- TACHO po STOP: `NOT_REQUIRED`,
- `actuation_supported=false`,
- brak automatycznej aktuacji Control Engine,
- brak zapisu tuningu przez validator,
- host-power bez zmian,
- RTC wakealarm bez zmian,
- boot state bez zmian,
- scheduled shutdown wyłączony.

## Następny krok

Stage7D powinien zwalidować kandydat `4,0 s` w runtime:

1. uruchomić Control Engine z izolowaną konfiguracją zawierającą tylko `tacho_failure_confirmation_seconds=4,0`,
2. wykonać fizyczny rozruch `1,0 V`,
3. potwierdzić przejście `CONFIRMING -> HEALTHY` bez `FEEDBACK_MISSING_CONFIRMED`,
4. wrócić do `STOP / 0 V`,
5. nie ustawiać jeszcze fallbacków SUPPLY / EXTRACT / BOTH.

Fallbacki pozostają `None` do osobnej walidacji ich semantyki i wartości.