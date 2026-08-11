# CM5 TACHO Stage 1 — walidacja bazowa GPIO

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Host:** `wentylacja` / Raspberry Pi Compute Module 5  
**Status:** bazowa walidacja GPIO oraz test zatrzymanych wentylatorów zaliczone; pierwszy pomiar obracającego się wentylatora pozostaje do wykonania.

## 1. Zweryfikowana gałąź

Pierwsza walidacja bazowa została wykonana na:

```text
branch: agent/cm5-tacho-stage1
HEAD:   a985fc4af109e301aa34e203c338785a3246e1fb
```

Po poprawce autodetekcji gpiochip test zatrzymanych wentylatorów wykonano na:

```text
branch: agent/cm5-tacho-stage1
HEAD:   04a8c28bca04b2e6b9e9b5c4e202cf6069b8fd1d
```

## 2. Pakiety GPIO

Na docelowym CM5 potwierdzono:

```text
gpiod             2.2.1-2+deb13u1
python3-libgpiod  2.2.1-2+deb13u1
```

Nie była wymagana instalacja nowych pakietów.

## 3. Pinmux

Wynik `pinctrl`:

```text
11: no    pd | -- // GPIO17 = none
13: no    pd | -- // GPIO27 = none
```

Wniosek:

- fizyczny pin 11 jest poprawnie mapowany jako GPIO17,
- fizyczny pin 13 jest poprawnie mapowany jako GPIO27,
- żaden z pinów nie ma aktywnej funkcji alternatywnej,
- obie linie są dostępne jako wejścia GPIO,
- `tacho_cli.py` żąda linii z `bias=DISABLED`, ponieważ tor sprzętowy ma zewnętrzny pull-up 10 kOhm do 3,3 V.

## 4. Kontrolery GPIO

`gpiodetect` na docelowym CM5 zwrócił:

```text
gpiochip0  [pinctrl-rp1]                 (54 lines)
gpiochip10 [gpio-brcmstb@107d508500]     (32 lines)
gpiochip11 [gpio-brcmstb@107d517c00]     (15 lines)
gpiochip12 [gpio-brcmstb@107d517c20]     (6 lines)
gpiochip13 [gpio-brcmstb@107d508520]     (4 lines)
```

Nagłówek GPIO używany w tym etapie znajduje się na `gpiochip0` (`pinctrl-rp1`).

## 5. Linie TACHO

`gpioinfo GPIO17 GPIO27` potwierdziło:

```text
gpiochip0 17 "GPIO17" input
gpiochip0 27 "GPIO27" input
```

Wniosek:

- `FAN SUPPLY TACHO` -> GPIO17 -> gpiochip0 offset 17,
- `FAN EXTRACT TACHO` -> GPIO27 -> gpiochip0 offset 27,
- obie linie były wolne i ustawione jako wejścia.

To potwierdza przydział zapisany w `docs/PINOUT.md`.

## 6. Testy software

Pierwsza walidacja:

```text
Ran 150 tests in 0.107s
OK
```

Po poprawce autodetekcji i dodaniu testu regresyjnego:

```text
Ran 151 tests in 0.107s
OK
```

Pełny zestaw testów pozostaje zielony.

## 7. Pierwsze uruchomienie narzędzia TACHO

Pierwszy read-only test bez jawnego gpiochip zakończył się bez przejęcia GPIO komunikatem:

```text
ERROR: GPIO line names are ambiguous across chips (/dev/gpiochip0, /dev/gpiochip4); rerun with --chip PATH
```

Jednocześnie `gpiodetect` i `gpioinfo` jednoznacznie potwierdziły, że rzeczywiste linie nagłówka są na `/dev/gpiochip0`.

Problem sklasyfikowano jako błąd autodetekcji aliasów urządzenia w narzędziu diagnostycznym, a nie problem sprzętowy ani konflikt GPIO.

## 8. Korekta software

Poprawiono `tools/hardware/tacho_cli.py`, aby przy autodetekcji deduplikował ścieżki wskazujące na ten sam znakowy węzeł urządzenia (`st_rdev`). Dodano test regresyjny.

Commity korekty:

```text
3bd017668e50eec66ca32cd4d9325d9dc18d6b43  Fix TACHO gpiochip alias auto-detection
3bede6faf557983a2da98ead90039d31db844370  Test gpiochip alias deduplication
```

## 9. Walidacja przy zatrzymanych wentylatorach

Na HEAD:

```text
04a8c28bca04b2e6b9e9b5c4e202cf6069b8fd1d
```

uruchomiono:

```bash
PYTHONPATH=src python3 tools/hardware/tacho_cli.py --chip /dev/gpiochip0 --duration 10
```

Narzędzie poprawnie zażądało obu linii:

```text
chip:    /dev/gpiochip0
SUPPLY:  GPIO17 -> offset 17
EXTRACT: GPIO27 -> offset 27
edge:    rising
bias:    disabled (external 10 kOhm pull-up is required)
formula: RPM = TACHO_HZ * 20 (3 pulses/revolution)
```

Przez cały 10-sekundowy test oraz w sekcji `FINAL` otrzymano:

```text
SUPPLY   NO VALID TACHO  age=n/a
EXTRACT  NO VALID TACHO  age=n/a
```

### Wniosek

Test zaliczony:

- oba GPIO mogą być jednocześnie zażądane przez libgpiod,
- brak fałszywych zboczy przy zatrzymanych wentylatorach,
- oba kanały pozostają niezależne,
- stan bez impulsów jest poprawnie raportowany jako `NO VALID TACHO`,
- nie wystąpił błąd dostępu do GPIO ani konflikt właściciela linii.

## 10. Mapowanie DAC potwierdzone w software

Aktualny `DFR0971Actuator` mapuje:

```text
supply_voltage  -> DAC channel 0 / VOUT0
extract_voltage -> DAC channel 1 / VOUT1
```

Dzięki temu pierwszy test dynamiczny może bezpiecznie uruchomić wyłącznie wentylator nawiewny przez `supply=5.0`, pozostawiając `extract=0.0`.

## 11. Następny krok

Pierwszy pomiar dynamiczny:

1. potwierdzić stan `ventilation-core`,
2. ustawić `supply=5.0 V`, `extract=0.0 V`,
3. odczekać kilka sekund na stabilizację,
4. zmierzyć `GPIO17` przez `tacho_cli.py`,
5. zawsze zakończyć test komendą `stop`, także po błędzie lub przerwaniu.

Punkt referencyjny z oscyloskopu dla 5 V:

```text
TACHO ≈ 71.937 Hz
RPM   ≈ 1439
```

Wartość nie jest jeszcze progiem produkcyjnym; służy do pierwszego porównania poprawności pomiaru CM5.
