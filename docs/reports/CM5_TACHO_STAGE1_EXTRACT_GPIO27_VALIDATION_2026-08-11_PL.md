# CM5 TACHO Stage 1 — walidacja EXTRACT na GPIO27

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Host:** `wentylacja` / Raspberry Pi Compute Module 5  
**Gałąź:** `agent/cm5-tacho-stage1`  
**Status:** dynamiczny pomiar kanału EXTRACT na GPIO27 — PASS; test STOP/timeout na finalnym GPIO27 pozostaje do wykonania.

## 1. Konfiguracja stanowiska

W laboratorium dostępny jest obecnie jeden fizyczny wentylator EC. Dla walidacji przyjęto jednoznaczne mapowanie:

```text
sterowanie: EXTRACT / DAC CH1 / VOUT1 / DB9 pin 5
TACHO:      GPIO27 / physical pin 13 / gpiochip0 offset 27
```

Przewód TACHO tego samego wentylatora został fizycznie przepięty z GPIO17 na GPIO27. GPIO17 pozostaje zarezerwowany dla przyszłego drugiego wentylatora i nie jest częścią tego testu.

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

## 4. Wnioski

Dynamiczny test kanału EXTRACT na docelowym wejściu GPIO27 jest zaliczony:

- `GPIO27` poprawnie odbiera zbocza TACHO,
- `libgpiod` poprawnie raportuje timestampy zdarzeń,
- estimator stabilnie wyznacza częstotliwość,
- przelicznik `RPM = Hz * 20` działa zgodnie z 3 impulsami na obrót,
- wynik jest zgodny co do rzędu i charakterystyki z wcześniejszym pomiarem oscyloskopowym,
- tryb `--only extract` prawidłowo izoluje pojedynczy kanał laboratoryjny,
- para `EXTRACT / CH1 / VOUT1 + GPIO27` jest potwierdzona dynamicznie na rzeczywistym CM5.

## 5. Następny krok

Przed uznaniem kanału EXTRACT za całkowicie zamknięty sprzętowo należy powtórzyć na GPIO27 test zaniku TACHO po `STOP`:

1. uruchomić EXTRACT na 5 V,
2. rozpocząć capture GPIO27,
3. wykonać `ventilationctl stop` podczas capture,
4. potwierdzić przejście z prawidłowego Hz/RPM do `NO VALID TACHO`,
5. potwierdzić brak błędu dostępu do GPIO i poprawne działanie timeoutu estimatora.

Po tym teście można przejść do integracji zwalidowanego kanału EXTRACT z `CoreState` jako read-only feedback. Kanał drugiego wentylatora pozostanie nieaktywny/niezwalidowany do czasu dostępności drugiego fizycznego wentylatora.
