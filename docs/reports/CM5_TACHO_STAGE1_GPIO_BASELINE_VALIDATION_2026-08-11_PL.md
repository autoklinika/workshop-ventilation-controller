# CM5 TACHO Stage 1 — walidacja bazowa GPIO

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Host:** `wentylacja` / Raspberry Pi Compute Module 5  
**Status:** bazowa walidacja GPIO zaliczona; pomiar zboczy TACHO pozostaje do wykonania.

## 1. Zweryfikowana gałąź

Na docelowym CM5 uruchomiono:

```text
branch: agent/cm5-tacho-stage1
HEAD:   a985fc4af109e301aa34e203c338785a3246e1fb
```

Repozytorium było aktualne względem `origin/agent/cm5-tacho-stage1` w momencie testu.

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
- wewnętrzny pull-down widoczny w stanie bazowym nie jest traktowany jako finalna konfiguracja pomiarowa; `tacho_cli.py` żąda linii z `bias=DISABLED`, ponieważ tor sprzętowy ma zewnętrzny pull-up 10 kOhm do 3,3 V.

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

Na zweryfikowanym HEAD uruchomiono pełny zestaw testów:

```text
Ran 150 tests in 0.107s
OK
```

Stan logiki domenowej TACHO i pozostałego `ventilation-core` był poprawny przed pierwszym odczytem GPIO.

## 7. Pierwsze uruchomienie narzędzia TACHO

Pierwszy read-only test:

```bash
PYTHONPATH=src python3 tools/hardware/tacho_cli.py --duration 10
```

zakończył się bez przejęcia GPIO komunikatem:

```text
ERROR: GPIO line names are ambiguous across chips (/dev/gpiochip0, /dev/gpiochip4); rerun with --chip PATH
```

Jednocześnie `gpiodetect` i `gpioinfo` jednoznacznie potwierdziły, że rzeczywiste linie nagłówka są na `/dev/gpiochip0`.

Problem został sklasyfikowany jako błąd autodetekcji ścieżek urządzeń/aliasów w narzędziu diagnostycznym, a nie problem sprzętowy ani konflikt GPIO.

## 8. Korekta software po walidacji

Po tym pomiarze poprawiono `tools/hardware/tacho_cli.py` tak, aby przy autodetekcji deduplikował ścieżki wskazujące na ten sam znakowy węzeł urządzenia (`st_rdev`).

Dodano również test regresyjny dla przypadku aliasów `/dev/gpiochip0` i `/dev/gpiochip4` wskazujących na to samo urządzenie.

Commity korekty:

```text
3bd017668e50eec66ca32cd4d9325d9dc18d6b43  Fix TACHO gpiochip alias auto-detection
3bede6faf557983a2da98ead90039d31db844370  Test gpiochip alias deduplication
```

## 9. Następny krok

Na docelowym CM5 należy pobrać aktualny HEAD gałęzi i ponowić najpierw test bez obracających się wentylatorów:

```bash
git pull --ff-only origin agent/cm5-tacho-stage1
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 tools/hardware/tacho_cli.py --chip /dev/gpiochip0 --duration 10
```

Jawne `--chip /dev/gpiochip0` jest w tym checkpointcie celowe: sprzętowe mapowanie zostało już jednoznacznie potwierdzone i dzięki temu kolejny test weryfikuje sam mechanizm żądania linii, odbioru zdarzeń i timeoutu.

Oczekiwany rezultat przy zatrzymanych wentylatorach:

```text
SUPPLY   NO VALID TACHO
EXTRACT  NO VALID TACHO
```

Po zaliczeniu tego kroku można przejść do pierwszego rzeczywistego pomiaru jednego wentylatora.
