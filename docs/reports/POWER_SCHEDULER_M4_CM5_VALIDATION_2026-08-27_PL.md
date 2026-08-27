# Power Scheduler M4 — walidacja na fizycznym CM5

Data: 2026-08-27

## Zakres

Walidacja M4 sprawdzała na rzeczywistym CM5 wyłącznie warstwę RTC i nieaktuującą część Power Schedulera. Test nie mógł wykonać `halt`, `poweroff`, `reboot`, nie wywoływał `wvc-host-power`, nie przełączał DFR0473 i nie restartował `ventilation-core`.

Walidowany commit funkcjonalny:

`a7dcb30623c14647dd912303bd5d9f9089816fe0`

Produkcja podczas testu pozostawała na:

`main = 7628c407cfc9c0ea72d262566759ea2d4598fec8`

## Wynik sprzętowy

**PASS — funkcjonalna część M4 została potwierdzona na fizycznym CM5.**

Zaobserwowane wyniki validatora:

- bezpośrednie uzbrojenie `/sys/class/rtc/rtc0/wakealarm`: PASS,
- wymagany epoch: `1787834918`,
- read-back RTC: `1787834918`,
- `verified = true`,
- wyczyszczenie alarmu po teście bezpośrednim: PASS,
- Power Scheduler wyznaczył `next_wake_at_local = 2026-08-27T14:50:38+02:00`,
- `rtc_alarm_armed = true`,
- `rtc_alarm_verified = true`,
- `rtc_alarm_value = 1787835038`,
- `scheduled_shutdown_enabled = true`,
- `shutdown_inhibited_reason = null`,
- `shutdown_ready = true`,
- `alert_code = null`,
- `host_power_requested = false`,
- `physical_power_action = false`.

Validator zakończył część funkcjonalną komunikatem:

`PASS: Power Scheduler M4 CM5 RTC arm/read-back/clear validated without host shutdown`

Przed próbą usunięcia worktree harness sprawdził również:

- końcowy `wakealarm` jest pusty,
- PID `ventilation-core` nie zmienił się,
- CWD `ventilation-core` nadal wskazuje produkcyjny checkout `main`.

## Defekt cleanupu

Po pełnym PASS części funkcjonalnej harness zakończył się kodem `255` podczas sprzątania:

`error: failed to delete '/home/wentylacja/wvc-power-scheduler-m4-validation': Permission denied`

Przyczyna nie dotyczyła RTC ani Power Schedulera. Validator był uruchamiany przez `sudo`, więc interpreter Python mógł utworzyć root-owned `__pycache__` wewnątrz odłączonego worktree. Następnie zwykły `git worktree remove --force` wykonywany jako użytkownik `wentylacja` nie mógł usunąć tych plików.

## Poprawka cleanupu

Harness został poprawiony na tej samej gałęzi roboczej:

- uruchamia validator z `PYTHONDONTWRITEBYTECODE=1`,
- uruchamia Python z `-B`,
- przed usuwaniem worktree usuwa wyłącznie ewentualne katalogi `__pycache__` wymagające uprawnień root,
- nie poszerza zakresu uprawnień validatora,
- nie dodaje żadnej ścieżki do host-power ani restartu core.

Pierwszy commit poprawki cleanupu:

`07b8c5951f337423762a91bdf55b15a535530545`

Test regresyjny cleanupu dodano w kolejnym commicie:

`1979bada7379b3d97ecd837043a2629eb6dc7aae`

## Wniosek M4

M4 potwierdza, że kod Power Schedulera potrafi na fizycznym CM5:

1. otrzymać przyszły `next_wake`,
2. przeliczyć go na jednoznaczny epoch UTC,
3. uzbroić rzeczywisty RTC,
4. odczytać alarm z RTC,
5. porównać wartość z oczekiwaną,
6. dopuścić planowany shutdown wyłącznie po poprawnej weryfikacji (`shutdown_ready = true`),
7. wyczyścić alarm po walidacji,
8. wykonać cały test bez fizycznego wyłączenia hosta i bez restartu `ventilation-core`.

Osobny wcześniejszy test sprzętowy potwierdził również, że CM5 po `halt` rzeczywiście uruchamia się sam z alarmu RTC.

M4 nie daje jeszcze Power Schedulerowi prawa do wywołania host-power. Integracja `Calendar Engine -> Power Scheduler -> zweryfikowany RTC -> wvc-host-power` należy do kolejnego etapu M5 i wymaga osobnej walidacji fail-safe.

`main` nie został zmieniony ani scalony w ramach M4.
