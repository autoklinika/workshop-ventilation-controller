# Power Scheduler M5B — pełna walidacja CM5 RTC / host-power / power-cycle

Data: 2026-08-27

## Status

**PASS — pełny fizyczny łańcuch został zweryfikowany na CM5.**

Walidacja objęła rzeczywisty RTC CM5, `PowerScheduler`, prawdziwy lokalny klient `wvc-host-power`, odcięcie domeny 12 V przez DFR0473, fizyczny poweroff CM5, automatyczne wybudzenie przez RTC oraz powrót usług produkcyjnych po starcie.

## Zweryfikowany łańcuch

```text
Calendar/PowerScheduler test resolution
        ↓
RTC wakealarm arm
        ↓
RTC exact read-back / verification
        ↓
PowerScheduler shutdown gate
        ↓
real wvc-host-power request("shutdown")
        ↓
DFR0473 12 V domain OFF
        ↓
CM5 poweroff
        ↓
RTC wake
        ↓
CM5 boot
        ↓
wvc-host-power: 12 V domain ON
        ↓
ventilation-core from production main
```

## Wynik VERIFY po RTC wake

```json
{
  "after_boot_id": "0d75d870-287f-4fba-8fe7-410092bd7bc9",
  "before_boot_id": "4de79b1d-2bee-433e-ab31-9a03c824b619",
  "estimated_boot_epoch": 1787838044,
  "expected_wake_epoch": 1787838037,
  "host_power_response": {
    "accepted": true,
    "action": "shutdown",
    "ok": true
  },
  "ok": true,
  "phase": "verify",
  "rtc_boot_delta_seconds": 7.2,
  "validation": "power_scheduler_m5b_cm5",
  "wakealarm_empty": true
}
```

## Potwierdzenia końcowe

- boot ID przed i po cyklu różny — **PASS**
- rzeczywisty poweroff i nowy boot — **PASS**
- RTC wake nastąpił 7,2 s od zaprogramowanego czasu — **PASS**
- `wakealarm` po wybudzeniu pusty — **PASS**
- odpowiedź host-power: `ok=true`, `accepted=true`, `action=shutdown` — **PASS**
- `ventilation-core` po wybudzeniu aktywny — **PASS**
- `ventilation-core` CWD: `/home/wentylacja/workshop-ventilation-controller` — **PASS**
- `wvc-host-power` po wybudzeniu aktywny — **PASS**
- host-power status: `12 V domain ON; host-power agent ready` — **PASS**
- produkcyjny `main` po wybudzeniu: `7628c407cfc9c0ea72d262566759ea2d4598fec8` — **PASS**

## PID po wybudzeniu

- `ventilation-core`: `1218`
- `wvc-host-power`: `714`

## Wniosek

M5B potwierdza, że sprzętowa i programowa ścieżka planowanego wyłączenia może bezpiecznie opierać się na następującej zasadzie:

1. wyznacz poprawny `next_wake`,
2. uzbrój RTC,
3. odczytaj RTC i porównaj dokładnie oczekiwany alarm,
4. dopiero po poprawnej weryfikacji wolno przekroczyć granicę `wvc-host-power`,
5. host-power wykonuje istniejącą sekwencję bezpieczeństwa i odcina domenę 12 V,
6. CM5 przechodzi w poweroff,
7. RTC uruchamia CM5 o zaprogramowanym czasie,
8. po starcie `wvc-host-power` ponownie załącza domenę 12 V, a produkcyjny `ventilation-core` wraca do pracy.

Fail-safe pozostaje obowiązkowy: błąd uzbrojenia lub read-back RTC musi blokować automatyczny shutdown.

## Referencje testowe

Gałąź walidacyjna przed raportem:

`agent/automation-v1-scheduler-assumptions`

Walidowany SHA kodu M5B:

`2252d17f85b299edfb5b7db5284031f6bf86e4e6`

Produkcja podczas testu:

`main = 7628c407cfc9c0ea72d262566759ea2d4598fec8`

Nie wykonano merge do `main`.
