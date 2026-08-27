# Power Scheduler M6A — walidacja runtime na CM5 bez aktuacji

Data: 2026-08-27  
Repozytorium: `autoklinika/workshop-ventilation-controller`  
Gałąź robocza: `agent/automation-v1-scheduler-assumptions`  
Testowany SHA M6: `02ecbefbdf08e0f0f1c60a4e3a300315de588a84`  
Produkcyjny `main`: `7628c407cfc9c0ea72d262566759ea2d4598fec8`

## 1. Cel

M6A potwierdza na fizycznym CM5, że zintegrowany runtime Power Scheduler może zostać uruchomiony w rzeczywistym `ventilation-core` z planowanym shutdownem pozostającym jawnie wyłączonym.

Test miał być nieaktuujący względem host power i RTC:

- bez `--enable-scheduled-shutdown`,
- bez uzbrajania RTC,
- bez żądania `shutdown/restart` do `wvc-host-power`,
- bez odcinania domeny 12 V,
- bez reboot/poweroff CM5.

Stan laboratoryjny dopuszczał `FAULT/output_state_unknown` z powodu fizycznie odłączonych DAC/SEN55/AERO, ale nadal wymagał logicznych nastaw EC `0.0 V` oraz braku obserwowanego ruchu wentylatorów.

## 2. Wynik

**M6A: PASS**

Proces testowy zakończył się:

`M6A CHILD EXIT CODE: 0`

Harness potwierdził kolejno:

- produkcyjny `main` przed testem był na oczekiwanym SHA i miał czysty working tree,
- logiczne nastawy EC były `0 V`,
- przed rolloutem nie zmienił się `boot_id`, PID host-power, RTC ani domena 12 V,
- tymczasowy branch RTC agent wystartował bez zmiany RTC,
- branch `ventilation-core` wystartował z Power Schedulerem,
- `scheduled_shutdown_enabled=false`,
- worker M6 był alive,
- RTC pozostał nieuzbrojony,
- host-power pozostał nietknięty,
- polityka AlertV2 M6 została załadowana,
- po restarcie branch core te same niezmienniki nadal obowiązywały,
- po rollbacku produkcyjny `main` został przywrócony,
- końcowo RTC i host-power nadal nie zostały użyte,
- CM5 nie wykonał reboot/poweroff,
- domena 12 V pozostała ON.

Końcowe komunikaty harnessu:

`PASS: Power Scheduler M6A runtime validated on CM5 with scheduled shutdown disabled`

`PASS: RTC wakealarm unchanged; host-power never requested; CM5 never rebooted/powered off`

## 3. Dowody runtime

- lab mode: `1`
- branch SHA: `02ecbefbdf08e0f0f1c60a4e3a300315de588a84`
- main before PID: `1218`
- branch PID #1: `26586`
- branch PID #2: `26692`
- main after PID: `27023`
- host-power PID: `714`
- boot_id: `0d75d870-287f-4fba-8fe7-410092bd7bc9`

Zmiana PID core pomiędzy kolejnymi etapami potwierdza rzeczywisty rollout branch, restart lifecycle oraz przywrócenie produkcyjnego core. Stały PID host-power i stały `boot_id` potwierdzają brak wykonania host-power i brak restartu hosta.

## 4. Znaczenie wyniku

M6A potwierdza na rzeczywistym CM5 najważniejszą właściwość wdrożeniową M6: samo zintegrowanie i uruchomienie Power Schedulera nie powoduje żadnej akcji zasilania, dopóki automatyczny scheduled shutdown nie zostanie jawnie włączony.

W połączeniu z wcześniejszym fizycznym M5B, który potwierdził pełny cykl RTC + host-power + DFR0473 + poweroff + RTC wake, mamy osobno zwalidowane:

1. aktywną ścieżkę wykonawczą M5B,
2. bezpieczną domyślną ścieżkę runtime M6A.

## 5. Status

**M6 IMPLEMENTATION: COMPLETE**  
**M6A PHYSICAL CM5 VALIDATION: PASS**

Nie wykonano merge do `main`. Automatyczny scheduled shutdown nie został włączony produkcyjnie.