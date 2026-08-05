# KAmod Service Wi-Fi Heartbeat Stage 1 — audyt, architektura i implementacja

## 1. Punkt wyjścia

- repozytorium: `autoklinika/workshop-ventilation-controller`,
- rzeczywisty HEAD `main` przy rozpoczęciu: `2ed28a8a5ba2e219493984732eca890ae0700cab`,
- gałąź implementacyjna: `agent/kamod-service-wifi-heartbeat-stage1`,
- Draft PR #9 / gałąź AERO BUS: poza zakresem i bez zmian,
- RS-485 Modbus RTU: jedyny kanał produkcyjny,
- Wi-Fi: wyłącznie niezależny kanał serwisowy.

## 2. Wynik audytu firmware Stage 2B

### 2.1. Architektura ESP-IDF

Firmware jest prawidłowo rozdzielony na komponenty:

```text
main -> app
         -> services -> sen55 -> drivers/I2C
         -> modbus -> esp-modbus -> UART2/RS-485
         -> diagnostics
         -> platform
         -> logging
         -> config/NVS
```

`main.cpp` nie zawiera logiki protokołów. SEN55 nie zna Modbus, a Modbus koduje gotowy snapshot pomiaru i diagnostyki.

### 2.2. SEN55 i diagnostyka

- I²C 100 kHz, SDA GPIO33, SCL GPIO32, adres SEN55 `0x69`,
- odczyt ośmiu pól oraz CRC-8 Sensirion,
- poll 200 ms,
- trzy kolejne błędy powodują przejście do offline,
- ponowna detekcja co 5 s,
- pierwszy pomiar: timeout 10 s,
- stale po 5 s,
- liczniki detekcji, komunikacji, CRC i poprawnych pomiarów,
- ostatni błąd i czas ostatniego sukcesu.

### 2.3. Modbus RTU

- ESP-Modbus 2.1.2,
- slave, UART2, half-duplex,
- TX GPIO25, RX GPIO27, DE/RE GPIO26,
- 19200 bit/s, 8N1,
- wyłącznie FC04 Read Input Registers,
- mapa v1, 19 rejestrów,
- aktualizacja pod blokadą kontrolera,
- adres urządzenia z `device_config/modbus_addr` w NVS,
- produkcyjne adresy `1` i `2`,
- brak rejestrów zapisywalnych.

Brakujący element dla planowanego heartbeatu: firmware nie liczył poprawnych odczytów Modbus ani wieku ostatniego żądania. Stage 1 dodaje pasywny monitor zdarzeń `MB_EVENT_INPUT_REG_RD`; nie zmienia obsługi ramki ani mapy rejestrów.

### 2.4. OTA, watchdog i pamięć konfiguracji

- flash 4 MB,
- `ota_0` i `ota_1` po `0x1D0000`,
- `otadata`, NVS i coredump,
- rollback bootloadera włączony,
- obraz pending jest potwierdzany po 30 s, gdy GPIO, I²C i RS-485 są gotowe,
- Task WDT: 10 s,
- panic: log i reboot,
- firmware Stage 1 nie implementuje transportu OTA, restartu ani polecenia zdalnego,
- Modbus address i poświadczenia serwisowe są lokalne w NVS.

### 2.5. Walidacja Stage 2B

- dwa węzły z tym samym firmware i osobnymi adresami NVS,
- 800/800 poprawnych cykli odczytu,
- 0 timeoutów,
- 0 błędów protokołu,
- 0 błędów wersji mapy,
- 0 próbek invalid/stale,
- stabilność po wprowadzeniu 10 ms odstępu między węzłami,
- hostowe testy mapy i pełny build ESP-IDF 6.0.2: PASS.

### 2.6. Drift dokumentacji

`docs/MODBUS_MAP_PL.md` nadal opisywał Stage 2A, stały adres `1` i firmware `0x0002`. Został zaktualizowany do rzeczywistego kontraktu Stage 2B i wersji firmware Stage 1.

## 3. Architektura kanału serwisowego Stage 1

### 3.1. Transport i role

- transport: UDP unicast,
- kierunek: wyłącznie KAmod -> CM5,
- KAmod: klient/stacja Wi-Fi i nadawca heartbeatów,
- CM5: serwer/odbiornik,
- adres odbiornika: `10.55.0.1`,
- port: UDP `45551`,
- węzeł nie otwiera żadnego portu aplikacyjnego,
- brak TCP, HTTP, MQTT, SSH i mDNS w Stage 1.

UDP wybrano, ponieważ heartbeat jest samodzielnym, okresowym snapshotem. Utrata pojedynczego datagramu nie tworzy kolejki, nie wymaga sesji ani utrzymywania połączenia i nie może zablokować produkcyjnej pętli.

### 3.2. Format ramki

```text
<ASCII JSON payload>\n<64 lowercase hex characters HMAC-SHA256>
```

HMAC jest liczony po dokładnych bajtach JSON przed separatorem. Maksymalny datagram odbiornika: 2048 B.

Pola schematu `WVC-HB1`, wersja `1`:

- `protocol`, `schema`,
- `node_id`, `key_id`, `mac`,
- `boot_id`, `seq`,
- `firmware`, `uptime_s`, `reset_reason`,
- `ota_partition`, `ota_pending`,
- `wifi_rssi_dbm`,
- `sensor_state`, `measurement_age_ms`, `sensor_last_error`,
- liczniki detekcji, komunikacji, CRC i poprawnych pomiarów,
- `rs485_ready`, `modbus_slave`, `modbus_monitor_ready`,
- `modbus_requests_total`, `modbus_requests_last_60s`,
- `last_modbus_request_age_ms`, `modbus_service_errors`.

Heartbeat świadomie nie zawiera PM, temperatury, wilgotności, VOC ani NOx. Dane produkcyjne pozostają wyłącznie w Modbus RTU.

### 3.3. Częstotliwość i stan online

- heartbeat co 10 s,
- losowy startowy jitter 0–2 s,
- CM5 uznaje węzeł za offline po 35 s bez poprawnego, uwierzytelnionego heartbeatu,
- utrata datagramu nie wymaga retransmisji,
- `seq` rośnie w ramach jednego `boot_id`.

### 3.4. Identyfikacja i uwierzytelnienie

- `node_id`: stabilna nazwa logiczna, np. `sensor-zone-1`,
- MAC: atrybut identyfikacyjny i opcjonalnie pinowany w rejestrze CM5,
- MAC nie jest samodzielnym mechanizmem bezpieczeństwa,
- `key_id`: identyfikator wersji klucza,
- klucz: losowe 32 B per węzeł,
- HMAC-SHA256: uwierzytelnienie i integralność,
- WPA2-PSK: ochrona warstwy radiowej,
- `boot_id + seq`: ochrona przed replay i odwróceniem kolejności,
- CM5 przechowuje bieżącą oraz zamknięte sesje boot w `/var/lib/wvc-service-heartbeat`.

Poświadczenia nie są logowane. Rejestr kluczy na CM5 ma tryb `0600`. W repozytorium jest tylko przykład z wartością zastępczą.

### 3.5. Reconnect i backoff

- 1, 2, 4, 8, 16, 32, 60 s,
- limit 60 s,
- jitter 0–500 ms,
- reset backoff po otrzymaniu adresu DHCP,
- brak bramy i DNS nie jest traktowany jako błąd,
- błąd inicjalizacji lub wysyłki Wi-Fi jest tylko ostrzeżeniem kanału serwisowego.

### 3.6. Izolacja tasków

- główny task aplikacji: core 0,
- Wi-Fi driver: core 1,
- lwIP TCP/IP: core 1,
- task heartbeat: core 1, priorytet 2,
- Modbus monitor: blokujący task zdarzeń, nie ingeruje w obsługę ramek,
- snapshot między produkcją a Wi-Fi jest krótką kopią pod spinlockiem,
- task Wi-Fi nie posiada referencji do sterownika SEN55, rejestrów Modbus ani DAC/AERO,
- task Wi-Fi nie jest klientem Task WDT; jego zawieszenie nie może restartować sprawnej ścieżki produkcyjnej.

### 3.7. CM5 receiver

Osobny proces i unit `wvc-service-heartbeat.service`:

- nie jest częścią `ventilation-core.service`,
- nie importuje ani nie aktualizuje `VentilationService` lub `CoreState`,
- weryfikuje subnet, schema, allowlist, HMAC, MAC i replay,
- zapisuje atomowy stan per node do `/run/wvc-service-heartbeat/nodes/*.json`,
- zapisuje replay state do `/var/lib/wvc-service-heartbeat`,
- loguje przejścia online/offline oraz odrzucenia,
- awaria odbiornika nie wpływa na SENSOR BUS, AERO BUS ani DAC.

### 3.8. Minimalna zmiana nftables

Jedyna nowa reguła input przed końcowym drop:

```nft
iifname "wlan0" ip daddr 10.55.0.1 udp dport 45551 accept
```

Forwarding pozostaje zablokowany. SSH i wszystkie inne porty pozostają niedostępne od `wlan0`.

## 4. Provisioning lokalny Stage 1

`tools/provision_sensor_node_service.py` tworzy jeden obraz NVS zawierający:

```text
device_config/modbus_addr
service_cfg/wifi_ssid
service_cfg/wifi_psk
service_cfg/node_id
service_cfg/key_id
service_cfg/auth_key
```

Narzędzie:

- pobiera WPA2 PSK przez `getpass`,
- generuje osobny 32-bajtowy klucz HMAC,
- nie wypisuje sekretów,
- zapisuje rejestr CM5 z prawami `0600`,
- opcjonalnie pinuje rzeczywisty MAC,
- może wygenerować obraz bez flashowania,
- ostrzega przez sam zakres operacji: zapis NVS zastępuje dotychczasową zawartość partycji, dlatego zawiera również adres Modbus.

Nie jest to provisioning sieciowy. Zdalna zmiana konfiguracji pozostaje poza Stage 1.

## 5. Plan etapów

1. **Heartbeat Stage 1 — ten zakres**: STA do WVC-SERVICE, UDP/HMAC, diagnostyka, receiver CM5, nftables.
2. **Provisioning Stage 2**: uwierzytelniona i jawnie autoryzowana zmiana konfiguracji; osobny protokół i threat model.
3. **Log retrieval Stage 3**: limitowany bufor zdarzeń, kontrola rozmiaru i rate limit.
4. **Remote restart Stage 4**: osobna autoryzacja polecenia, nonce, audit log, brak restartu produkcji od błędu Wi-Fi.
5. **OTA Stage 5**: podpisany obraz, A/B, walidacja, rollback, kontrola wersji i zasilania.

Stage 1 nie implementuje etapów 2–5.

## 6. Kryteria PASS

### 6.1. Programowe

- pełny build ESP-IDF 6.0.2,
- istniejące testy mapy Modbus PASS,
- testy receivera: poprawny HMAC, zły HMAC, subnet, MAC pinning, replay, zamknięty boot, offline timeout,
- test rozdzielenia systemd i minimalnej reguły nftables,
- brak sekretów w repozytorium,
- brak TCP/app listenera na węźle,
- receiver nie jest połączony z `ventilation-core`.

### 6.2. Sprzętowe — dwa węzły

- oba węzły łączą się z `WVC-SERVICE` i dostają DHCP bez router/DNS,
- poprawne `node_id`, MAC, firmware, slave i RSSI w CM5,
- heartbeat co około 10 s,
- poprawny wzrost `seq`, uptime i liczników Modbus,
- odłączenie AP/wyłączenie `wlan0`: nieprzerwany odczyt obu slave po RS-485, pomiary SEN55 i brak resetu WDT,
- restart DHCP/receivera: Modbus bez przerwy; heartbeat wraca automatycznie,
- odłączenie RS-485: Wi-Fi i SEN55 działają; heartbeat zgłasza brak aktywności Modbus,
- odłączenie SEN55: Modbus nadal odpowiada diagnostyką; heartbeat zgłasza offline/stale,
- fałszywy HMAC i replay są odrzucane,
- brak dostępu węzła do Internetu, Ethernetu i SSH CM5,
- test równoległy minimum 30 min bez degradacji dotychczasowego wyniku Stage 2B.

## 7. Pliki implementacji

### Firmware

- `firmware/sensor-node/components/service_wifi/**`,
- `firmware/sensor-node/components/config/include/config/service_credentials.hpp`,
- `firmware/sensor-node/components/config/src/service_credentials.cpp`,
- `firmware/sensor-node/components/app/include/app/application.hpp`,
- `firmware/sensor-node/components/app/src/application.cpp`,
- `firmware/sensor-node/components/modbus/include/modbus/modbus_rtu_slave.hpp`,
- `firmware/sensor-node/components/modbus/src/modbus_rtu_slave.cpp`,
- odpowiednie `CMakeLists.txt`, `firmware_config.hpp`, `sdkconfig.defaults`.

### CM5 i narzędzia

- `src/ventilation_core/service_heartbeat.py`,
- `deploy/systemd/wvc-service-heartbeat.service`,
- `deploy/cm5/wifi/nftables/wvc-sensor-service.nft`,
- `deploy/cm5/wifi/heartbeat/heartbeat-keys.example.json`,
- `tools/provision_sensor_node_service.py`,
- `tools/install_cm5_service_heartbeat.sh`,
- `tools/validate_cm5_service_heartbeat.sh`,
- `tests/test_service_heartbeat.py`,
- `tests/test_service_heartbeat_systemd.py`,
- workflowy i `.gitignore`.

## 8. Stan po implementacji programowej

- lokalne testy receivera i deploymentu: `9/9 PASS`,
- `compileall`: PASS,
- składnia obu skryptów shell: PASS,
- pełny build ESP-IDF i testy GitHub Actions: wymagane po push,
- walidacja na docelowych dwóch KAmod i CM5: wymagana przed merge,
- brak merge i brak zmiany statusu Draft PR #9.
