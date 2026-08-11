# CM5 TACHO Stage 1 — walidacja dynamiczna pierwszego wentylatora

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Host:** `wentylacja` / Raspberry Pi Compute Module 5  
**Gałąź:** `agent/cm5-tacho-stage1`  
**Status:** pierwszy fizyczny kanał TACHO zwalidowany dynamicznie; mapowanie funkcjonalne obu wentylatorów pozostaje do jednoznacznego ustalenia.

## 1. Kontekst

Po zaliczeniu bazowej walidacji GPIO potwierdzono:

- GPIO17 / pin fizyczny 11 / gpiochip0 offset 17,
- GPIO27 / pin fizyczny 13 / gpiochip0 offset 27,
- oba wejścia wolne i dostępne przez libgpiod 2.2.1,
- brak fałszywych zboczy przy zatrzymanych wentylatorach,
- `RPM = TACHO_HZ * 20` dla 3 impulsów na obrót.

W software DAC obowiązuje mapowanie:

```text
supply_voltage  -> CH0 / VOUT0
extract_voltage -> CH1 / VOUT1
```

Ręczna walidacja stanowiska wykazała, że aktualnie fizycznie podłączony wentylator uruchamia się przy:

```text
supply=0.0 V
extract=5.0 V
```

czyli przez CH1 / VOUT1.

## 2. Pierwszy dynamiczny pomiar 5 V

Po ustawieniu CH1 na 5,0 V i 5 s stabilizacji uruchomiono równoczesny odczyt GPIO17 i GPIO27 przez `tools/hardware/tacho_cli.py`.

Aktywność pojawiła się wyłącznie na GPIO17.

Próbki po ustabilizowaniu wynosiły około:

```text
71.122 Hz -> 1422.4 RPM
71.453 Hz -> 1429.1 RPM
71.393 Hz -> 1427.9 RPM
71.296 Hz -> 1425.9 RPM
71.056 Hz -> 1421.1 RPM
71.264 Hz -> 1425.3 RPM
71.172 Hz -> 1423.4 RPM
71.351 Hz -> 1427.0 RPM
71.196 Hz -> 1423.9 RPM
71.006 Hz -> 1420.1 RPM
71.224 Hz -> 1424.5 RPM
71.374 Hz -> 1427.5 RPM
71.079 Hz -> 1421.6 RPM
71.244 Hz -> 1424.9 RPM
```

Pierwsza próbka `69.041 Hz / 1380.8 RPM` została potraktowana jako próbka przejściowa po rozpoczęciu capture.

Średnia z kolejnych 14 stabilnych próbek:

```text
frequency ~= 71.231 Hz
RPM       ~= 1424.6
```

Zakres stabilnych próbek:

```text
71.006 .. 71.453 Hz
1420.1 .. 1429.1 RPM
```

Punkt referencyjny ze wcześniejszej walidacji oscyloskopowej dla 5 V:

```text
71.937 Hz
1438.7 RPM
```

Odchyłka średniego pomiaru CM5 względem punktu oscyloskopowego wynosi około:

```text
-0.98 %
```

### Wniosek

Pomiar okresu zboczy przez libgpiod na CM5 działa poprawnie i stabilnie. Wynik jest zgodny z wcześniejszą charakterystyką laboratoryjną z odchyłką poniżej 1%.

## 3. Ujawnione mapowanie stanowiska

Sterowanie aktywnego wentylatora:

```text
CH1 / VOUT1 / software EXTRACT
```

TACHO tego samego fizycznego wentylatora:

```text
GPIO17 / obecna robocza etykieta SUPPLY
```

GPIO27 przez cały test pozostawało:

```text
NO VALID TACHO
```

Nie należy jeszcze automatycznie zmieniać semantyki `supply/extract` w kodzie. Wynik może oznaczać zamianę przewodów TACHO, zamianę przewodów sterujących 0–10 V albo po prostu inne niż założone przypisanie fizycznych wentylatorów na stanowisku. Finalne mapowanie należy ustalić po identyfikacji obu fizycznych wentylatorów.

## 4. Test STOP / zaniku TACHO

Wentylator uruchomiono ponownie na CH1 = 5,0 V. Po 5 s stabilizacji rozpoczęto 12-sekundowy capture TACHO z drukiem co 0,5 s. Po 4 s capture wykonano `ventilationctl stop`.

Bezpośrednio przed STOP GPIO17 raportowało stabilnie około:

```text
69.905 .. 70.090 Hz
1398.1 .. 1401.8 RPM
```

Po komendzie STOP kolejny wydruk pokazał:

```text
SUPPLY   NO VALID TACHO  age=0.426s
```

Następnie stan `NO VALID TACHO` utrzymywał się do końca capture, a `age` wzrastało monotonicznie do około 7,926 s.

GPIO27 pozostawało `NO VALID TACHO` przez cały test.

### Ważna interpretacja

Ten log potwierdza, że po komendzie STOP elektryczny sygnał TACHO na GPIO17 przestaje generować zbocza w czasie krótszym niż rozdzielczość wydruku 0,5 s.

Nie można na tej podstawie stwierdzić, że mechaniczny wirnik zatrzymał się w około 0,4 s. Możliwe jest szybkie wyhamowanie, ale możliwe jest również, że elektronika wentylatora przestaje publikować TACHO podczas wybiegu lub poniżej pewnego progu. Do Stage 1 wystarcza potwierdzenie poprawnego zaniku zboczy i timeoutu.

## 5. Ocena aktualnego timeoutu

Estimator używa obecnie timeoutu 0,25 s.

Dla najniższego wcześniej zmierzonego punktu roboczego 1,0 V:

```text
f ~= 19.933 Hz
period ~= 50.2 ms
```

Timeout 0,25 s odpowiada więc około pięciu brakującym impulsom w najniższym zwalidowanym punkcie pracy. Jest wystarczająco konserwatywny dla diagnostyki Stage 1 i nie powoduje fałszywego timeoutu w zwalidowanym zakresie 1..10 V.

Nie należy jeszcze traktować 0,25 s jako finalnego progu alarmowego `fan stopped`. Produkcyjny alarm powinien mieć osobny, dłuższy czas potwierdzenia od wewnętrznego timeoutu ważności pojedynczego odczytu TACHO.

## 6. Wynik etapu

Pierwszy fizyczny kanał TACHO na CM5: **PASS**.

Potwierdzono:

- odbiór rzeczywistych zboczy na GPIO17,
- poprawne kernelowe timestampy libgpiod,
- stabilne wyznaczanie częstotliwości,
- poprawny przelicznik 3 imp/obrót,
- zgodność RPM z oscyloskopem w granicy około 1%,
- brak aktywności na drugim wejściu podczas testu jednego wentylatora,
- poprawny zanik ważnego TACHO po komendzie STOP.

## 7. Następny krok

Przed integracją TACHO z `CoreState` należy jednoznacznie ustalić fizyczne mapowanie drugiego wentylatora:

1. który fizyczny wentylator odpowiada CH0 / VOUT0,
2. który fizyczny wentylator odpowiada CH1 / VOUT1,
3. który przewód TACHO trafia na GPIO17,
4. który przewód TACHO trafia na GPIO27,
5. dopiero potem przypisać nazwy `SUPPLY` i `EXTRACT` w software i dokumentacji.

Do czasu tego testu nie należy korygować mapowania na podstawie samego pierwszego wentylatora.
