# CM5 SENSOR BUS Stage 1 — raport końcowy i walidacja sprzętowa

Data: 2026-08-05  
Repozytorium: `autoklinika/workshop-ventilation-controller`  
Gałąź: `agent/cm5-sensor-bus-worker-stage1-refresh`  
Draft PR: `#8`  
Baza etapu: `main` @ `40de40f84218d8e4b74ec7d57f5eb81700530746`

## 1. Wynik etapu

CM5 SENSOR BUS Stage 1 został zaimplementowany i zwalidowany na docelowym sprzęcie.

Uruchomiony tor produkcyjny:

```text
CM5
└── /dev/ttyAMA0
    └── DFR0845
        └── Modbus RTU 19200, 8N1, FC04
            ├── KAmod + SEN55, slave 1
            └── KAmod + SEN55, slave 2
```

Oba węzły są odczytywane przez osobny, nadzorowany proces `sensor_bus_worker`, który jest jedynym właścicielem `/dev/ttyAMA0`. Dane są publikowane w autorytatywnym `CoreState` i dostępne przez lokalny interfejs `ventilationctl sensors`.

Końcowy status Stage 1: **PASS**.

## 2. Konfiguracja zwalidowana na CM5

```text
Port:                    /dev/ttyAMA0
Warstwa fizyczna:        RS-485 przez DFR0845
Protokół:                Modbus RTU
Prędkość:                19200 bit/s
Format:                  8N1
Funkcja:                 FC04 Read Input Registers
Adresy:                  1 i 2
Mapa:                    SEN55 Modbus map v1
Liczba rejestrów:        19 Input Registers
Przerwa między węzłami:  co najmniej 10 ms
Okres odpytywania:       1,0 s
Timeout odpowiedzi:      0,5 s
```

AERO BUS na `/dev/ttyAMA4`, 9600 bit/s i slave `44` pozostaje poza zakresem tego etapu.

## 3. Przygotowanie systemu operacyjnego

Na docelowym CM5 potwierdzono:

- `/dev/ttyAMA0` istnieje i należy do grupy `dialout`,
- użytkownik `wentylacja` należy do grupy `dialout`,
- `serial-getty@ttyAMA0.service` jest wyłączony i nie zajmuje portu,
- kernel nie używa `/dev/ttyAMA0` jako konsoli szeregowej,
- zainstalowany jest `pyserial`,
- proces uruchomiony jako użytkownik `wentylacja` może otworzyć UART w trybie wyłącznym.

## 4. Korekta okablowania DFR0845

Pierwszy brak odpowiedzi wynikał z zamienionych linii UART po stronie DFR0845.

Poprawne połączenie:

```text
CM5 TX -> DFR0845 T
CM5 RX <- DFR0845 R
```

Po korekcie oba węzły zaczęły zwracać kompletne ramki Modbus o długości 43 bajtów:

```text
slave 1: 01 04 26 ... CRC
slave 2: 02 04 26 ... CRC
```

## 5. Wykryta awaria sprzętowa KAmod

Podczas walidacji pierwotny moduł KAmod przeznaczony dla slave `2` przestał odpowiadać na RS-485.

Diagnostyka przez USB potwierdziła jednocześnie:

```text
firmware:                 0.3.0-stage2b
resolved slave address:   2
Modbus RTU:               uruchomiony, 19200 8N1
UART2:                    TX=25, RX=27, DE/RE=26
SEN55:                    wykryty i pracujący
pomiary:                  poprawne, maska 0xFF
restart ESP32:            brak
```

Przeniesienie modułu w miejsce sprawnego slave `1` oraz próby pod adresami `1` i `2` nie przywróciły komunikacji. Pozwoliło to wykluczyć:

- CM5,
- DFR0845,
- przewody i miejsce wpięcia,
- zapisany adres NVS,
- firmware ESP32,
- czujnik SEN55.

Usterkę zlokalizowano w lokalnym torze RS-485 płytki KAmod. Moduł został wymieniony, wgrano ten sam firmware i zapisano adres `2`. Po wymianie oba slave odpowiedziały poprawnie w 10 kolejnych cyklach, łącznie 20/20 transakcji.

Wniosek: awaria miała charakter sprzętowy i nie była defektem `sensor_bus_worker` ani protokołu.

## 6. Walidacja funkcjonalna workera

Po uruchomieniu produkcyjnego workera potwierdzono dla obu urządzeń:

```text
online=true
usable=true
measurement_valid=true
measurement_stale=false
sensor_present=true
availability_mask=255
status_mask=3
firmware_version=0.3
map_version=1
communication_errors=0
consecutive_failures=0
worker_alive=true
worker_restarts=0
```

Odczyty PM, wilgotności, temperatury, VOC Index i NOx Index były aktualizowane niezależnie dla każdego węzła.

## 7. Walidacja degradacji i automatycznego powrotu

Sprawdzono zachowanie po utracie pojedynczego slave.

Dla odłączonego węzła worker publikował:

```text
online=false
usable=false
communication_errors rośnie
consecutive_failures rośnie
```

W tym samym czasie drugi slave pozostawał odpytywany i zachowywał poprawny stan. Proces SENSOR BUS pozostawał żywy, a licznik `worker_restarts` nie wzrastał.

Po ponownym podłączeniu węzła komunikacja wróciła automatycznie, bez restartu `ventilation-core` i bez restartu `sensor_bus_worker`.

Potwierdzono tym samym separację domen awarii:

```text
awaria slave 1 != awaria slave 2
awaria SENSOR BUS != awaria DAC / I2C
```

## 8. Test długotrwały

Wykonano test ciągły przekraczający wymagane 300 cykli na każdy węzeł.

Wynik:

```text
slave 1: polls=355, successful_polls=355
slave 2: polls=355, successful_polls=355
łącznie: 710/710 poprawnych transakcji
```

Dla obu węzłów:

```text
communication_errors=0
consecutive_failures=0
invalid_measurements=0
stale_measurements=0
map_version_errors=0
```

Globalnie:

```text
ready=true
worker_alive=true
worker_restarts=0
last_error=null
```

## 9. Walidacja systemd i wykryty problem shutdown

Usługa została zainstalowana jako:

```text
/etc/systemd/system/ventilation-core.service
```

Pierwszy kontrolowany restart ujawnił błąd sekwencji zamykania:

```text
Hardware command timed out: stop
Failed to force DAC outputs to zero during shutdown
State 'stop-sigterm' timed out
SIGKILL
```

Przyczyną był domyślny `KillMode=control-group`. `systemd` wysyłał `SIGTERM` równocześnie do procesu głównego i jego procesów potomnych. Worker DAC kończył się, zanim proces główny zdążył wysłać mu polecenie `stop` i potwierdzić wyzerowanie wyjść.

Jednostkę poprawiono:

```ini
TimeoutStopSec=20
KillSignal=SIGTERM
KillMode=mixed
```

Po poprawce początkowy `SIGTERM` trafia do procesu głównego, który wykonuje kontrolowaną sekwencję:

1. wymuszenie `0 V` na obu kanałach DAC,
2. zamknięcie workera DAC,
3. zatrzymanie `sensor_bus_worker`,
4. zamknięcie Unix socketu,
5. zakończenie procesu głównego.

Ponowny restart usługi zakończył się prawidłowo:

```text
Stopping ventilation-core.service...
Deactivated successfully.
Stopped ventilation-core.service.
Started ventilation-core.service.
```

Nie wystąpiły timeout, `SIGKILL` ani błąd wyzerowania DAC.

## 10. Walidacja pełnego restartu CM5

Po wykonaniu `sudo reboot` potwierdzono:

```text
ventilation-core.service: enabled
ventilation-core.service: active (running)
```

Usługa uruchomiła się automatycznie podczas startu systemu. Stan po restarcie:

```text
mode=STOP
supply_voltage=0.0
extract_voltage=0.0
hardware_ready=true
output_state_known=true
consecutive_hardware_failures=0
active_alarms=[]
```

SENSOR BUS po restarcie:

```text
ready=true
worker_alive=true
worker_restarts=0
last_error=null
```

Po około 100 cyklach:

```text
slave 1: polls=101, successful_polls=101, errors=0
slave 2: polls=101, successful_polls=101, errors=0
```

Oba węzły były `online=true`, `usable=true`, miały `availability_mask=255`, `status_mask=3` oraz mapę `v1`.

Ciągłość `uptime_seconds` węzłów była oczekiwana, ponieważ KAmod były zasilane niezależnie od restartowanego CM5.

## 11. Walidacja programowa końcowego checkpointu przed raportem

Po poprawce sekwencji systemd:

```text
Commit:     eb45fa615329b01de28c6b6d9385c533bed0e768
Workflow:   Ventilation Core Tests
Run:        #296
compileall: PASS
unit tests: 33/33 PASS
conclusion: success
```

Testy regresyjne sprawdzają między innymi:

- `KillMode=mixed`,
- limit czasu wystarczający na kontrolowane sprzątnięcie workerów,
- dotychczasowe zachowanie Modbus RTU i mapy SEN55,
- izolację timeoutu pojedynczego węzła,
- integrację SENSOR BUS z `CoreState`,
- bezpieczne zamykanie procesów.

## 12. Kryteria odbioru

| Kryterium | Wynik |
|---|---:|
| Odczyt slave `1` i `2` na jednej magistrali | PASS |
| FC04, 19 rejestrów, mapa v1 | PASS |
| Minimum 10 ms między węzłami | PASS |
| Niezależne statystyki obu slave | PASS |
| Timeout jednego slave nie blokuje drugiego | PASS |
| Automatyczny powrót po ponownym podłączeniu | PASS |
| Brak wpływu błędu SENSOR BUS na DAC | PASS |
| Minimum 300 cykli na węzeł bez błędów | PASS |
| Uruchomienie przez systemd | PASS |
| Kontrolowany restart bez SIGKILL | PASS |
| Bezpieczny stan DAC `STOP`, `0 V / 0 V` | PASS |
| Automatyczny start po pełnym reboot CM5 | PASS |
| 33/33 testy programowe | PASS |

## 13. Zakres zamknięty

Stage 1 dostarcza:

- produkcyjny `sensor_bus_worker`,
- obsługę dwóch KAmod + SEN55 na `/dev/ttyAMA0`,
- pełny model diagnostyczny obu węzłów,
- nadzór procesu i automatyczną rekonfigurację portu,
- interfejs `ventilationctl sensors`,
- konfigurację systemd działającą po restarcie usługi i CM5,
- niezależność awarii czujników od toru DAC.

## 14. Poza zakresem i następne etapy

Nadal poza zakresem pozostają:

- AERO BUS na `/dev/ttyAMA4`,
- zapis FC06 do rekuperatora slave `44`,
- automatyczne sterowanie wentylacją na podstawie SEN55,
- progi PM/VOC oraz tryby AUTO i BOOST,
- GUI, MQTT, historia danych i AI.

PR `#8` pozostaje Draft. Nie wykonano merge i nie oznaczono go jako Ready for Review.
