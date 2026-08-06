# CM5 Wi-Fi Service — izolowana sieć serwisowa KAmod + SEN55

## 1. Status dokumentu

Dokument opisuje rzeczywiście wdrożoną konfigurację kanału serwisowego Wi-Fi dla dwóch węzłów KAmod ESP32 POW RS485 + SEN55.

Stan na: **2026-08-06**

- CM5 AP/DHCP/firewall: **PASS**,
- dwa fizyczne węzły KAmod w sieci: **PASS**,
- uwierzytelnione heartbeat HMAC obu węzłów: **PASS**,
- pełny zestaw testów przed merge, obejmujący fault injection i długi soak: **jeszcze niezamknięty**.

RS-485 Modbus RTU pozostaje jedynym kanałem produkcyjnym. Wi-Fi jest kanałem wyłącznie serwisowym.

## 2. Topologia

```text
sieć warsztatowa / komputer serwisowy
                 |
                 | Ethernet
                 v
       eth0: sieć administracyjna
       CM5 ventilation controller
       wlan0: 10.55.0.1/24
                 |
                 | WVC-SERVICE, 2,4 GHz, kanał 6
                 v
       sensor-node-1    sensor-node-2
       Modbus slave 1   Modbus slave 2
```

Parametry profilu NetworkManager:

| Parametr | Wartość |
|---|---|
| profil | `wvc-sensor-service` |
| SSID | `WVC-SERVICE` |
| interfejs | `wlan0` |
| tryb | AP |
| pasmo | 2,4 GHz (`bg`) |
| kanał | 6 |
| adres CM5 | `10.55.0.1/24` |
| uwierzytelnienie warstwy radiowej | brak — sieć otwarta |
| AP isolation | włączone |
| Wi-Fi power saving | wyłączone |
| IPv6 | wyłączone |
| trasa domyślna przez wlan0 | brak |
| forwarding IPv4/IPv6 | wyłączony |

## 3. Decyzja o otwartej sieci

`WVC-SERVICE` jest celowo otwartą siecią radiową. Nie używa WPA2-PSK ani wspólnego hasła.

Ta decyzja usuwa wspólny sekret Wi-Fi i upraszcza lokalny provisioning dwóch modułów. Nie oznacza rezygnacji z uwierzytelniania aplikacyjnego:

- każdy węzeł ma osobny losowy klucz HMAC 32 B,
- heartbeat jest podpisany HMAC-SHA256,
- CM5 stosuje allowlistę `node_id` i `key_id`,
- opcjonalne pinowanie MAC pozostaje dostępne,
- `boot_id + seq` chroni przed replay i odwróceniem kolejności,
- niepoprawny HMAC, nieznany węzeł lub replay są odrzucane.

Konsekwencja: ruch radiowy nie jest szyfrowany na warstwie Wi-Fi i może być obserwowany przez urządzenie w zasięgu. Heartbeat Stage 1 zawiera tylko diagnostykę i nie przenosi pomiarów PM/VOC/NOx ani poleceń sterujących.

## 4. DHCP bez routera i DNS

Dedykowany `dnsmasq` działa tylko na `wlan0`:

```text
zakres:       10.55.0.100–10.55.0.119
maska:        255.255.255.0
lease time:   12 h
router:       niewysyłany
DNS:          niewysyłany
DNS service:  wyłączony przez port=0
```

Węzły otrzymują adres lokalny, maskę, broadcast i parametry dzierżawy. Nie otrzymują bramy ani DNS.

Zwalidowane dzierżawy 2026-08-06:

| Węzeł | MAC | Adres DHCP |
|---|---|---|
| `sensor-node-1` | `88:13:BF:00:52:D0` | `10.55.0.106` |
| `sensor-node-2` | `88:13:BF:01:37:28` | `10.55.0.110` |

Adresy z puli DHCP nie są jeszcze kontraktem stałych rezerwacji.

## 5. Firewall i izolacja

Na CM5 obowiązuje defense in depth:

- DHCP na UDP/67 jest dostępny od `wlan0`,
- heartbeat jest przyjmowany wyłącznie na `10.55.0.1:45551/UDP`,
- SSH i pozostałe lokalne usługi CM5 są zablokowane od strony `wlan0`,
- forwarding `wlan0 -> eth0` i `eth0 -> wlan0` jest zablokowany,
- `net.ipv4.ip_forward = 0`,
- `net.ipv6.conf.all.forwarding = 0`,
- profil AP ma `ipv4.never-default yes`, brak gateway i brak DNS,
- AP isolation oddziela klientów radiowych.

Nie używamy `nmcli device wifi hotspot` ani `ipv4.method shared`, ponieważ mogłyby uruchomić routing/NAT.

## 6. Heartbeat Stage 1

Transport:

```text
KAmod -> UDP unicast -> 10.55.0.1:45551 -> wvc-service-heartbeat.service
```

Format:

```text
<JSON ASCII>\n<64 znaki hex HMAC-SHA256>
```

Częstotliwość: około 10 s. Węzeł jest uznawany za offline po 35 s bez poprawnego, uwierzytelnionego heartbeatu.

Heartbeat zawiera m.in.:

- `node_id`, `key_id`, MAC,
- firmware, uptime, reset reason,
- partycję i stan OTA,
- RSSI,
- stan SEN55 i liczniki błędów,
- gotowość RS-485,
- adres slave i pasywne liczniki zapytań Modbus.

Heartbeat nie zawiera wartości PM, temperatury, wilgotności, VOC ani NOx. Dane produkcyjne pozostają w Modbus RTU.

## 7. Pliki wdrożeniowe

```text
deploy/cm5/wifi/dnsmasq/wvc-sensor-service.conf
deploy/cm5/wifi/nftables/wvc-sensor-service.nft
deploy/cm5/wifi/systemd/wvc-sensor-dhcp.service
deploy/cm5/wifi/systemd/wvc-sensor-firewall.service
deploy/systemd/wvc-service-heartbeat.service
tools/install_cm5_wifi_service.sh
tools/validate_cm5_wifi_service.sh
tools/install_cm5_service_heartbeat.sh
tools/validate_cm5_service_heartbeat.sh
tools/provision_sensor_node_service.py
```

## 8. Instalacja AP

Wymagany jest działający dostęp administracyjny przez `eth0`.

Przygotowanie bez aktywacji:

```bash
cd /home/wentylacja/workshop-ventilation-controller
sudo bash tools/install_cm5_wifi_service.sh
```

Aktywacja:

```bash
sudo bash tools/install_cm5_wifi_service.sh --activate
```

Skrypt:

- instaluje konfigurację DHCP, nftables i systemd,
- tworzy lub aktualizuje profil `wvc-sensor-service`,
- usuwa odziedziczone ustawienie `802-11-wireless-security`,
- nie pyta o hasło,
- ustawia izolowany AP bez routingu,
- przy `--activate` uruchamia AP, firewall i DHCP,
- wykonuje walidację.

## 9. Provisioning węzła

Przykład dla pierwszego węzła:

```powershell
python tools\provision_sensor_node_service.py `
  --port COM9 `
  --modbus-address 1 `
  --node-id sensor-node-1 `
  --registry "$env:USERPROFILE\wvc-secrets\heartbeat-keys.json"
```

Dla drugiego węzła używa się `--modbus-address 2` oraz `--node-id sensor-node-2`.

NVS zawiera:

```text
device_config/modbus_addr
service_cfg/wifi_ssid
service_cfg/node_id
service_cfg/key_id
service_cfg/auth_key
```

Nie ma pola `wifi_psk`. Starszy, dodatkowy klucz `wifi_psk` zapisany wcześniej w NVS jest ignorowany przez aktualny firmware.

Rejestr kluczy jest sekretem. Nie wolno go commitować ani umieszczać w logach.

## 10. Instalacja odbiornika heartbeat

```bash
sudo bash tools/install_cm5_service_heartbeat.sh \
  /home/wentylacja/heartbeat-keys.json
```

Installer kopiuje rejestr jako `/etc/wvc-service-heartbeat/keys.json` z prawami `0600` i zawsze restartuje receiver. Restart jest wymagany, ponieważ proces ładuje rejestr tylko przy starcie.

## 11. Walidacja

AP:

```bash
sudo bash tools/validate_cm5_wifi_service.sh
```

Validator akceptuje oba równoważne wyniki NetworkManager dla wyłączonego oszczędzania energii:

```text
2
lub
disable
```

Receiver:

```bash
sudo bash tools/validate_cm5_service_heartbeat.sh
sudo journalctl -u wvc-service-heartbeat.service -f
```

Stan węzłów:

```bash
ls -l /run/wvc-service-heartbeat/nodes
python3 -m json.tool /run/wvc-service-heartbeat/nodes/sensor-node-1.json
python3 -m json.tool /run/wvc-service-heartbeat/nodes/sensor-node-2.json
```

## 12. Zwalidowany stan dwóch węzłów — 2026-08-06

| Pole | `sensor-node-1` | `sensor-node-2` |
|---|---:|---:|
| Modbus slave | 1 | 2 |
| source IP | `10.55.0.106` | `10.55.0.110` |
| RSSI w próbce | `-32 dBm` | `-57 dBm` |
| firmware | `0.4.0-stage1` | `0.4.0-stage1` |
| `sensor_state` | `running` | `running` |
| `rs485_ready` | `true` | `true` |
| błędy SEN55 | 0 | 0 |
| heartbeat HMAC | zaakceptowany | zaakceptowany |
| online | `true` | `true` |

Wynik bring-up dwóch węzłów i całego toru KAmod -> CM5: **PASS**.

## 13. Ograniczenia i testy pozostające przed merge

Checkpoint nie zamyka jeszcze następujących testów:

- kontrolowane wyłączenie AP i potwierdzenie ciągłości Modbus obu slave,
- restart DHCP oraz receivera podczas równoległego odczytu RS-485,
- odłączenie RS-485 i weryfikacja diagnostyki heartbeat,
- odłączenie SEN55 i weryfikacja stanu offline/stale,
- test fałszywego HMAC i replay na docelowym CM5,
- test braku dostępu do Ethernetu/SSH z klienta w `WVC-SERVICE`,
- minimum 30 min równoległego soak testu dwóch węzłów.

Do czasu ich wykonania PR pozostaje Draft i nie jest gotowy do merge.
