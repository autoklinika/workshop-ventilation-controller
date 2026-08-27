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

## 9. M6A — przygotowana walidacja CM5 bez aktuacji

Dodano:

`tools/install_validate_power_scheduler_m6a_cm5.sh`

M6A jest testem wdrożeniowym, który uruchamia branch runtime na rzeczywistym CM5, ale **celowo nie podaje** `--enable-scheduled-shutdown`.

M6A wymaga i sprawdza:

- dokładny CI-tested SHA gałęzi,
- produkcyjny `main` na oczekiwanym SHA,
- bezpieczny logiczny stan 0 V,
- tryb laboratoryjny STOP/FAULT dla odłączonego DAC/SEN55/AERO,
- działający worker Power Scheduler,
- `scheduled_shutdown_enabled=false`,
- RTC nieuzbrojony,
- brak żądania host-power,
- ten sam `boot_id`,
- ten sam PID `wvc-host-power`,
- niezmieniony `wakealarm`,
- domenę 12 V nadal ON,
- politykę AlertV2 `2026-08-27.1` / 52 wpisy,
- restart branch core i ponowną kontrolę lifecycle,
- automatyczny rollback do produkcyjnego `main`.

M6A nie zawiera bezpośredniej komendy poweroff/reboot i nie włącza automatycznego scheduled shutdown.

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

**Implementacja M6: COMPLETE po zielonym CI końcowego HEAD.**

**M6A: przygotowany do fizycznego testu CM5; nie jest warunkiem poprawności kodu M6, ale jest wymaganym testem przed późniejszym świadomym włączeniem automatycznego scheduled shutdown w konfiguracji produkcyjnej.**

Nie wykonano merge do `main`. Produkcyjny `main` pozostaje źródłem prawdy do czasu osobnej, jednoznacznej decyzji o merge.
