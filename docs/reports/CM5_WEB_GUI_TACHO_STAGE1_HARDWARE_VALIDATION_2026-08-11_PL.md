# Web GUI + CM5 TACHO Stage 1 — walidacja sprzętowa GUI

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Gałąź GUI:** `agent/web-gui-manual-control-stage1`  
**PR GUI:** #20 — Draft  
**Gałąź TACHO:** `agent/cm5-tacho-stage1`  
**PR TACHO:** #21 — Draft  
**Wynik:** PASS

## 1. Cel

Zweryfikować na rzeczywistym CM5, że Web GUI poprawnie prezentuje nowy, read-only kontrakt `CoreState.tacho` dla kanału EXTRACT i nie miesza feedbacku TACHO z autorytatywnym sterowaniem DAC.

Zakres obejmował:

- prezentację `command / voltage / actual RPM`,
- poprawne zachowanie przy `tacho.extract.valid=false`,
- brak wpływu utraty TACHO na ręczne sterowanie,
- automatyczne odzyskanie RPM po ponownym podłączeniu przewodu TACHO,
- uruchomienie GUI bez restartowania produkcyjnego `ventilation-core`.

## 2. Bezpieczna konfiguracja testu

Produkcyjny checkout CM5 pozostał na gałęzi TACHO:

```text
branch: agent/cm5-tacho-stage1
HEAD:   7186d2dd69509e6d2a104857bbb1260b32bc07f4
```

Aktualny head origin PR #21 podczas walidacji:

```text
d20a89c8d0a74b0cc209be4e26d022f3963df3cb
```

Porównanie `7186d2d..d20a89c` wykazało, że po produkcyjnym commicie zmieniał się wyłącznie raport `CM5_TACHO_STAGE1_RUNTIME_VALIDATION_2026-08-11_PL.md`; kod runtime TACHO pozostał bez zmian.

Web GUI uruchomiono z osobnego worktree:

```text
/home/wentylacja/workshop-ventilation-web-gui-stage1
```

na commicie:

```text
4ea8d3f60524791cf713ed6b62d41135d49b5e65
```

Testowa instancja Web GUI działała na:

```text
http://192.168.1.64:18088
```

i korzystała z produkcyjnego socketu:

```text
/run/workshop-ventilation/ventilation-core.sock
```

PID `ventilation-core` przed i po uruchomieniu GUI był identyczny:

```text
60300
```

Wniosek: Web GUI zostało zwalidowane bez restartu produkcyjnego core.

## 3. Smoke test STOP — PASS

Przed uruchomieniem wentylatora runtime raportował:

```text
mode: STOP
setpoints: 0.0 / 0.0 V
hardware_ready: true
output_state_known: true
active_alarms: []
tacho.ready: true
tacho.worker_alive: true
tacho.last_error: null
tacho.supply: null
tacho.extract.valid: false
tacho.extract.frequency_hz: 0.0
tacho.extract.rpm: 0.0
```

GUI poprawnie interpretowało:

```text
SUPPLY: TACHO nie skonfigurowano
EXTRACT: RPM — / TACHO brak sygnału
```

Brak sygnału przy STOP nie został pokazany jako potwierdzone `0 RPM`.

## 4. EXTRACT 5,0 V — PASS

Przez Web GUI zadano ręcznie:

```text
SUPPLY: 0.0 V
EXTRACT: 5.0 V
```

GUI pokazało:

```text
Sterowanie: 50%
Napięcie:   5,0 V
Obroty:     około 1400 RPM
TACHO:      sygnał OK
GPIO:       GPIO27
```

Przykładowy ekran podczas testu:

```text
50%
5,0 V
1396 RPM
69,8 Hz · GPIO27
```

Niezależny odczyt `ventilation-core` potwierdził:

```text
mode: MANUAL
supply_voltage: 0.0
extract_voltage: 5.0
hardware_ready: true
active_alarms: []
tacho_valid: true
```

Porównanie dwóch niezależnych odczytów CORE i WEB dało:

```text
CORE mode=MANUAL extract=5.0 valid=True rpm=1401.5 hz=70.073 age=0.000
WEB  mode=MANUAL extract=5.0 valid=True rpm=1401.8 hz=70.088 age=0.008
```

Różnica RPM/Hz była wyłącznie skutkiem odczytu w dwóch różnych chwilach.

Wniosek: GUI poprawnie prezentuje autorytatywny command oraz niezależny actual feedback.

## 5. Fizyczne odłączenie TACHO przy pracującym wentylatorze — PASS

Przy nadal aktywnym:

```text
EXTRACT = 5.0 V
```

fizycznie odłączono wyłącznie przewód sygnałowy TACHO od GPIO27.

Wentylator nadal pracował fizycznie.

GUI automatycznie przeszło do:

```text
Sterowanie: 50%
Napięcie:   5,0 V
Obroty:     —
TACHO:      brak sygnału
GPIO27 · brak aktualnych impulsów
```

`ventilation-core` raportował równocześnie:

```text
mode: MANUAL
supply_voltage: 0.0
extract_voltage: 5.0
hardware_ready: True
output_state_known: True
active_alarms: []
tacho_ready: True
worker_alive: True
last_error: None
tacho_valid: False
tacho_hz: 0.0
tacho_rpm: 0.0
tacho_age: 15.55 s
```

Wniosek: utrata TACHO nie wpływa na sterowanie, a GUI nie przedstawia runtime `rpm=0.0` jako pewnego potwierdzenia zatrzymania wirnika.

## 6. Ponowne podłączenie TACHO bez restartu — PASS

Przewód TACHO ponownie podłączono do GPIO27 przy nadal pracującym EXTRACT = 5.0 V.

Bez restartu `ventilation-core` i bez restartu Web GUI panel automatycznie wrócił do:

```text
Sterowanie: 50%
Napięcie:   5,0 V
Obroty:     1409 RPM
TACHO:      sygnał OK
70,4 Hz · GPIO27
```

Niezależny odczyt core:

```text
mode: MANUAL
extract_voltage: 5.0
hardware_ready: True
output_state_known: True
active_alarms: []
tacho_ready: True
worker_alive: True
last_error: None
tacho_valid: True
tacho_hz: 70.43268512540011
tacho_rpm: 1408.6537025080022
tacho_age: 0.008756770002946723
```

Użytkownik potwierdził, że wentylator fizycznie pracował podczas odzyskania feedbacku.

Wniosek: ścieżka `valid=false -> valid=true` jest poprawnie odzwierciedlana w Web GUI bez restartu core.

## 7. AERO BUS pozostaje niezależny

Podczas walidacji AERO BUS pozostawał wcześniej zgłoszonym, niezależnym stanem niedostępnym.

GUI pokazywało równocześnie:

```text
Core / DAC: OK
SENSOR BUS: OK
AERO BUS: NIEDOSTĘPNY
```

Stan AERO nie wpływał na prezentację ani działanie TACHO.

## 8. Walidacja testów Web GUI

Na CM5, w osobnym worktree, wykonano testy Web GUI:

```text
Ran 19 tests
OK
```

Obejmowały m.in.:

- brak generic command proxy,
- zachowanie istniejących endpointów manual control,
- rozdzielenie command / voltage / RPM,
- `valid=false -> RPM: —`,
- neutralne `tacho.supply == null`,
- read-only renderer TACHO,
- brak TACHO w warunku blokowania manualnego sterowania,
- statyczną dostępność `tacho.js`.

## 9. Zbiorczy wynik

Web GUI + TACHO Stage 1 dla EXTRACT uzyskuje wynik:

```text
HARDWARE / RUNTIME / GUI PRESENTATION PASS
```

Potwierdzono:

- poprawny odczyt żywego `CoreState.tacho`,
- poprawne `command / voltage / actual`,
- brak fałszywego `0 RPM` przy nieważnym feedbacku,
- izolację TACHO od sterowania,
- utrzymanie MANUAL i 5,0 V przy odłączonym sygnale,
- automatyczny powrót RPM po ponownym podłączeniu,
- brak restartu `ventilation-core`,
- brak wpływu AERO BUS na TACHO.

## 10. Granice etapu

Nadal nie wdrożono:

- command-vs-actual alarm,
- fan stopped alarm,
- under-speed / over-speed,
- oczekiwanej charakterystyki RPM względem 0–10 V,
- closed-loop RPM,
- automatycznego STOP po utracie TACHO,
- drugiego kanału TACHO SUPPLY.

PR #20 i PR #21 pozostają Draft. Ten raport nie wykonuje merge ani Ready for Review.
