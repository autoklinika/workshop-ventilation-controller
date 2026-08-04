# SEN55 Modbus Stage 2B — raport końcowy i handoff do CM5 SENSOR BUS

Data zakończenia: 2026-08-04

Repozytorium: `autoklinika/workshop-ventilation-controller`

PR: `#7`

Merge commit `main`:

```text
8a1556bc7829a0a50222f07f39a4bfe638bea5ec
```

## 1. Status końcowy

Stage 2B został zakończony, zwalidowany sprzętowo i scalony do `main`.

Dwa niezależne węzły KAmod ESP32 POW RS485 + SEN55 pracują na jednej magistrali SENSOR BUS:

```text
KAmod + SEN55 #1 -> Modbus slave 1
KAmod + SEN55 #2 -> Modbus slave 2
```

Oba urządzenia używają tego samego firmware:

```text
0.3.0-stage2b
```

Różnią się wyłącznie trwałym adresem zapisanym lokalnie w NVS.

## 2. Potwierdzony kontrakt SENSOR BUS

```text
Modbus RTU
19200 bit/s
8N1
FC04 Read Input Registers
mapa rejestrów v1
19 Input Registers
interfejs read-only
```

Nie dodano:

- zdalnego zapisu konfiguracji,
- zmiany adresu przez Modbus,
- wspólnej magistrali z rekuperatorem,
- MQTT,
- GUI,
- automatyki wentylatorów,
- produkcyjnego mastera CM5.

## 3. Zakończona walidacja sprzętowa

Po dodaniu kontrolowanej przerwy między zapytaniami wykonano test w obu kolejnościach.

Kolejność `1,2`:

```text
slave=1: polls=300 success=300 errors=0 invalid=0 stale=0 map_errors=0
slave=2: polls=300 success=300 errors=0 invalid=0 stale=0 map_errors=0
```

Kolejność `2,1`:

```text
slave=2: polls=100 success=100 errors=0 invalid=0 stale=0 map_errors=0
slave=1: polls=100 success=100 errors=0 invalid=0 stale=0 map_errors=0
```

Łącznie:

```text
800/800 poprawnych odpytań
0 timeoutów
0 błędów protokołu
0 pomiarów invalid
0 pomiarów stale
0 błędów mapy
```

## 4. Istotna obserwacja z testów

Bez jawnej przerwy pomiędzy odpowiedzią pierwszego urządzenia i zapytaniem do drugiego sporadyczny timeout dotyczył zawsze urządzenia odpytywanego jako drugie.

Po odwróceniu kolejności błąd przenosił się z adresu `2` na adres `1`. Wykluczyło to usterkę konkretnego KAmod, SEN55 lub adresacji.

Do narzędzia master dodano domyślnie:

```text
inter-node delay = 10 ms
```

Po tej zmianie obie kolejności działały bezbłędnie.

Wniosek projektowy dla produkcyjnego mastera CM5:

- zachować wymuszoną ciszę między transakcjami,
- nie wysyłać kolejnego żądania natychmiast po odebraniu poprzedniej odpowiedzi,
- raportować błędy osobno dla każdego węzła,
- awaria jednego slave nie może blokować odpytywania drugiego.

## 5. CI

Dla końcowego HEAD Stage 2B zakończone powodzeniem:

- `Ventilation Core Tests`,
- `Sensor node firmware`,
- hostowe testy mapy rejestrów,
- kontrola narzędzi PC,
- pełny build ESP-IDF 6.0.2.

## 6. Następny etap

Następny etap to produkcyjna obsługa SENSOR BUS przez `ventilation-core` na CM5.

Proponowana gałąź:

```text
agent/cm5-sensor-bus-worker-stage1
```

Docelowa architektura:

```text
ventilation-core
    ↓
sensor_bus_worker
    ↓
izolowany interfejs UART-RS485 DFR0845
    ↓
KAmod + SEN55 slave 1
KAmod + SEN55 slave 2
```

Worker ma być jedynym właścicielem portu UART/RS-485. GUI, MQTT, narzędzia webowe i logika domenowa nie mogą otwierać portu ani operować na surowych rejestrach.

## 7. Pierwszy problem następnej rozmowy — zasilanie DFR0845

Prace programowe nad workerem nie powinny rozpocząć się przed rozstrzygnięciem zasilania dwóch modułów DFR0845.

Planowane są dwa niezależne interfejsy:

```text
DFR0845 #1 -> SENSOR BUS
DFR0845 #2 -> AERO BUS
```

Aktualny problem praktyczny:

- braki magazynowe wcześniej rozważanych przetwornic do zasilania 3,3 V,
- konieczność ustalenia bezpiecznego i prostego sposobu zasilania obu DFR0845 z dostępnych szyn systemu,
- brak zgody na przypadkowe zasilenie logiki UART napięciem niebezpiecznym dla CM5.

Oficjalna dokumentacja DFRobot podaje dla wejścia logicznego modułu:

```text
VCC: 3.3–5 V
```

Moduł posiada również osobne zaciski `12V-IN` oraz izolowane wyjście `12 V / do 2 W`. Nie wolno utożsamiać wejścia `12V-IN` z zasilaniem logicznej strony UART.

Schemat DFR0845 pokazuje:

- wejście `VCC_IN` po stronie UART,
- wewnętrzną przetwornicę do zasilania części modułu,
- translację sygnałów UART zależną od napięcia `VCC_IN`,
- osobną izolowaną stronę RS-485,
- osobny tor opcjonalnego zasilania 12 V po stronie magistrali.

Źródła producenta:

- DFRobot Wiki — `Gravity: Active Isolated RS485 to UART Module`, SKU DFR0845,
- schemat `DFR0845_gravity-activate-isolated-rs485-to-uart-module_schematics_V1.0.pdf`,
- datasheet transceivera TD541S485H udostępniony przez DFRobot.

## 8. Decyzje, których nie wolno przyjąć bez pomiarów

Nie zakładać automatycznie, że:

- DFR0845 można bezpiecznie zasilić z pinu 3,3 V CM5 bez sprawdzenia poboru prądu,
- zasilenie DFR0845 napięciem 5 V jest bezpieczne dla wejść UART CM5,
- wejście `12V-IN` zasila stronę logiczną UART,
- opcjonalne wyjście 12 V będzie używane do zasilania KAmod lub AERO,
- oba moduły mogą być zasilane z jednego małego konwertera bez obliczenia zapasu,
- masa logiczna CM5 może być łączona z izolowaną masą RS-485 po stronie magistrali.

## 9. Pierwszy zakres następnej rozmowy

Najpierw należy:

1. potwierdzić dokładną rewizję posiadanych DFR0845,
2. odtworzyć rzeczywisty schemat zasilania CM5, DAC i obu magistral,
3. określić dostępne szyny: 12 V, 5 V i 3,3 V,
4. sprawdzić dopuszczalny prąd szyny 3,3 V CM5 IO Board,
5. zmierzyć pobór jednego DFR0845 przy zasilaniu 3,3 V:
   - bez komunikacji,
   - podczas odbioru,
   - podczas nadawania,
6. sprawdzić poziomy TX/RX względem `VCC_IN`,
7. rozstrzygnąć, czy moduły będą zasilane:
   - bezpośrednio z 3,3 V CM5,
   - z dedykowanego konwertera 12 V -> 3,3 V,
   - ze wspólnego konwertera o odpowiednim zapasie,
   - innym bezpiecznym rozwiązaniem,
8. dopiero po decyzji zasilania wybrać UART-y CM5 i rozpocząć `sensor_bus_worker`.

## 10. Ograniczenia następnego etapu

W pierwszym etapie CM5 SENSOR BUS nie dodawać:

- sterowania AERO,
- automatycznych progów PM/VOC,
- trybów AUTO/BOOST,
- GUI,
- MQTT,
- bazy historii,
- AI.

Zakres ma objąć wyłącznie:

- bezpieczne zasilanie i połączenie DFR0845,
- trwałe przypisanie portu,
- osobny worker SENSOR BUS,
- odczyt slave `1` i `2`,
- walidację mapy oraz statusów,
- diagnostykę utraty i powrotu komunikacji,
- integrację autorytatywnego stanu z `ventilation-core`,
- testy na rzeczywistym CM5.
