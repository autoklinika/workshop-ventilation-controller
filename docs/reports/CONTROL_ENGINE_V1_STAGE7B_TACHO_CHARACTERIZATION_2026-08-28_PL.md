# Control Engine V1 — Stage7B fizyczna charakterystyka TACHO

**Data:** 2026-08-28  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/automation-v1-control-engine`  
**Kod zwalidowany fizycznie:** `672c846b92fe013f806c87e392b730e10288f658`  
**CI przed testem:** GitHub Actions `33166926327` — SUCCESS

## Cel

Stage7B rozszerzał Stage7A o pełny, stałoczasowy rozruch obu lokalnych wentylatorów EC. Celem było rozdzielenie:

1. czasu do pierwszego wiarygodnego feedbacku TACHO,
2. mechanicznego czasu dojścia do prędkości ustalonej,
3. stabilności obrotów po rozruchu.

Test nie zapisywał żadnej wartości tuningowej Control Engine i nie nadawał Control Engine prawa do aktuacji.

## Warunki testu

- oba wentylatory EC sterowane fizycznie z istniejącej, ręcznej ścieżki core,
- `2.0 V` dla supply i extract,
- 3 niezależne cykle,
- każdy cykl: 15 s ciągłego `2.0 V`,
- pomiędzy cyklami pełny `STOP / 0 V`,
- 2 s przerwy pomiędzy cyklami,
- sampling ok. 0.1 s,
- statystyka stanu ustalonego z ostatnich 5 s każdego cyklu,
- AERO, host-power, RTC i scheduled shutdown pozostawały poza zakresem aktuacji testu.

## Wynik ogólny

**PASS**.

Po każdym cyklu potwierdzono:

- `STOP / 0 V`,
- brak obserwowanego ruchu wentylatorów,
- TACHO `NOT_REQUIRED` po zatrzymaniu,
- Control Engine nadal `SHADOW-only`,
- brak automatycznego zapisu tuningu,
- brak zmiany boot ID,
- brak zmiany procesu/statusu host-power,
- brak zmiany RTC wakealarm.

## Czas do pierwszego HEALTHY

| Cykl | Supply | Extract |
|---|---:|---:|
| 1 | 1.874 s | 1.874 s |
| 2 | 1.385 s | 1.595 s |
| 3 | 1.488 s | 1.488 s |

Najgorszy zaobserwowany czas do pierwszego poprawnego TACHO:

- supply: **1.874 s**,
- extract: **1.874 s**.

To jest wyłącznie zaobserwowana granica detekcji przy 2.0 V. Nie jest to automatycznie właściwy `tacho_failure_confirmation_seconds`.

## Prędkość ustalona — ostatnie 5 s

### Cycle 1

- supply mean: **651.94 RPM**, min 646.56, max 659.45,
- extract mean: **649.16 RPM**, min 645.24, max 657.12.

### Cycle 2

- supply mean: **661.01 RPM**, min 650.67, max 782.66,
- extract mean: **660.32 RPM**, min 653.65, max 665.52.

### Cycle 3

- supply mean: **658.01 RPM**, min 654.67, max 660.20,
- extract mean: **656.68 RPM**, min 654.35, max 659.23.

Średnia wartości tail-mean ze wszystkich cykli:

- supply: **656.98 RPM**,
- extract: **655.39 RPM**.

Wcześniejsza sprzętowa charakterystyka oscyloskopowa dla 2.0 V dawała ok. **667 RPM**, więc obecny runtime TACHO jest zgodny z niezależnym pomiarem sprzętowym.

## Mechaniczny rozruch

Pierwszy poprawny TACHO pojawia się znacznie wcześniej niż zakończenie mechanicznego rozpędzania. Z logu wynika, że:

- ok. 2 s: ~250–370 RPM,
- ok. 3 s: ~470–530 RPM,
- ok. 4 s: ~590–605 RPM,
- ok. 5–6 s: ~620–650 RPM,
- ok. 6–8 s: wentylatory są już blisko stanu ustalonego ~650–660 RPM.

Wniosek: czasu `first HEALTHY` nie należy utożsamiać z czasem pełnego mechanicznego rozruchu.

## Obserwacja anomalii RPM

W cyklu 2 kanał supply zarejestrował pojedynczy maksymalny odczyt **782.66 RPM**, podczas gdy otaczający stan ustalony wynosił około 650–660 RPM. Pozostałe przebiegi były stabilne.

Obecny `TachoEstimator` uśrednia sześć ostatnich okresów. Pojedynczy zbyt krótki okres wejściowy może więc chwilowo podnieść obliczone RPM. Ta obserwacja:

- nie podważa detekcji obecności/utraty TACHO,
- nie jest obecnie podstawą do uznania kanału za uszkodzony,
- powinna zostać uwzględniona przed przyszłym nadzorem typu `zadane RPM vs rzeczywiste RPM` przez filtr plausibility/outlier.

## Wniosek dotyczący confirmation window

Nie ustawiamy jeszcze produkcyjnego `tacho_failure_confirmation_seconds`.

Powód: polityka dopuszcza pracę od **1.0 V**, a wcześniejsza sprzętowa charakterystyka potwierdziła rzeczywisty punkt pracy 1.0 V na poziomie ok. **399 RPM**. Najniższe napięcie pracy może mieć najwolniejszy start i najdłuższy czas do pierwszego TACHO.

Następny krok: powtórzyć długą charakterystykę dla **1.0 V** jako worst-case low-speed start. Dopiero po tym pomiarze dobrać confirmation window z zapasem.

## Granica bezpieczeństwa

Stage7B nie zmienił architektury Control Engine:

- `actuation_supported=false`,
- brak Control Engine -> GP8403,
- brak Control Engine -> AERO executor,
- brak Control Engine -> host-power,
- brak zmiany produkcyjnych wartości TACHO fallback,
- brak merge do `main`.
