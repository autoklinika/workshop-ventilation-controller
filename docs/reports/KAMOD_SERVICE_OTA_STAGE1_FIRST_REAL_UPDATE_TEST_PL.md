# KAmod Service OTA Stage 1 — pierwszy rzeczywisty test aktualizacji

Data: 2026-08-06

## 1. Cel

Wykonać pierwszy rzeczywisty transfer OTA wyłącznie na `sensor-node-1`:

```text
wersja źródłowa: 0.5.0-stage1
partycja źródłowa: ota_0
wersja docelowa: 0.5.1-stage1
oczekiwana partycja docelowa: ota_1
```

Obraz `0.5.1-stage1` różni się od bootstrapu wyłącznie numerem wersji. Brak zmian funkcjonalnych jest celowy: test ma jednoznacznie zweryfikować transport, zapis do nieaktywnej partycji, restart, self-test i potwierdzenie obrazu.

`kFirmwareVersionPacked` pozostaje `0x0005`, ponieważ rejestr Modbus przechowuje wersję major/minor, a aktualizacja zmienia wyłącznie patch.

## 2. Niezmienniki

```text
RS-485 Modbus RTU: jedyny kanał produkcyjny
heartbeat Wi-Fi: best effort
OTA: operacja ręczna
aktualizacja: jeden węzeł naraz
sensor-node-2: bez zmian
```

Nie wykonywać merge ani nie oznaczać PR jako Ready for Review bez wyraźnego polecenia użytkownika.

## 3. Stan wejściowy wymagany przed testem

Na CM5:

```bash
wvc-servicectl ota-status sensor-node-1
wvc-servicectl nodes
cd /home/wentylacja/workshop-ventilation-controller
PYTHONPATH=src python3 -m ventilation_core.ctl sensors
```

Wymagane:

- `sensor-node-1` raportuje `0.5.0-stage1`, `ota_0`, `pending=false`, `state=idle`,
- `sensor-node-2` pozostaje na `0.4.0-stage1`,
- oba slave Modbus są `online`, `usable`, `measurement_valid=true`, `measurement_stale=false`,
- `worker_alive=true`, `worker_restarts=0`,
- `consecutive_failures=0` dla obu slave.

Historyczne liczniki `communication_errors`, `invalid_measurements` i `stale_measurements` nie muszą być równe zero. Kryterium testu stanowi brak nowych trwałych problemów oraz powrót `consecutive_failures` do zera.

## 4. Obraz testowy

Gałąź:

```text
agent/kamod-service-ota-stage1
```

Wersja:

```text
ESP app version: 0.5.1
heartbeat/status: 0.5.1-stage1
packed Modbus version: 0x0005
```

Do `ota-install` przekazywać wyłącznie obraz aplikacji:

```text
kamod_sen55_sensor_node.bin
```

Nie przekazywać bootloadera, tablicy partycji ani `ota_data_initial.bin`.

## 5. Umieszczenie obrazu na CM5

Docelowa ścieżka:

```text
/home/wentylacja/ota/kamod_sen55_sensor_node-0.5.1-stage1.bin
```

Po skopiowaniu:

```bash
mkdir -p /home/wentylacja/ota
ls -l /home/wentylacja/ota/kamod_sen55_sensor_node-0.5.1-stage1.bin
sha256sum /home/wentylacja/ota/kamod_sen55_sensor_node-0.5.1-stage1.bin
```

Rozmiar i SHA-256 muszą odpowiadać wartościom zweryfikowanym w artefakcie CI dla aktualnego HEAD.

## 6. Pierwszy transfer OTA

Przed uruchomieniem zapisać stan SENSOR BUS:

```bash
cd /home/wentylacja/workshop-ventilation-controller
PYTHONPATH=src python3 -m ventilation_core.ctl sensors \
  | tee /tmp/wvc-ota-0.5.1-sensors-before.json
```

Uruchomić:

```bash
wvc-servicectl ota-install \
  sensor-node-1 \
  /home/wentylacja/ota/kamod_sen55_sensor_node-0.5.1-stage1.bin \
  --wait-timeout 300
```

Klient czeka na stan terminalny. Oczekiwany wynik:

```text
state: succeeded
remote.firmware: 0.5.1-stage1
remote.partition: ota_1
remote.pending: false
remote.image_state: valid
remote.state: idle
```

Podczas restartu `sensor-node-1` dopuszczalne są krótkotrwałe błędy odczytu Modbus slave 1. `sensor-node-2` i cały worker SENSOR BUS muszą pozostać aktywne.

## 7. Walidacja po aktualizacji

```bash
wvc-servicectl ota-status sensor-node-1
wvc-servicectl nodes
cd /home/wentylacja/workshop-ventilation-controller
PYTHONPATH=src python3 -m ventilation_core.ctl sensors \
  | tee /tmp/wvc-ota-0.5.1-sensors-after.json
```

Wymagane:

- `sensor-node-1`: `0.5.1-stage1`, `ota_1`, `pending=false`, `image_state=valid`,
- nowy `boot_id`,
- `sensor-node-1` wraca do `online`,
- slave 1 wraca do `online`, `usable`, `valid`, `non-stale`, `consecutive_failures=0`,
- slave 2 pozostaje zdrowy i nie restartuje się,
- `worker_alive=true`, `worker_restarts=0`,
- `ventilation-core` nie jest restartowany przez OTA.

## 8. Zachowanie przy niepowodzeniu

Gdy `ota-install` zwróci:

- `failed` — nie ponawiać automatycznie; zapisać pełny JSON i `journalctl -u wvc-service-agent.service`,
- `uncertain` — wykonać `wvc-servicectl ota-status sensor-node-1` i nie odłączać zasilania,
- `rolled_back` — zachować logi, potwierdzić powrót do `0.5.0-stage1` na `ota_0`,
- timeout klienta — nie uruchamiać drugiej operacji przed sprawdzeniem `ota-status`.

Nie flashować wtedy `sensor-node-2`.

## 9. Zakres po pierwszym PASS

Po poprawnym `ota_0 -> ota_1` kolejne testy Stage 1 obejmą osobno:

1. przerwany transfer bez zmiany partycji startowej,
2. odrzucenie błędnego HMAC,
3. odrzucenie błędnego SHA-256,
4. kontrolowany rollback obrazu niespełniającego health-checku.

Dopiero po pełnym PASS wszystkich scenariuszy bootstrap OTA zostanie wgrany przez USB na `sensor-node-2`.
