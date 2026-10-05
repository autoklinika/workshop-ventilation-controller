# Power Scheduler M6 — integracja runtime

Data: 2026-08-27  
Repozytorium: `autoklinika/workshop-ventilation-controller`  
Gałąź robocza: `agent/automation-v1-scheduler-assumptions`  
Produkcyjny `main` podczas realizacji M6: `7628c407cfc9c0ea72d262566759ea2d4598fec8`

## 1. Cel M6

M6 integruje zwalidowany w etapach M4/M5 mechanizm planowanego wyłączania i budzenia CM5 z rzeczywistym runtime `ventilation-core`, bez osłabiania istniejących granic bezpieczeństwa.

M6 nie zmienia zasady odpowiedzialności komponentów:

- Calendar Engine odpowiada za `kiedy` i za profil pracy,
- Power Scheduler decyduje, czy wolno przygotować planowane wyłączenie,
- RTC wake alarm przechowuje wyłącznie najbliższy termin uruchomienia,
- `wvc-host-power` pozostaje jedyną granicą wykonującą host `shutdown/restart` i odcinającą domenę 12 V przez DFR0473,
- `ventilation-core` pozostaje autorytatywnym właścicielem logiki,
- GUI i Home Assistant nie otrzymują nowej władzy sterującej.

## 2. Twarde zasady bezpieczeństwa

Planowane automatyczne wyłączenie CM5 jest **domyślnie wyłączone**. Włączenie wymaga jawnej flagi runtime:

`--enable-scheduled-shutdown`

Produkcyjny `deploy/systemd/ventilation-core.service` w M6 tej flagi nie zawiera.

Przed przekroczeniem granicy host-power Power Scheduler wymaga kolejno:

1. poprawnego rozstrzygnięcia Calendar Engine,
2. fazy `INACTIVE`,
3. trybu `STANDBY` lub `OFF`,
4. poprawnego `next_wake`,
5. minimalnego wyprzedzenia czasu wake,
6. uzbrojenia RTC,
7. dokładnego read-back RTC zgodnego z oczekiwanym epoch,
8. dopiero wtedy dokładnego żądania `shutdown` do istniejącego host-power.

Brak spełnienia któregokolwiek warunku pozostawia CM5 uruchomiony.

## 3. Granica uprawnień RTC

`ventilation-core` nadal pracuje jako użytkownik `wentylacja` i zachowuje `NoNewPrivileges=true`.

Core nie otrzymał bezpośredniego prawa zapisu do `/sys/class/rtc/rtc0/wakealarm`.

Dodano osobny lokalny agent:

`wvc-rtc-wake.service`

Agent:

- działa jako `root`,
- komunikuje się wyłącznie przez lokalny `AF_UNIX`,
- akceptuje tylko trzy jawne operacje: `read`, `clear`, `arm`,
- nie ma ścieżki host-power,
- nie wykonuje poleceń shell/systemd,
- dla `arm` wymusza read-back poprzez istniejący `SysfsRtcWakeAlarm`.

Core komunikuje się z nim przez `RtcWakeAgentClient`.

## 4. Granica host-power

Istniejący protokół `wvc-host-power` nie został rozszerzony.

Nadal dopuszcza wyłącznie:

- `shutdown`,
- `restart`.

Power Scheduler może wysłać tylko dokładne `shutdown` i wyłącznie po poprawnej weryfikacji RTC.

Zachowana pozostaje zwalidowana sekwencja host-power:

1. próba EC STOP / 0 V,
2. best-effort zatrzymanie peryferiów/AERO,
3. DFR0473 — domena 12 V OFF,
4. systemd host power action.

## 5. Runtime Power Scheduler

Dodano `PowerSchedulerRuntime` jako lekki worker niezależny od pętli sterowania DAC.

Właściwości:

- okresowe obliczanie stanu Power Schedulera,
- pierwszy tick opóźniony o jeden interwał, aby serwer Unix core był już dostępny dla ścieżki bezpieczeństwa host-power,
- `snapshot()` jest bez efektów ubocznych,
- odczyt `status` nie uzbraja RTC i nie wysyła host-power,
- najwyżej jedna próba dla danego `next_wake_at_utc`,
- wyjątek workera nie kończy `ventilation-core`,
- stan jest publikowany w `CoreState.power_scheduler`.

Publikowana diagnostyka obejmuje m.in.:

- `scheduled_shutdown_enabled`,
- `shutdown_ready`,
- `next_shutdown_at`,
- `next_wake_at_local`,
- `next_wake_at_utc`,
- `rtc_alarm_armed`,
- `rtc_alarm_verified`,
- `rtc_alarm_value`,
- `shutdown_inhibited_reason`,
- `worker_alive`,
- `last_tick_at`,
- `last_attempted_wake_at_utc`,
- `last_host_power_requested`,
- `last_host_power_accepted`.

## 6. Fail-safe po błędach

### `RTC_WAKE_ARM_FAILED`

Jeżeli RTC nie da się uzbroić lub read-back nie jest dokładnie zgodny:

- planowane wyłączenie jest anulowane,
- host-power nie jest wywoływany,
- wykonywane jest best-effort czyszczenie RTC,
- CM5 pozostaje uruchomiony,
- core publikuje `RTC_WAKE_ARM_FAILED`.

### `HOST_POWER_REQUEST_FAILED`

Jeżeli po poprawnym RTC host-power odrzuci żądanie lub transport zawiedzie:

- RTC jest czyszczony best-effort,
- CM5 pozostaje uruchomiony,
- core publikuje `HOST_POWER_REQUEST_FAILED`.

## 7. AlertV2

Domyślna polityka AlertV2 została podniesiona do:

`policy_version = "2026-08-27.1"`

Liczba wpisów polityki:

`52`

Dodano:

- `RTC_WAKE_ARM_FAILED`,
- `HOST_POWER_REQUEST_FAILED`.

Oba są diagnostyczne względem sterowania wentylacją:

- `weight = 3`,
- `severity = "alarm"`,
- `reaction = "continue_degraded"`,
- `affects_control = false`,
- `hmi_color = "orange"`.

Validator AlertV2 wymusza dla obu `affects_control=false` i nie pozwala nadać im reakcji sterującej wentylacją.

## 8. Testy automatyczne M6

Zakres testów obejmuje m.in.:

- scheduler disabled-by-default nie zapisuje RTC,
- scheduler disabled-by-default nie przekracza host-power,
- `snapshot()` nie ma efektów ubocznych,
- RTC failure nie dociera do host-power,
- host-power rejection czyści RTC,
- pojedynczy `next_wake` nie może generować powtarzających się żądań shutdown,
- RTC agent ma wąski protokół i brak ścieżki wykonania host power,
- core pozostaje nieuprzywilejowany,
- produkcyjny unit nie włącza automatycznego shutdownu,
- nowe alerty są mapowane w AlertV2,
- nowe alerty nie mogą uzyskać `affects_control=true`,
- historyczne projekcje AlertV2 zachowują zgodność z polityką 52 wpisów.

Końcowy CI dla implementacji M6 na SHA `02ecbefbdf08e0f0f1c60a4e3a300315de588a84` zakończył się `SUCCESS`.

## 9. M6A — fizyczna walidacja CM5 bez aktuacji

M6A wykonano na rzeczywistym CM5 w trybie laboratoryjnym przy użyciu:

`tools/install_validate_power_scheduler_m6a_cm5.sh`

Testowany SHA M6:

`02ecbefbdf08e0f0f1c60a4e3a300315de588a84`

M6A celowo nie podawał `--enable-scheduled-shutdown`.

Wynik:

**PASS — `M6A CHILD EXIT CODE: 0`**

Potwierdzono:

- produkcyjny `main` na oczekiwanym SHA,
- bezpieczny logiczny stan 0 V,
- poprawne uruchomienie branch runtime,
- działający worker Power Scheduler,
- `scheduled_shutdown_enabled=false`,
- RTC nieuzbrojony,
- brak żądania host-power,
- niezmieniony `wakealarm`,
- niezmieniony `boot_id`,
- niezmieniony PID `wvc-host-power`,
- domenę 12 V cały czas ON,
- politykę AlertV2 M6 załadowaną w runtime,
- poprawny restart branch core i ponowną kontrolę lifecycle,
- poprawny rollback do produkcyjnego `main`,
- brak reboot/poweroff CM5 przez cały test.

Dowody procesu:

- main before PID: `1218`,
- branch PID #1: `26586`,
- branch PID #2: `26692`,
- main after PID: `27023`,
- host-power PID: `714`,
- boot_id: `0d75d870-287f-4fba-8fe7-410092bd7bc9`.

Końcowe komunikaty testu:

`PASS: Power Scheduler M6A runtime validated on CM5 with scheduled shutdown disabled`

`PASS: RTC wakealarm unchanged; host-power never requested; CM5 never rebooted/powered off`

Szczegóły: `docs/reports/POWER_SCHEDULER_M6A_CM5_NON_ACTUATING_VALIDATION_2026-08-27_PL.md`.

## 10. Relacja do fizycznego M5B

Przed M6 fizyczny M5B potwierdził pełny cykl:

`Power Scheduler -> RTC arm/read-back -> wvc-host-power -> DFR0473 OFF -> CM5 poweroff -> RTC wake -> recovery usług`

Wynik M5B:

- zmiana `boot_id` potwierdzona,
- host-power zaakceptował `shutdown`,
- start po RTC wystąpił około 7,2 s od zaprogramowanego alarmu,
- `wakealarm` po boot był pusty,
- `ventilation-core` i host-power wróciły do pracy,
- domena 12 V wróciła ON.

Szczegóły: `docs/reports/POWER_SCHEDULER_M5B_CM5_FULL_POWER_CYCLE_VALIDATION_2026-08-27_PL.md`.

## 11. Status M6

**M6 IMPLEMENTATION: COMPLETE**

**M6 CI: PASS**

**M6A PHYSICAL CM5 VALIDATION: PASS**

M6 jest domknięte zarówno po stronie implementacji i testów automatycznych, jak i fizycznej walidacji nieaktuującego runtime na CM5.

Automatyczny scheduled shutdown nadal pozostaje domyślnie wyłączony i nie został włączony produkcyjnie.

Nie wykonano merge do `main`. Produkcyjny `main` pozostaje źródłem prawdy do czasu osobnej, jednoznacznej decyzji o merge.