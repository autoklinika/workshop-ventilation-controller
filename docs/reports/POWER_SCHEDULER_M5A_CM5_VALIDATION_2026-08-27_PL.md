# Power Scheduler M5A — walidacja CM5

Data: 2026-08-27

## Cel

Zweryfikować na fizycznym CM5 granicę bezpieczeństwa pomiędzy Power Schedulerem a istniejącym host-power bez wykonywania rzeczywistej akcji zasilania hosta.

M5A używał:

- prawdziwego RTC CM5 przez `/sys/class/rtc/rtc0/wakealarm`,
- rzeczywistej logiki `PowerScheduler`,
- nieaktuującej atrapy granicy host-power, która tylko rejestrowała dokładny intent.

Test nie otwierał produkcyjnego socketu `wvc-host-power`, nie przełączał DFR0473, nie restartował `ventilation-core` i nie wyłączał CM5.

## Zweryfikowany commit

`63cfcfde894bd5417cb8439e19c342e6eaa6a59f`

Produkcja podczas testu pozostała na:

`main = 7628c407cfc9c0ea72d262566759ea2d4598fec8`

## Wynik sprzętowy

PASS.

Najważniejsze wartości z rzeczywistego przebiegu:

- `physical_rtc_epoch = 1787836728`,
- `rtc_alarm_armed = true`,
- `rtc_alarm_verified = true`,
- `shutdown_ready = true`,
- `host_power_requested = true`,
- `host_power_accepted = true`,
- zarejestrowane intencje host-power: dokładnie `["shutdown"]`,
- `real_host_power_socket_used = false`,
- `physical_power_action = false`,
- PID `ventilation-core` przed/po: `1221`,
- PID `wvc-host-power`: `718`,
- kod wyjścia harnessu: `0`.

Końcowe komunikaty:

```text
PASS: M5A verified RTC gate -> exact shutdown intent without host power action
PASS: M5A did not restart core, call real host-power, or power off CM5
```

## Potwierdzone własności bezpieczeństwa

1. Power Scheduler nie przekracza granicy host-power przed poprawnym uzbrojeniem i read-back RTC.
2. Po zweryfikowanym RTC generowany jest wyłącznie dokładny intent `shutdown`.
3. Test M5A nie posiadał ścieżki do rzeczywistego wyłączenia CM5.
4. Produkcyjny `main` i działający `ventilation-core` pozostały nietknięte.

## Następny etap

M5B: pełna walidacja łańcucha na CM5:

`Power Scheduler -> RTC verified -> real wvc-host-power -> DFR0473 OFF -> CM5 poweroff -> RTC wake -> post-boot verify`.

M5B musi pozostać testem jawnie opt-in i fail-safe: niepoprawny RTC ma blokować przekroczenie granicy host-power.