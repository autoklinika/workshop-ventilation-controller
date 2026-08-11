# CM5 TACHO Stage 1 — runbook walidacji GPIO

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Status:** przygotowane do wykonania na docelowym CM5; bez zmian w produkcyjnym `ventilation-core`.

## 1. Cel

Ten krok ma potwierdzić na działającym Raspberry Pi Compute Module 5:

- że fizyczny pin 11 jest dostępny jako `GPIO17`,
- że fizyczny pin 13 jest dostępny jako `GPIO27`,
- że obie linie są wolne i mogą zostać zażądane jako wejścia,
- że kernel/libgpiod rejestruje zbocza TACHO,
- że zmierzona częstotliwość odpowiada oczekiwanym RPM,
- że oba kanały można czytać równocześnie bez wpływu na DAC, SENSOR BUS i AERO BUS.

Ten etap **nie** zmienia sterowania wentylacją i **nie** dodaje jeszcze alarmów TACHO.

## 2. Przyjęty pinout do walidacji

| Funkcja | GPIO | Pin fizyczny 40-pin |
|---|---:|---:|
| FAN SUPPLY TACHO | GPIO17 | 11 |
| FAN EXTRACT TACHO | GPIO27 | 13 |

Tor elektryczny każdego wejścia pozostaje zgodny z walidacją sprzętową:

```text
FAN TACHO
   |
   +---- 10 kOhm ---- 3.3 V
   |
   +---- 1 kOhm ---- GPIO CM5
                      |
                     1 nF
                      |
                     GND
```

Wspólna masa wentylatora i CM5 jest wymagana.

## 3. Pakiety

Na Raspberry Pi OS / Debian 13 `trixie` używamy libgpiod 2.x.

```bash
sudo apt update
sudo apt install -y gpiod python3-libgpiod
```

Sprawdzenie wersji:

```bash
gpiodetect --version || true
gpioinfo --version
python3 - <<'PY'
import gpiod
print("python gpiod:", getattr(gpiod, "__version__", "version attribute unavailable"))
PY
```

## 4. Kontrola pinmux przed podłączeniem TACHO

W katalogu repozytorium:

```bash
cd /home/wentylacja/workshop-ventilation-controller

git fetch origin
git switch agent/cm5-tacho-stage1
git pull --ff-only origin agent/cm5-tacho-stage1
```

Następnie sprawdzić mapowanie fizycznych pinów:

```bash
pinctrl -p 11
pinctrl -p 13
```

Oczekiwane znaczenie:

```text
pin 11 -> GPIO17
pin 13 -> GPIO27
```

Nie wymagamy konkretnego numeru `/dev/gpiochipN`; na CM5 z RP1 numer gpiochip może zależeć od systemu/kernelu. Narzędzie projektowe rozwiązuje linie po nazwach `GPIO17` i `GPIO27`.

## 5. Kontrola libgpiod

```bash
gpiodetect
gpioinfo GPIO17 GPIO27
```

Przed uruchomieniem diagnostyki obie linie powinny być dostępne. Jeżeli `gpioinfo` pokazuje konsumenta, który już posiada daną linię, należy najpierw ustalić jego pochodzenie; nie wolno wymuszać przejęcia GPIO.

## 6. Pierwszy test bez uruchamiania wentylatora

Z podłączonym i zwalidowanym torem TACHO, ale przy zatrzymanym wentylatorze:

```bash
PYTHONPATH=src python3 tools/hardware/tacho_cli.py --duration 5
```

Oczekiwany wynik dla zatrzymanego kanału:

```text
NO VALID TACHO
```

Samo uruchomienie narzędzia nie steruje DAC i nie zmienia napięcia 0–10 V.

## 7. Test jednego wentylatora

Najpierw uruchomić tylko jeden wentylator istniejącym, zwalidowanym mechanizmem sterowania. Następnie w drugim terminalu:

```bash
PYTHONPATH=src python3 tools/hardware/tacho_cli.py --duration 15
```

Narzędzie:

- automatycznie wyszukuje gpiochip zawierający obie linie,
- żąda GPIO17 i GPIO27 jako wejścia,
- wyłącza wewnętrzny bias GPIO, ponieważ tor ma zewnętrzny pull-up 10 kOhm,
- rejestruje wyłącznie zbocza narastające,
- używa monotonicznych timestampów zdarzeń z kernela,
- przelicza częstotliwość według `RPM = Hz * 20`.

Dla punktów ze sprzętowej walidacji oczekujemy orientacyjnie:

| Sterowanie | TACHO | RPM |
|---:|---:|---:|
| 1.0 V | 19.933 Hz | 399 |
| 2.0 V | 33.370 Hz | 667 |
| 5.0 V | 71.937 Hz | 1439 |
| 8.0 V | 101.090 Hz | 2022 |
| 10.0 V | 113.280 Hz | 2266 |

Nie traktować tych wartości jako sztywnej tolerancji produkcyjnej. W tym etapie potwierdzamy poprawność pomiaru, monotoniczność i rozsądny rząd wielkości.

## 8. Test obu wentylatorów równocześnie

Po pozytywnym teście pojedynczego kanału uruchomić oba wentylatory i ponownie wykonać:

```bash
PYTHONPATH=src python3 tools/hardware/tacho_cli.py --duration 30
```

Warunki zaliczenia:

1. oba kanały generują stabilne odczyty,
2. `SUPPLY` reaguje tylko na wentylator nawiewny,
3. `EXTRACT` reaguje tylko na wentylator wyciągowy,
4. zatrzymanie jednego wentylatora powoduje timeout tylko jego kanału,
5. drugi kanał pozostaje prawidłowy,
6. nie pojawiają się błędy DAC, SENSOR BUS ani AERO BUS.

## 9. Dodatkowa obserwacja surowych zboczy

Jeżeli potrzebna jest niezależna kontrola bez kodu projektu, libgpiod udostępnia `gpiomon`.

Najpierw z `gpioinfo` ustalić gpiochip zawierający linię, a następnie przykładowo:

```bash
gpiomon --edges=rising --num-events=20 GPIO17
```

To polecenie jest wyłącznie diagnostyczne i nie zastępuje pomiaru Hz/RPM przez `tacho_cli.py`.

## 10. Czego nie robimy w tym kroku

Do czasu zakończenia powyższej walidacji nie należy:

- dodawać TACHO do `CoreState`,
- generować alarmu `command > 0 && rpm == 0`,
- ustalać tolerancji `expected_rpm`,
- publikować RPM do telemetrii/AI,
- uzależniać sterowania wentylatorami od TACHO,
- uruchamiać osobnego stałego workera GPIO.

## 11. Handoff po pozytywnej walidacji

Po uzyskaniu rzeczywistych logów z obu GPIO następny etap software powinien:

1. przenieść obsługę libgpiod z narzędzia diagnostycznego do infrastruktury `ventilation_core`,
2. zachować pomiar na kernelowych timestampach zboczy,
3. wystawić dwa niezależne `TachoReading`,
4. dołączyć RPM do stanu/API bez wpływu na decyzje sterujące,
5. dopiero w kolejnym kroku zaprojektować diagnostykę rozbieżności `command` / `actual RPM`.
