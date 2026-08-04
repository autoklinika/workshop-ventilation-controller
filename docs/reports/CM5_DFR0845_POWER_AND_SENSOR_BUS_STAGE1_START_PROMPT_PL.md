# Prompt startowy — DFR0845 power bring-up i CM5 SENSOR BUS Stage 1

Kontynuujemy projekt Workshop Ventilation Controller.

Repozytorium:

```text
autoklinika/workshop-ventilation-controller
```

Stage 2B dla dwóch węzłów KAmod + SEN55 został zakończony, zwalidowany sprzętowo i scalony przez PR #7.

Zintegrowany commit Stage 2B na `main`:

```text
8a1556bc7829a0a50222f07f39a4bfe638bea5ec
```

Po merge dodano dokumentację handoffu, dlatego najpierw sprawdź rzeczywisty aktualny HEAD `main` i nie zakładaj, że powyższy commit jest końcem gałęzi.

Przeczytaj dokładnie:

```text
docs/reports/SEN55_MODBUS_STAGE2B_FINAL_REPORT_AND_CM5_SENSOR_BUS_HANDOFF_PL.md
docs/SOFTWARE_ARCHITECTURE_PL.md
docs/SYSTEM_ARCHITECTURE_PL.md
docs/hardware/CM5_HARDWARE_BASELINE_PL.md
docs/MODBUS_MAP_PL.md
docs/COMPIT_AERO4A2_INTEGRATION_PL.md
docs/DECISIONS_PL.md
docs/ROADMAP_PL.md
```

## Najważniejszy punkt startowy

Nie zaczynaj jeszcze implementacji `sensor_bus_worker`.

Najpierw musimy rozwiązać zasilanie dwóch modułów:

```text
DFRobot DFR0845
Gravity: Active Isolated RS485 to UART Module
```

Planowane użycie:

```text
DFR0845 #1 -> osobna magistrala SENSOR BUS
DFR0845 #2 -> osobna magistrala AERO BUS
```

Mamy problem z dostępnością wcześniej rozważanych przetwornic 3,3 V. Trzeba sprawdzić, czy są one rzeczywiście potrzebne, a następnie wybrać bezpieczne rozwiązanie dostępne do zakupu.

## Stan potwierdzony przez producenta

Oficjalna dokumentacja DFRobot dla DFR0845 podaje:

```text
zasilanie strony logicznej VCC: 3.3–5 V
```

Moduł ma również osobne zaciski:

```text
12V-IN
izolowane wyjście 12 V / do 2 W
```

Nie wolno utożsamiać `12V-IN` z wejściem zasilania logiki UART.

Schemat producenta pokazuje wejście `VCC_IN`, wewnętrzną przetwornicę, translację poziomów UART zależną od `VCC_IN`, izolowany transceiver RS-485 oraz osobny tor 12 V po stronie magistrali.

Najpierw odszukaj i przeanalizuj wyłącznie oficjalne materiały producenta:

- DFRobot Wiki dla SKU DFR0845,
- oficjalny schemat DFR0845 V1.0,
- oficjalny datasheet transceivera udostępniony przez DFRobot,
- oficjalną dokumentację CM5 IO Board dotyczącą pinów 3,3 V, UART i dopuszczalnego poboru prądu.

## Pytania, które trzeba rozstrzygnąć

1. Jakie napięcie na `VCC_IN` zapewnia bezpieczne poziomy TX/RX dla UART CM5?
2. Czy zasilenie DFR0845 napięciem 5 V może wystawić 5 V na wejście RX CM5?
3. Jaki jest rzeczywisty pobór prądu jednego DFR0845 przy 3,3 V:
   - w spoczynku,
   - podczas odbioru,
   - podczas nadawania?
4. Czy szyna 3,3 V CM5 IO Board może bezpiecznie zasilić dwa takie moduły z odpowiednim zapasem?
5. Czy lepiej zastosować jeden wspólny konwerter 12 V -> 3,3 V, dwa osobne konwertery, czy bezpośrednie zasilanie z CM5?
6. Czy wejście `12V-IN` ma być używane, skoro KAmod i AERO mają własne zasilanie?
7. Jak zachować rzeczywistą izolację galwaniczną i nie połączyć przypadkowo masy logicznej CM5 z izolowaną masą strony RS-485?
8. Jak zabezpieczyć zasilanie obu modułów: bezpiecznik, ograniczenie prądu, filtracja i złącza?
9. Jakie dostępne od ręki gotowe moduły zasilające są odpowiednie, jeśli osobna przetwornica 3,3 V okaże się konieczna?

## Zasady bezpieczeństwa

- CM5 używa logiki UART 3,3 V.
- Nie podłączaj sygnału potencjalnie 5-woltowego do GPIO CM5.
- Nie zasilaj DFR0845 z 12 V przez pin `VCC`.
- Nie łącz mas po obu stronach bariery izolacyjnej bez jednoznacznego uzasadnienia schematem.
- Nie używaj opcjonalnego wyjścia 12 V DFR0845 do zasilania KAmod ani AERO bez osobnej decyzji projektowej.
- Pierwszy test wykonuj z jednym DFR0845, zasilaczem laboratoryjnym z ograniczeniem prądu i pomiarem napięć TX/RX.
- Nie opieraj decyzji wyłącznie na opisie sklepu; sprawdź schemat i datasheet.
- Preferuj gotowe moduły i prostą architekturę dla jednego lokalnego wdrożenia. Nie projektuj własnego PCB.

## Oczekiwany rezultat pierwszej części etapu

Przed rozpoczęciem programowania przygotuj:

1. jednoznaczny schemat zasilania obu DFR0845,
2. budżet prądowy z zapasem,
3. tabelę napięć i połączeń dla strony UART i RS-485,
4. listę wymaganych gotowych elementów,
5. plan pomiarów stanowiskowych,
6. kryteria zaliczenia testu zasilania,
7. aktualizację dokumentacji i rejestru decyzji.

Nie kupuj elementów ani nie przyjmuj konkretnej topologii bez przedstawienia użytkownikowi wariantów i rekomendacji.

## Potwierdzony stan Stage 2B

Dwa węzły KAmod + SEN55 działają na jednej magistrali SENSOR BUS:

```text
slave 1
slave 2
19200 bit/s
8N1
FC04
mapa v1
19 Input Registers
```

Końcowa walidacja:

```text
kolejność 1,2: 600/600 poprawnych odczytów
kolejność 2,1: 200/200 poprawnych odczytów
łącznie: 800/800
errors=0
invalid=0
stale=0
map_errors=0
```

Produkcyny master musi zachować co najmniej 10 ms przerwy pomiędzy transakcjami do kolejnych węzłów.

## Dopiero po zamknięciu problemu zasilania

Po zatwierdzeniu i zwalidowaniu zasilania rozpocznij:

```text
CM5 SENSOR BUS Stage 1
```

Proponowana gałąź:

```text
agent/cm5-sensor-bus-worker-stage1
```

Zakres programowy:

- osobny `sensor_bus_worker`,
- worker jako jedyny właściciel UART/RS-485,
- trwała nazwa portu i konfiguracja sprzętowa,
- odczyt slave `1` i `2`,
- domyślna przerwa 10 ms między węzłami,
- walidacja wersji mapy, statusu, maski dostępności i wieku pomiaru,
- niezależne liczniki błędów per węzeł,
- utrata jednego węzła bez blokowania drugiego,
- automatyczny powrót po ponownym podłączeniu,
- normalizowany model danych niezależny od numerów rejestrów,
- integracja z autorytatywnym stanem `ventilation-core`,
- komendy diagnostyczne przez `ventilationctl`,
- testy jednostkowe, integracyjne i fizyczne na CM5,
- uruchamianie pod `systemd` dopiero po walidacji ręcznej.

## Poza zakresem

Na tym etapie nie dodawaj:

- produkcyjnego workera AERO,
- automatycznego sterowania wentylatorami na podstawie SEN55,
- progów PM/VOC,
- trybów AUTO i BOOST,
- GUI,
- MQTT,
- historii pomiarów,
- AI.

AERO pozostaje na osobnej magistrali:

```text
9600 bit/s
8N1
slave 44
FC03/FC06
```

Bezwładność fizycznej reakcji AERO nie może wpływać na świeżość odczytów SENSOR BUS.

## Zasady pracy z repozytorium

- zacznij od rzeczywistego aktualnego `main`,
- przed zmianami pokaż diagnozę problemu zasilania i rekomendowane warianty,
- nie wykonuj merge,
- nie oznaczaj PR jako Ready for Review,
- nie zmieniaj architektury dwóch oddzielnych magistral bez wyraźnej decyzji użytkownika,
- po każdym większym checkpointcie przygotuj commit, push i krótki raport,
- końcową walidację sprzętową wykonuj wspólnie z użytkownikiem krok po kroku.
