# CM5 TACHO Stage 2 — walidacja zaniku i recovery SUPPLY

Data: 2026-08-13

## Cel

Potwierdzić na docelowym CM5 zachowanie read-only TACHO nawiewu podczas fizycznego odłączenia i ponownego podłączenia przewodu SUPPLY TACHO przy pracujących obu wentylatorach.

Mapowanie:

```text
SUPPLY control -> DAC CH0 / VOUT0
SUPPLY TACHO   -> GPIO17 / physical pin 11
EXTRACT control -> DAC CH1 / VOUT1
EXTRACT TACHO   -> GPIO27 / physical pin 13
```

## Warunki testu

Uruchomiono testowy core Stage 2 na osobnym socketcie z AERO BUS wyłączonym programowo, ponieważ rekuperator był w tym czasie fizycznie odłączony.

Oba wentylatory ustawiono na:

```text
supply=5.0 V
extract=5.0 V
```

Produkcjny `ventilation-core.service` został wcześniej zatrzymany po wymuszeniu STOP.

## Baseline — oba TACHO podłączone

Trzy kolejne próbki:

```text
SUPPLY valid=True  1222.4 RPM | EXTRACT valid=True 1227.3 RPM | alarms=0
SUPPLY valid=True  1404.4 RPM | EXTRACT valid=True 1411.6 RPM | alarms=0
SUPPLY valid=True  1437.9 RPM | EXTRACT valid=True 1451.7 RPM | alarms=0
```

Pierwsza próbka obejmowała jeszcze rozbieg wentylatorów. Następne próbki były stabilne.

## Fizyczne odłączenie wyłącznie SUPPLY TACHO

Po odłączeniu przewodu TACHO nawiewu, bez zmiany przewodu sterującego 0–10 V i bez zatrzymania wentylatora, otrzymano pięć kolejnych próbek:

```text
mode=MANUAL | supply=5.0 | extract=5.0 | SUPPLY valid=False rpm=0.0 | EXTRACT valid=True rpm=1464.8 | alarms=0
mode=MANUAL | supply=5.0 | extract=5.0 | SUPPLY valid=False rpm=0.0 | EXTRACT valid=True rpm=1468.5 | alarms=0
mode=MANUAL | supply=5.0 | extract=5.0 | SUPPLY valid=False rpm=0.0 | EXTRACT valid=True rpm=1471.3 | alarms=0
mode=MANUAL | supply=5.0 | extract=5.0 | SUPPLY valid=False rpm=0.0 | EXTRACT valid=True rpm=1466.4 | alarms=0
mode=MANUAL | supply=5.0 | extract=5.0 | SUPPLY valid=False rpm=0.0 | EXTRACT valid=True rpm=1465.5 | alarms=0
```

Potwierdzono kontrakt bezpieczeństwa:

- `SUPPLY valid=False` po zaniku impulsów,
- setpoint SUPPLY pozostaje 5.0 V,
- tryb core pozostaje `MANUAL`,
- EXTRACT TACHO działa nadal niezależnie,
- brak aktywnych alarmów,
- utrata feedbacku TACHO nie steruje DAC i nie zatrzymuje wentylatora.

## Ponowne podłączenie SUPPLY TACHO

Po ponownym podłączeniu przewodu, bez restartu core, feedback odzyskał `valid=True` automatycznie:

```text
SUPPLY valid=True 1431.4 RPM | EXTRACT valid=True 1450.6 RPM | alarms=0
SUPPLY valid=True 1432.3 RPM | EXTRACT valid=True 1457.7 RPM | alarms=0
SUPPLY valid=True 1440.5 RPM | EXTRACT valid=True 1457.2 RPM | alarms=0
SUPPLY valid=True 1443.1 RPM | EXTRACT valid=True 1744.9 RPM | alarms=0
SUPPLY valid=True 1437.3 RPM | EXTRACT valid=True 1453.8 RPM | alarms=0
```

SUPPLY odzyskał stabilny odczyt około 1430–1443 RPM bez restartu procesu.

### Obserwacja: pojedynczy outlier EXTRACT

W jednej próbce podczas fazy po ponownym podłączeniu SUPPLY TACHO odnotowano pojedynczy skok EXTRACT do `1744.9 RPM`. Sąsiednie próbki EXTRACT wynosiły około 1450–1458 RPM, więc jest to izolowany outlier.

Nie wpłynął on na:

- tryb core,
- setpointy DAC,
- alarmy,
- `valid` obu kanałów.

Stage 2 TACHO pozostaje read-only, dlatego pojedynczy outlier nie ma wpływu na sterowanie. Przed ewentualnym przyszłym wykorzystaniem RPM w automatyce zamkniętej pętli należy dodać lub zwalidować filtrację/plausibility check dla impulsowych odchyleń.

## Końcowy STOP i recovery produkcji

Po teście testowy core wykonano STOP:

```text
mode=STOP
supply=0.0 V
extract=0.0 V
SUPPLY valid=False / 0 RPM
EXTRACT valid=False / 0 RPM
alarms=0
```

Następnie testowy proces został zamknięty, produkcyjny `ventilation-core.service` przywrócony i potwierdzono:

```text
service=active
mode=STOP
supply=0.0 V
extract=0.0 V
hardware_ready=True
active_alarms=[]
```

## Wynik

**PASS** dla kontrolowanego fizycznego disconnect/reconnect SUPPLY TACHO.

Potwierdzone:

1. zanik SUPPLY TACHO jest wykrywany jako `valid=False`,
2. utrata TACHO nie zmienia setpointu SUPPLY ani trybu core,
3. EXTRACT pozostaje niezależny,
4. brak alarmów i brak wpływu na DAC,
5. ponowne podłączenie odzyskuje `valid=True` automatycznie bez restartu core,
6. końcowy stan po walidacji jest bezpieczny: STOP / 0.0 V / 0.0 V.
