# CM5 AERO BUS Stage 3A — implementacja i końcowa walidacja sprzętowa

Data rozpoczęcia: 2026-08-05  
Data zakończenia walidacji: 2026-08-05  
Repozytorium: `autoklinika/workshop-ventilation-controller`  
Gałąź: `agent/cm5-aero-bus-stage3a-readonly`  
Baza: `main` @ `ce6068d04cc354dd6dfbe5ee7b5f9d7090d80a4f`

## 1. Wynik etapu

**Stage 3A zakończono wynikiem PASS.**

Na docelowym CM5 uruchomiono niezależny, nadzorowany i produkcyjny tor odczytu rekuperatora przez drugą magistralę RS-485:

```text
CM5
└── /dev/ttyAMA4
    └── DFR0845 #2
        └── Modbus RTU 9600, 8N1
            └── COMPIT NANO COLOR 2 v6.30, slave 44
                └── C14
                    └── AERO 4A2
```

Runtime Stage 3A pozostaje **wyłącznie read-only**. `aero_bus_worker` nie zawiera FC06 ani żadnej ścieżki zapisu do NANO/AERO.

## 2. Potwierdzony kontrakt AERO BUS

```text
port:        /dev/ttyAMA4
baud:        9600 bit/s
format:      8N1
slave:       44
funkcja:     FC03 Read Holding Registers
poll:        2,0 s
timeout:     0,5 s
odstęp:      50 ms między rejestrami
```

Odczytywane są wyłącznie potwierdzone adresy PDU:

| Adres PDU | Pole domenowe | Skalowanie |
|---:|---|---|
| 2016 | `humidity_percent` | unsigned / 10 |
| 2021 | `supply_temperature_celsius` | signed16 / 10 |
| 2022 | `extract_temperature_celsius` | signed16 / 10 |
| 2023 | `outdoor_temperature_celsius` | signed16 / 10 |
| 2033 | `fan_1_percent` | unsigned % |
| 2034 | `fan_2_percent` | unsigned % |

Każdy rejestr jest pobierany osobnym żądaniem FC03 z przerwą 50 ms. Nie przyjęto założenia, że niepotwierdzone adresy pośrednie są bezpieczne dla odczytu blokowego.

Nazwy `fan_1` i `fan_2` pozostają neutralne. Stage 3A nie przypisuje ich jeszcze do nawiewu i wywiewu.

## 3. Architektura wykonawcza

```text
ventilation-core
├── proces główny — CoreState i Unix socket
├── hardware worker — I²C / DFR0971
├── sensor_bus_worker — /dev/ttyAMA0, slave 1 i 2
└── aero_bus_worker — /dev/ttyAMA4, slave 44, tylko FC03
```

`aero_bus_worker`:

- jest jedynym właścicielem `/dev/ttyAMA4`,
- działa w osobnym procesie,
- nie blokuje SENSOR BUS ani DAC,
- automatycznie ponownie otwiera port po błędzie,
- jest nadzorowany i restartowany po nieoczekiwanym zakończeniu procesu,
- publikuje normalizowany `AeroBusState`,
- rozdziela `ready`, `online` i `usable`,
- utrzymuje niezależne liczniki odpytań, sukcesów, błędów komunikacji i nieprawidłowych próbek.

Awaria AERO BUS nie ustawia alarmu DAC, nie zmienia nastaw wentylatorów 0–10 V i nie zatrzymuje SENSOR BUS.

## 4. Interfejs diagnostyczny

Pełny stan rdzenia:

```bash
PYTHONPATH=src python3 -m ventilation_core.ctl status
```

Tylko AERO BUS:

```bash
PYTHONPATH=src python3 -m ventilation_core.ctl aero
```

Tylko SENSOR BUS:

```bash
PYTHONPATH=src python3 -m ventilation_core.ctl sensors
```

## 5. Walidacja programowa

Zwalidowany przed testami sprzętowymi HEAD:

```text
Commit:     afc619d2bad5d96899342c9d34f902b82ab5ccad
Workflow:   Ventilation Core Tests
Run:        #318
Python:     3.11.15
compileall: PASS
unit tests: 42/42 PASS
conclusion: success
```

Testy obejmują między innymi:

- FC03 i poprawną budowę żądania,
- odczyt wyłącznie sześciu potwierdzonych rejestrów,
- dekodowanie signed16 temperatur,
- skalowanie wilgotności,
- walidację zakresu mocy wentylatorów,
- odrzucenie niepełnego lub nieprawidłowego snapshotu,
- rozdzielenie błędu transportu i błędu danych,
- niezależność awarii AERO BUS od DAC i SENSOR BUS,
- integrację z `CoreState`,
- konfigurację `/dev/ttyAMA4`, slave `44`, 9600 bit/s w systemd,
- zachowanie bezpiecznego `KillMode=mixed`.

## 6. Walidacja sprzętowa na docelowym CM5

### 6.1. Warunki wejściowe

Potwierdzono:

- `/dev/ttyAMA4` istnieje i należy do grupy `dialout`,
- port nie był zajęty przez inny proces,
- `serial-getty@ttyAMA4.service` był nieaktywny i wyłączony,
- CM5 używa osobnego DFR0845 dla AERO BUS,
- SENSOR BUS pracuje niezależnie na `/dev/ttyAMA0`.

### 6.2. Pierwszy pełny snapshot

Pierwszy test ręcznie uruchomionego Stage 3A dał:

```text
AERO BUS:
  ready=true
  worker_alive=true
  worker_restarts=0
  online=true
  usable=true
  polls=7
  successful_polls=7
  communication_errors=0
  consecutive_failures=0
  invalid_samples=0
```

Przykładowa potwierdzona telemetria:

```text
humidity_percent=44,0
supply_temperature_celsius=31,6
extract_temperature_celsius=32,0
outdoor_temperature_celsius=32,0
fan_1_percent=0
fan_2_percent=0
```

Wartości sześciu pól zostały porównane z panelem NANO COLOR 2 i potwierdzone przez użytkownika jako prawidłowe.

W tym samym czasie:

- oba węzły SENSOR BUS były `online=true` i `usable=true`,
- oba węzły miały zero błędów komunikacji,
- DAC pozostawał w `STOP`,
- nastawy programowe wynosiły `0,0 V / 0,0 V`,
- `hardware_ready=true`,
- brak aktywnych alarmów.

### 6.3. Odłączenie i automatyczny powrót AERO BUS

Podczas kontrolowanego odłączenia tylko magistrali AERO uzyskano:

```text
ready=true
worker_alive=true
worker_restarts=0
online=false
usable=false
last_error="No response or incomplete Modbus header"
communication_errors=22
consecutive_failures>0
```

W trakcie awarii:

- SENSOR BUS nadal odczytywał oba węzły bez błędów komunikacji,
- DAC pozostał w `STOP`,
- nastawy i stan wyjść nie zostały zmienione,
- rdzeń nie został zrestartowany,
- worker AERO nie zakończył procesu.

Po ponownym podłączeniu komunikacja wróciła automatycznie:

```text
online=true
usable=true
consecutive_failures=0
last_error=null
worker_restarts=0
```

Licznik `communication_errors=22` prawidłowo pozostał licznikiem historycznym wykonanego testu awarii.

### 6.4. Test długotrwały

Punkt początkowy po odzyskaniu magistrali:

```text
successful_polls=96
communication_errors=22
invalid_samples=0
```

Stan końcowy:

```text
polls=475
successful_polls=453
communication_errors=22
consecutive_failures=0
invalid_samples=0
worker_restarts=0
online=true
usable=true
```

Przyrost po odzyskaniu magistrali:

```text
453 - 96 = 357 kolejnych pełnych i poprawnych snapshotów
```

W całym okresie testu nie przybył żaden nowy błąd komunikacji ani nieprawidłowa próbka.

Równolegle oba węzły SENSOR BUS osiągnęły `949/949` poprawnych odpytań bez błędów komunikacji.

### 6.5. Kontrolowana walidacja FC06 poza runtime Stage 3A

Sterowanie nie zostało dodane do `aero_bus_worker`. Do ręcznej walidacji sprzętowej wykorzystano osobne zabezpieczone narzędzie:

```text
tools/compit_nano_v630_control_test.py
```

Narzędzie:

- dopuszcza zapis wyłącznie do ADR `1080` i `1081`,
- wymaga `--execute --confirm NANO630`,
- odczytuje stan poprzedni,
- weryfikuje echo FC06,
- weryfikuje readback FC03,
- obserwuje fizyczną telemetrię mocy wentylatorów,
- automatycznie przywraca poprzednią wartość, jeżeli nie użyto `--keep`.

Na rzeczywistym NANO/AERO potwierdzono:

- ADR `1081`: wietrzenie ON i powrót do poprzedniego stanu,
- ADR `1080`: bieg `1` i powrót,
- ADR `1080`: bieg `2` i powrót,
- ADR `1080`: bieg `3` i powrót,
- prawidłowe przyjęcie poleceń przez Modbus,
- prawidłową fizyczną reakcję AERO,
- automatyczne przywrócenie stanu bazowego.

Walidacja wykazała, że wcześniejsze okno 45 s jest zbyt krótkie. Dla Stage 3B obowiązuje:

```text
maksymalny czas oczekiwania na fizyczne wykonanie lub powrót: 60 s
telemetry polling podczas oczekiwania: 2 s
```

Potwierdzenie FC06 nie zmienia zakresu Stage 3A. Produkcyjna ścieżka zapisu i maszyna stanów będą implementowane dopiero w Stage 3B.

### 6.6. Instalacja i kontrolowany restart systemd

Zainstalowano jednostkę:

```text
/etc/systemd/system/ventilation-core.service
```

Potwierdzono:

- `enabled`,
- `active (running)`,
- automatyczny start workera SENSOR BUS,
- automatyczny start workera AERO BUS,
- aktywny Unix socket,
- poprawny stan DAC, SENSOR BUS i AERO BUS po starcie.

Kontrolowany `systemctl restart ventilation-core.service` zakończył się czysto:

```text
Stopping ventilation-core.service...
ventilation-core.service: Deactivated successfully.
Stopped ventilation-core.service.
Started ventilation-core.service.
```

Nie wystąpiły:

- timeout zatrzymania,
- `SIGKILL`,
- błąd zerowania DAC,
- nieoczekiwany restart workera,
- błąd otwarcia UART.

Po restarcie AERO BUS miał `4/4` poprawne odczyty, a każdy węzeł SENSOR BUS `9/9` poprawnych odczytów.

### 6.7. Pełny reboot CM5

Po pełnym `sudo reboot` potwierdzono:

```text
systemctl is-enabled ventilation-core.service -> enabled
systemctl is-active ventilation-core.service  -> active
```

Usługa uruchomiła się automatycznie podczas bootu. Stan po około jednej minucie:

```text
AERO BUS:
  ready=true
  worker_alive=true
  worker_restarts=0
  online=true
  usable=true
  polls=27
  successful_polls=27
  communication_errors=0
  invalid_samples=0

SENSOR BUS slave 1:
  online=true
  usable=true
  polls=66
  successful_polls=66
  communication_errors=0

SENSOR BUS slave 2:
  online=true
  usable=true
  polls=66
  successful_polls=66
  communication_errors=0

Core/DAC:
  mode=STOP
  supply_voltage=0,0
  extract_voltage=0,0
  hardware_ready=true
  output_state_known=true
  active_alarms=[]
```

`slave 2` raportował `sensor_errors=11`. Licznik pochodzi z celowego wcześniejszego odłączenia SEN55, pozostawał stabilny i nie był błędem RS-485 ani aktualną awarią czujnika.

System nie miał włączonego trwałego journalu, dlatego `journalctl -b -1` nie mógł odczytać logu poprzedniego bootu. Nie wpływa to na wynik testu: automatyczny start po pełnym reboocie oraz poprawny stan wszystkich domen zostały bezpośrednio potwierdzone.

## 7. Końcowe kryteria PASS

| Kryterium | Wynik |
|---|---|
| `/dev/ttyAMA4`, 9600 8N1, slave 44 | PASS |
| sześć osobnych odczytów FC03 | PASS |
| zgodność danych z panelem | PASS |
| `ready/online/usable` | PASS |
| izolacja awarii AERO BUS | PASS |
| automatyczny powrót bez restartu core | PASS |
| minimum 300 kolejnych snapshotów | PASS — 357 |
| brak nowych błędów po odzyskaniu | PASS |
| brak wpływu na SENSOR BUS | PASS |
| brak wpływu na DAC | PASS |
| kontrolowany restart systemd | PASS |
| automatyczny start po pełnym reboocie | PASS |
| wietrzenie przez ADR 1081, narzędzie testowe | PASS |
| biegi 1, 2 i 3 przez ADR 1080, narzędzie testowe | PASS |
| automatyczne przywrócenie stanu | PASS |
| wymagane okno wykonania 60 s | POTWIERDZONE |

## 8. Świadomie poza zakresem Stage 3A

Produkcyjny runtime Stage 3A nie dodaje:

- FC06,
- wyboru biegu,
- wietrzenia,
- maszyny stanów wykonania,
- identyfikacji `fan_1`/`fan_2` jako nawiew/wywiew,
- automatyki jakości powietrza,
- GUI, MQTT ani historii.

## 9. Handoff do Stage 3B

Stage 3B powinien dodać kontrolowane FC06 dla:

```text
ADR 1080 — bieg 0..3
ADR 1081 — wietrzenie 0/1
```

Wymagana maszyna stanów:

```text
REQUESTED
ACCEPTED_BY_NANO
WAITING_FOR_AERO
PHYSICALLY_CONFIRMED
EXECUTION_TIMEOUT
```

Obowiązujące zasady:

- read-before-write,
- idempotencja,
- echo FC06 i readback nie są fizycznym potwierdzeniem,
- telemetria `2033/2034` co 2 s podczas oczekiwania,
- timeout wykonania i powrotu **60 s**,
- brak sprzecznych poleceń podczas oczekiwania,
- bezpieczne odtworzenie stanu po błędzie,
- audyt żądań, przyjęcia i fizycznego wykonania.

## 10. Decyzja końcowa

**CM5 AERO BUS Stage 3A jest zakończony, zwalidowany sprzętowo i gotowy do integracji.**

PR pozostaje Draft do czasu wyraźnej decyzji użytkownika o oznaczeniu Ready for Review i merge.
