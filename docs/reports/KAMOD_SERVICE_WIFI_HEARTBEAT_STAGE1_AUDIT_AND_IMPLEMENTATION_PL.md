# KAmod Service Wi-Fi Heartbeat Stage 1 — audyt i implementacja

## 1. Punkt wyjścia

- repozytorium: `autoklinika/workshop-ventilation-controller`,
- bazowy HEAD `main`: `2ed28a8a5ba2e219493984732eca890ae0700cab`,
- gałąź: `agent/kamod-service-wifi-heartbeat-stage1`,
- Draft PR: #11,
- Draft PR #9 / AERO BUS: poza zakresem i bez zmian,
- RS-485 Modbus RTU: jedyny kanał produkcyjny,
- Wi-Fi: niezależny kanał wyłącznie serwisowy.

## 2. Audyt istniejącego firmware

Firmware zachowuje rozdział odpowiedzialności:

```text
app -> services/SEN55 -> I2C
app -> modbus -> UART2/RS-485
app -> diagnostics
app -> service_wifi
```

Potwierdzone niezmienniki:

- SEN55 nie zna protokołu Modbus,
- Modbus publikuje gotowy snapshot,
- Wi-Fi nie dostarcza pomiarów do logiki sterującej,
- Wi-Fi nie steruje DAC/AERO,
- błąd kanału Wi-Fi nie zatrzymuje SEN55 ani Modbus,
- firmware nie implementuje w Stage 1 OTA transportu, zdalnego restartu ani zdalnego provisioningu.

## 3. Kontrakt heartbeat

- transport: UDP unicast,
- kierunek: KAmod -> CM5,
- odbiornik: `10.55.0.1:45551`,
- okres: 10 s,
- początkowy jitter: 0–2 s,
- offline timeout: 35 s,
- protokół: `WVC-HB1`, schema 1,
- ramka: JSON + separator LF + HMAC-SHA256 hex.

Każdy węzeł ma osobny losowy klucz 32 B. CM5 sprawdza:

- subnet źródłowy,
- `node_id` i `key_id`,
- opcjonalnie MAC,
- HMAC,
- `boot_id + seq` przeciw replay.

Heartbeat nie zawiera PM, temperatury, wilgotności, VOC ani NOx.

## 4. Model sieci po walidacji sprzętowej

Podczas bring-up wykryto, że wspólne WPA2-PSK utrudniało odtwarzalny provisioning. Użytkownik podjął decyzję o usunięciu hasła z prywatnego AP.

Stan końcowy Stage 1:

- SSID `WVC-SERVICE`,
- otwarta warstwa Wi-Fi (`WIFI_AUTH_OPEN`),
- brak `wifi_psk` w aktualnym kontrakcie NVS,
- brak pytania o hasło w provisioningu,
- HMAC-SHA256 per node pozostaje wymagane,
- AP isolation pozostaje włączone,
- firewall dopuszcza tylko DHCP i jawnie otwarty port heartbeat,
- brak routera, DNS, NAT i forwardingu.

Ruch radiowy nie jest szyfrowany. Jest to zaakceptowane dla diagnostycznego, jednokierunkowego heartbeatu bez danych produkcyjnych i bez poleceń sterujących.

## 5. Provisioning

Aktualny obraz NVS zawiera:

```text
device_config/modbus_addr
service_cfg/wifi_ssid
service_cfg/node_id
service_cfg/key_id
service_cfg/auth_key
```

Narzędzie `tools/provision_sensor_node_service.py`:

- waliduje adres Modbus 1–247,
- waliduje `node_id`, `key_id`, SSID i opcjonalny MAC,
- generuje osobny klucz HMAC 32 B,
- aktualizuje lokalny rejestr CM5 atomowo,
- ustawia tryb pliku rejestru na `0600`,
- może generować obraz bez flashowania,
- nie pyta o hasło Wi-Fi i go nie zapisuje.

## 6. Receiver CM5

`wvc-service-heartbeat.service` jest osobnym procesem od `ventilation-core`.

Receiver:

- nasłuchuje tylko na `10.55.0.1:45551/UDP`,
- weryfikuje HMAC i replay,
- zapisuje stan runtime do `/run/wvc-service-heartbeat/nodes`,
- zapisuje stan replay do `/var/lib/wvc-service-heartbeat`,
- loguje przejścia online/offline i odrzucenia,
- nie aktualizuje `CoreState` ani logiki wentylacji.

Podczas wdrażania drugiego węzła wykryto operacyjny błąd installera: rejestr zawierał oba węzły, ale działający proces nadal miał starą allowlistę w pamięci. Installer został zmieniony tak, aby po każdej instalacji `keys.json` wykonywał restart receivera.

## 7. Walidator AP

Na docelowym NetworkManager wartość `802-11-wireless.powersave=2` jest prezentowana tekstowo jako `disable`. Stary validator zgłaszał fałszywy FAIL.

Validator akceptuje teraz oba równoważne warianty:

```text
2
disable
```

Dodatkowo sprawdza, że profil AP nie zawiera konfiguracji key management.

## 8. Walidacja programowa przed checkpointem

Zakres walidacji repozytorium:

- `python -m unittest discover -s tests -v`,
- `python -m compileall -q src tools tests`,
- `bash -n` dla skryptów wdrożeniowych,
- pełny build ESP-IDF 6.0.2 w workflow `Sensor node firmware`,
- kontrola, że firmware używa `WIFI_AUTH_OPEN`,
- kontrola braku `wifi_psk` i promptu WPA2,
- kontrola restartu receivera po zmianie rejestru.

Wynik workflow należy odczytać dla końcowego HEAD checkpointu.

## 9. Walidacja sprzętowa 2026-08-06

### 9.1. CM5

Potwierdzono:

- `wlan0` działa jako AP na `10.55.0.1/24`,
- profil `wvc-sensor-service` jest aktywny,
- DHCP działa na `10.55.0.100–10.55.0.119`,
- firewall i DHCP są enabled/active,
- receiver nasłuchuje na `10.55.0.1:45551`,
- AP nie wysyła routera ani DNS,
- otwarta autoryzacja radiowa działa.

### 9.2. sensor-node-1

```text
node_id: sensor-node-1
Modbus slave: 1
MAC: 88:13:BF:00:52:D0
DHCP: 10.55.0.106
firmware: 0.4.0-stage1
RSSI w próbce: -32 dBm
sensor_state: running
rs485_ready: true
błędy SEN55: 0
online: true
```

### 9.3. sensor-node-2

```text
node_id: sensor-node-2
Modbus slave: 2
MAC: 88:13:BF:01:37:28
DHCP: 10.55.0.110
firmware: 0.4.0-stage1
RSSI w próbce: -57 dBm
sensor_state: running
rs485_ready: true
błędy SEN55: 0
online: true
```

CM5 zaakceptował HMAC obu węzłów i utworzył dwa osobne pliki runtime.

Wynik bring-up dwóch fizycznych węzłów: **PASS**.

## 10. Zakres nadal otwarty przed merge

Nie wykonano jeszcze kompletnego testu wszystkich kryteriów fault-injection i soak:

- utrata AP podczas ciągłego odczytu obu slave,
- restart DHCP i receivera podczas pracy Modbus,
- odłączenie RS-485,
- odłączenie SEN55,
- fałszywy HMAC i replay na docelowym sprzęcie,
- próba dostępu do Ethernetu i SSH od strony AP,
- minimum 30 min pracy równoległej bez degradacji.

Dlatego PR #11 pozostaje Draft. Nie wykonywać merge ani Ready for Review bez jawnego polecenia użytkownika.

## 11. Wynik checkpointu

- implementacja kanału heartbeat: gotowa,
- otwarta sieć serwisowa: wdrożona,
- dwa węzły online: potwierdzone,
- HMAC per node: potwierdzone,
- poprawki operacyjne installera i validatora: wprowadzone,
- pełne kryteria przed merge: częściowo otwarte.
