# Walidacja RTC wake na CM5 — 2026-08-27

## Cel

Szybka, niezależna walidacja sprzętowej ścieżki RTC przed implementacją Power Schedulera.

## Środowisko

- Raspberry Pi Compute Module 5
- strefa systemowa: `Europe/Warsaw`
- test w warunkach laboratoryjnych
- główne 5 V CM5 pozostawało podane podczas `halt`

## Test A — RTC i wakealarm bez zatrzymywania hosta

Wynik:

- `/dev/rtc0` obecny — PASS
- sterownik: `rpi-rtc soc@107c000000:rpi_rtc` — PASS
- czas RTC zgodny z czasem UTC systemu — PASS
- zapis `/sys/class/rtc/rtc0/wakealarm` — PASS
- read-back alarmu — PASS
- skasowanie alarmu — PASS

Przykładowy test alarmu `+120 s`:

- zapisany epoch: `1787832122`
- interpretacja lokalna: `2026-08-27T14:02:02+02:00`

## Test B — rzeczywiste wybudzenie CM5

Po ustawieniu alarmu RTC i wykonaniu kontrolowanego `halt` CM5 uruchomił się samoczynnie.

Po powrocie:

```text
2026-08-27T14:07:45+02:00
up 0 minutes
boot start: 2026-08-27 14:06:47
boot_id: 4de79b1d-2bee-433e-ab31-9a03c824b619
wakealarm: <empty>
```

Wynik: **RTC HARDWARE WAKE = PASS**.

## Wniosek architektoniczny

CM5 potrafi zostać zatrzymany i ponownie uruchomiony przez alarm RTC, jeśli główne zasilanie 5 V pozostaje dostępne. Można przejść do implementacji Power Schedulera.

Power Scheduler musi zachować fail-safe:

1. pobrać `next_wake` z Calendar Engine,
2. zwalidować przyszły timestamp,
3. zapisać alarm RTC,
4. odczytać alarm z RTC,
5. porównać odczyt z oczekiwanym timestampem,
6. dopiero po zgodnym read-back dopuścić scheduled shutdown.

Błąd uzbrojenia/weryfikacji RTC ma blokować automatyczny shutdown i docelowo generować `RTC_WAKE_ARM_FAILED` w AlertV2.
