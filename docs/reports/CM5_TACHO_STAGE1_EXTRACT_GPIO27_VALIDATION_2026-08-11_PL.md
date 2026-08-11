# CM5 TACHO Stage 1 — walidacja EXTRACT na GPIO27

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Host:** `wentylacja` / Raspberry Pi Compute Module 5  
**Gałąź:** `agent/cm5-tacho-stage1`  
**Status:** kanał EXTRACT `CH1/VOUT1 + GPIO27` zwalidowany dynamicznie i testem STOP/timeout — **HARDWARE PASS**.

## 1. Konfiguracja stanowiska

W laboratorium dostępny jest obecnie jeden fizyczny wentylator EC. Dla walidacji przyjęto jednoznaczne mapowanie:

```text
sterowanie: EXTRACT / DAC CH1 / VOUT1 / DB9 pin 5
TACHO:      GPIO27 / physical pin 13 / gpiochip0 offset 27
```

Przewód TACHO tego samego wentylatora został fizycznie przepięty z GPIO17 na GPIO27. GPIO17 pozostaje zarezerwowany dla przyszłego drugiego wentylatora i nie jest częścią finalnej walidacji bieżącego kanału.

Narzędzie uruchomiono w trybie jednego kanału:

```bash
PYTHONPATH=src python3 tools/hardware/tacho_cli.py \
  --chip /dev/gpiochip0 \
  --only extract \
  --duration 15
```

## 2. Wynik dynamiczny przy 5,0 V

Sterowanie:

```text
supply=0.0 V
extract=5.0 V
```

Po około 5 s stabilizacji zarejestrowano:

```text
68.175 Hz -> 1363.5 RPM
70.051 Hz -> 1401.0 RPM
70.521 Hz -> 1410.4 RPM
70.579 Hz -> 1411.6 RPM
70.750 Hz -> 1415.0 RPM
70.899 Hz -> 1418.0 RPM
70.892 Hz -> 1417.8 RPM
70.700 Hz -> 1414.0 RPM
70.822 Hz -> 1416.4 RPM
70.835 Hz -> 1416.7 RPM
70.978 Hz -> 1419.6 RPM
70.401 Hz -> 1408.0 RPM
70.489 Hz -> 1409.8 RPM
70.328 Hz -> 1406.6 RPM
69.798 Hz -> 1396.0 RPM
```

Pierwszą próbkę `68.175 Hz / 1363.5 RPM` traktujemy jako przejściową po rozpoczęciu capture.

Średnia z kolejnych 14 próbek:

```text
frequency ~= 70.575 Hz
RPM       ~= 1411.5
```

Zakres kolejnych 14 próbek:

```text
69.798 .. 70.978 Hz
1396.0 .. 1419.6 RPM
```

Odchylenie standardowe częstotliwości dla tych 14 próbek wynosi około:

```text
0.330 Hz
```

## 3. Porównanie z wcześniejszą walidacją oscyloskopową

Punkt referencyjny z wcześniejszej charakterystyki dla sterowania 5 V:

```text
71.937 Hz
1438.7 RPM
```

Średni wynik CM5 na GPIO27:

```text
70.575 Hz
1411.5 RPM
```

Odchyłka częstotliwości względem punktu referencyjnego:

```text
-1.89 %
```

Różnica tej wielkości nie wskazuje na błąd liczenia impulsów ani problem z GPIO. Wentylator był mierzony w innym przebiegu czasowym niż pomiar oscyloskopowy i rzeczywista prędkość dla tej samej komendy 5 V może się nieznacznie różnić.

## 4. Test STOP / timeout na finalnym GPIO27

Wentylator ponownie uruchomiono przez:

```text
supply=0.0 V
extract=5.0 V
```

Po 5 s stabilizacji rozpoczęto 12-sekundowy capture wyłącznie GPIO27 z wydrukiem co 0,5 s. Po 4 s capture wykonano `ventilation_core.ctl stop`.

Przed STOP odczyt ustabilizował się kolejno do około:

```text
70.086 Hz -> 1401.7 RPM
70.081 Hz -> 1401.6 RPM
70.148 Hz -> 1403.0 RPM
70.296 Hz -> 1405.9 RPM
```

Pierwszy wydruk po zaniku impulsów:

```text
EXTRACT  NO VALID TACHO  age=0.295s
```

Następnie `NO VALID TACHO` utrzymywało się bez żadnego fałszywego powrotu do stanu valid aż do końca capture:

```text
age=0.795s
...
age=7.795s
FINAL: NO VALID TACHO
```

### Interpretacja timeoutu

Estimator używa timeoutu:

```text
0.25 s
```

Pierwszy zaobserwowany nieważny odczyt przy `age=0.295 s` jest zgodny z tym progiem oraz z rozdzielczością wydruku 0,5 s.

Test potwierdza:

- po STOP elektryczny sygnał TACHO przestaje generować zbocza,
- po przekroczeniu 0,25 s od ostatniego zbocza estimator przechodzi do invalid/0 RPM,
- po przejściu do invalid nie pojawiają się fałszywe zbocza ani chwilowe ponowne valid,
- GPIO27 pozostaje stabilnym wejściem także podczas przejścia RUN -> STOP.

Nie należy utożsamiać `age=0.295 s` z mechanicznym czasem zatrzymania wirnika. Jest to czas od ostatniego zarejestrowanego zbocza TACHO do chwili wydruku stanu nieważnego.

## 5. Wynik sprzętowy kanału EXTRACT

Para:

```text
sterowanie: EXTRACT / CH1 / VOUT1 / DB9 pin 5
feedback:   EXTRACT TACHO / GPIO27 / pin 13
```

otrzymuje status:

**HARDWARE PASS**.

Potwierdzono:

- GPIO27 poprawnie odbiera rzeczywiste zbocza TACHO,
- `libgpiod` poprawnie raportuje monotoniczne timestampy zdarzeń,
- estimator stabilnie wyznacza częstotliwość,
- przelicznik `RPM = Hz * 20` działa zgodnie z 3 impulsami na obrót,
- dynamiczny wynik 5 V jest zgodny z wcześniejszą charakterystyką oscyloskopową,
- tryb `--only extract` prawidłowo izoluje pojedynczy kanał,
- STOP powoduje prawidłowe przejście do `NO VALID TACHO`,
- brak fałszywych impulsów po zatrzymaniu.

## 6. Integracja runtime po Hardware PASS

Po zakończeniu sprzętowej walidacji rozpoczęto integrację read-only kanału EXTRACT z `ventilation-core`.

Założenia bezpieczeństwa integracji:

- tylko `EXTRACT / GPIO27` jest obecnie integrowany,
- GPIO17 pozostaje nieaktywny w runtime do czasu drugiego wentylatora,
- TACHO nie zmienia setpointów,
- TACHO nie może wymuszać `FAULT`,
- TACHO nie zeruje DAC,
- błąd monitora TACHO jest niezależny od DAC/SENSOR/AERO,
- feedback będzie widoczny w `CoreState.tacho`.

Runtime TACHO pozostaje opt-in przez `--enable-extract-tacho` do czasu przejścia testów software i kontrolowanej walidacji usługi systemd na rzeczywistym CM5.

## 7. Następny krok

1. uruchomić pełny zestaw testów repo na aktualnym HEAD gałęzi,
2. potwierdzić nowe testy TACHO runtime,
3. dopiero po PASS włączyć `--enable-extract-tacho` w produkcyjnej jednostce `ventilation-core.service`,
4. po kontrolowanym restarcie potwierdzić `CoreState.tacho.extract` przy STOP i przy 5 V,
5. potwierdzić, że awaria/odłączenie TACHO nie wpływa na DAC, SENSOR BUS ani AERO BUS.

Drugi kanał TACHO zostanie zwalidowany dopiero po dostępności drugiego fizycznego wentylatora.
