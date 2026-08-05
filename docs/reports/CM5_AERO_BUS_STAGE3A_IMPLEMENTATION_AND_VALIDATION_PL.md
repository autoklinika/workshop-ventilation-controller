# CM5 AERO BUS Stage 3A — implementacja read-only i plan walidacji

Data rozpoczęcia: 2026-08-05  
Repozytorium: `autoklinika/workshop-ventilation-controller`  
Gałąź: `agent/cm5-aero-bus-stage3a-readonly`  
Baza: `main` @ `ce6068d04cc354dd6dfbe5ee7b5f9d7090d80a4f`

## 1. Cel

Dodać do `ventilation-core` niezależny, produkcyjny tor odczytu rekuperatora przez drugą magistralę RS-485:

```text
CM5
└── /dev/ttyAMA4
    └── DFR0845 #2
        └── Modbus RTU 9600, 8N1
            └── COMPIT NANO COLOR 2 v6.30, slave 44
                └── C14
                    └── AERO 4A2
```

Stage 3A jest **wyłącznie read-only**. Kod nie zawiera FC06 ani żadnej ścieżki zapisu do NANO/AERO.

## 2. Potwierdzony kontrakt

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

Odczytywane są wyłącznie adresy potwierdzone wcześniej na rzeczywistym panelu NANO COLOR 2 v6.30:

| Adres PDU | Pole domenowe | Skalowanie |
|---:|---|---|
| 2016 | `humidity_percent` | unsigned / 10 |
| 2021 | `supply_temperature_celsius` | signed16 / 10 |
| 2022 | `extract_temperature_celsius` | signed16 / 10 |
| 2023 | `outdoor_temperature_celsius` | signed16 / 10 |
| 2033 | `fan_1_percent` | unsigned % |
| 2034 | `fan_2_percent` | unsigned % |

Nazwy `fan_1` i `fan_2` pozostają celowo neutralne. Na tym etapie nie przypisujemy ich do nawiewu i wywiewu bez dodatkowej walidacji fizycznej.

Każdy potwierdzony rejestr jest odczytywany osobnym żądaniem FC03 z przerwą 50 ms. Nie zakładamy, że niepotwierdzone adresy pomiędzy nimi mogą być bezpiecznie pobierane jednym blokiem.

## 3. Architektura

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
- jest restartowany po nieoczekiwanym zakończeniu,
- publikuje normalizowany `AeroBusState`,
- rozdziela stan portu (`ready`), komunikacji (`online`) i wiarygodności danych (`usable`),
- utrzymuje niezależne liczniki odpytań, sukcesów, błędów komunikacji i nieprawidłowych próbek.

Awaria AERO BUS nie ustawia alarmu DAC, nie zmienia napięć wentylatorów i nie zatrzymuje SENSOR BUS.

## 4. Interfejs diagnostyczny

Pełny stan:

```bash
ventilationctl status
```

Tylko AERO BUS:

```bash
ventilationctl aero
```

Przykładowa struktura:

```json
{
  "ok": true,
  "aero_bus": {
    "port": "/dev/ttyAMA4",
    "baudrate": 9600,
    "slave_address": 44,
    "register_addresses": [2016, 2021, 2022, 2023, 2033, 2034],
    "ready": true,
    "worker_alive": true,
    "online": true,
    "usable": true,
    "telemetry": {
      "humidity_percent": 45.0,
      "supply_temperature_celsius": 21.0,
      "extract_temperature_celsius": 22.0,
      "outdoor_temperature_celsius": 7.0,
      "fan_1_percent": 40,
      "fan_2_percent": 42
    }
  }
}
```

## 5. Walidacja programowa

Lokalnie przygotowany zakres przeszedł:

```text
compileall: PASS
nowe testy: 11/11 PASS
```

Testy obejmują:

- FC03 i poprawną budowę żądania,
- odczyt wyłącznie sześciu potwierdzonych rejestrów,
- signed16 dla temperatur,
- skalowanie wilgotności,
- walidację zakresu mocy wentylatorów,
- brak danych przy niepełnym snapshotcie,
- rozdzielenie błędu transportu i błędu danych,
- niezależność awarii AERO od DAC,
- konfigurację `/dev/ttyAMA4`, slave `44`, 9600 w systemd,
- zachowanie bezpiecznego `KillMode=mixed`.

Pełny workflow GitHub Actions musi zostać zaliczony po otwarciu Draft PR.

## 6. Walidacja sprzętowa na CM5

Najpierw nie instalować nowej jednostki systemd. Zatrzymać działającą usługę i uruchomić Stage 3A ręcznie.

### 6.1. Aktualizacja gałęzi

```bash
cd /home/wentylacja/workshop-ventilation-controller
git fetch origin
git switch agent/cm5-aero-bus-stage3a-readonly
git pull
```

### 6.2. Sprawdzenie portu

```bash
ls -l /dev/ttyAMA4
sudo fuser -v /dev/ttyAMA4
sudo systemctl status serial-getty@ttyAMA4.service --no-pager
```

Port nie może być zajęty przez inny proces ani konsolę szeregową.

### 6.3. Testy lokalne

```bash
PYTHONPATH=src python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

### 6.4. Ręczne uruchomienie

```bash
sudo systemctl stop ventilation-core.service

sudo install -d -o wentylacja -g wentylacja -m 0770 \
  /run/workshop-ventilation

cd /home/wentylacja/workshop-ventilation-controller

sudo -u wentylacja env PYTHONPATH=src python3 -m ventilation_core.main \
  --socket /run/workshop-ventilation/ventilation-core.sock \
  --sensor-port /dev/ttyAMA0 \
  --sensor-addresses 1,2 \
  --sensor-baud 19200 \
  --sensor-timeout 0.5 \
  --sensor-poll-interval 1.0 \
  --sensor-inter-node-delay 0.010 \
  --sensor-reconnect-delay 1.0 \
  --aero-port /dev/ttyAMA4 \
  --aero-address 44 \
  --aero-baud 9600 \
  --aero-timeout 0.5 \
  --aero-poll-interval 2.0 \
  --aero-inter-register-delay 0.050 \
  --aero-reconnect-delay 1.0 \
  --log-level INFO
```

W drugim terminalu:

```bash
cd /home/wentylacja/workshop-ventilation-controller
PYTHONPATH=src python3 -m ventilation_core.ctl aero
PYTHONPATH=src python3 -m ventilation_core.ctl sensors
PYTHONPATH=src python3 -m ventilation_core.ctl status
```

### 6.5. Kryteria PASS

- `aero_bus.ready=true`,
- `worker_alive=true`,
- `online=true`,
- `usable=true`,
- wszystkie sześć pól ma wartości zgodne z panelem,
- `successful_polls` rośnie,
- `communication_errors=0`,
- `invalid_samples=0`,
- SENSOR BUS nadal odczytuje slave 1 i 2 bez nowych błędów,
- DAC pozostaje `hardware_ready=true`,
- odłączenie AERO BUS ustawia `online=false`, ale nie wpływa na sensory ani DAC,
- ponowne podłączenie przywraca dane bez restartu rdzenia,
- minimum 300 pełnych snapshotów bez błędów,
- kontrolowany restart usługi i pełny reboot CM5 przechodzą poprawnie.

Dopiero po ręcznej walidacji należy zainstalować zaktualizowaną jednostkę systemd.

## 7. Świadomie poza zakresem

Stage 3A nie dodaje:

- FC06,
- wyboru biegu,
- wietrzenia,
- maszyny stanów wykonania,
- timeoutu fizycznego wykonania 45 s,
- identyfikacji `fan_1`/`fan_2` jako nawiew/wywiew,
- automatyki jakości powietrza,
- GUI, MQTT ani historii.

Sterowanie AERO będzie osobnym Stage 3B dopiero po pełnym zaliczeniu read-only.
