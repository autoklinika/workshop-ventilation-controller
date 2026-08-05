# CM5 Wi-Fi Service — prywatna sieć serwisowa węzłów KAmod + SEN55

## 1. Status dokumentu

Dokument jest autorytatywnym opisem wdrożonej konfiguracji prywatnego Wi-Fi CM5 dla węzłów pomiarowych KAmod ESP32 POW RS485 + SEN55.

Stan na: **2026-08-05**

Walidacja na docelowym CM5: **PASS**

Dokument rozwija decyzję D-043 z `DECISIONS_PL.md` oraz zasady opisane w `DUAL_CHANNEL_NODE_COMMUNICATION_PL.md`. Nie zastępuje kontraktu Modbus RTU SENSOR BUS.

## 2. Cel i granice odpowiedzialności

Każdy węzeł SEN55 + KAmod korzysta docelowo z dwóch niezależnych kanałów:

- **RS-485 Modbus RTU** — jedyny kanał produkcyjny dla pomiarów, jakości danych i podstawowej diagnostyki wykorzystywanej przez `ventilation-core`,
- **prywatne Wi-Fi CM5** — kanał wyłącznie serwisowy.

Wi-Fi ma służyć do:

- provisioningu,
- heartbeatów,
- odczytu wersji firmware,
- odczytu uptime, RSSI, temperatury ESP32 i przyczyny restartu,
- diagnostyki I²C i RS-485,
- pobierania lokalnego bufora zdarzeń,
- kontrolowanego restartu węzła,
- OTA A/B z walidacją i rollbackiem.

Wi-Fi nie może:

- zastępować pomiarów Modbus RTU,
- dostarczać danych produkcyjnych do logiki sterowania,
- sterować DAC lub wentylatorami,
- wykonywać poleceń Modbus wobec innych urządzeń,
- zapewniać węzłom dostępu do Internetu lub sieci warsztatowej,
- powodować zatrzymania RS-485 po utracie kanału radiowego.

Na obecnym etapie nie otwarto jeszcze żadnego portu aplikacyjnego dla heartbeatów, OTA ani diagnostyki. Zapora dopuszcza wyłącznie DHCP i diagnostyczny ICMP echo do CM5. Porty serwisowe zostaną dodane dopiero po zatwierdzeniu protokołu kanału serwisowego.

## 3. Zwalidowana platforma

Konfigurację uruchomiono na:

```text
Raspberry Pi Compute Module 5 Wireless, 4 GB RAM, 32 GB eMMC
Debian GNU/Linux 13 (trixie), 13.6
kernel 6.18.34+rpt-rpi-2712
NetworkManager 1.52.1
sterownik Wi-Fi brcmfmac 7.45.16.144
interfejs Ethernet: eth0
interfejs Wi-Fi: wlan0
```

Karta zgłasza obsługę:

- trybu AP,
- pasma 2,4 GHz,
- WPA2/CCMP.

Globalna domena regulacyjna była ustawiona na `PL: DFS-ETSI`. Punkt dostępowy został zwalidowany na kanale 6 w paśmie 2,4 GHz.

## 4. Zwalidowana topologia i adresacja

```text
Komputer serwisowy / sieć warsztatowa
                |
                | Ethernet
                v
       eth0: 192.168.1.64/24
        CM5 ventilation controller
       wlan0: 10.55.0.1/24
                |
                | prywatne Wi-Fi 2,4 GHz
                v
       KAmod/SEN55 node 1 i node 2
```

Parametry AP:

| Parametr | Wartość |
|---|---|
| profil NetworkManager | `wvc-sensor-service` |
| SSID | `WVC-SERVICE` |
| interfejs | `wlan0` |
| tryb | AP |
| pasmo | 2,4 GHz (`bg`) |
| kanał | 6 |
| szerokość potwierdzona | 20 MHz |
| adres CM5 | `10.55.0.1/24` |
| bezpieczeństwo | WPA2-PSK / RSN / CCMP |
| minimalna długość hasła projektowa | 16 znaków |
| PMF | optional |
| AP isolation | włączone |
| oszczędzanie energii Wi-Fi | wyłączone |
| autoconnect | włączone |
| priorytet autoconnect | 200 |
| IPv6 | wyłączone na profilu AP |

Hasło WPA2 jest przechowywane wyłącznie lokalnie przez NetworkManager na CM5. Nie wolno zapisywać go w repozytorium, dokumentacji, logach ani zgłoszeniach.

## 5. DHCP bez bramy i DNS

Dedykowany `dnsmasq` działa tylko jako serwer DHCP na `wlan0`:

```text
zakres:       10.55.0.100–10.55.0.119
maska:        255.255.255.0
lease time:   12 h
DNS:          niewysyłany
router:       niewysyłany
DNS service:  wyłączony przez port=0
```

Klient może poprosić w DHCP o opcję 3 (`router`) i 6 (`dns-server`), ale serwer świadomie ich nie wysyła. Węzeł otrzymuje wyłącznie adres, maskę, broadcast i parametry dzierżawy.

Dalszy etap powinien przypisać stałe rezerwacje DHCP po rzeczywistych adresach MAC węzłów, np.:

```text
sensor-zone-1: 10.55.0.11
sensor-zone-2: 10.55.0.12
```

Nie należy dodawać rezerwacji przed poznaniem i zapisaniem MAC obu modułów KAmod.

## 6. Routing i izolacja

Na CM5 obowiązuje:

```text
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0
```

Trasa domyślna prowadzi wyłącznie przez `eth0`. Profil AP ma:

```text
ipv4.method manual
ipv4.never-default yes
brak ipv4.gateway
brak ipv4.dns
ipv6.method disabled
```

Nie używamy skrótu:

```bash
nmcli device wifi hotspot
```

ani `ipv4.method shared`, ponieważ taki tryb może automatycznie uruchomić routing/NAT i udostępnić klientom uplink CM5.

`nftables` realizuje defense in depth:

- pozwala klientom uzyskać DHCP,
- pozwala na ICMP echo-request do `10.55.0.1`,
- blokuje SSH i wszystkie pozostałe lokalne usługi CM5 od strony `wlan0`,
- blokuje forwarding `wlan0 -> eth0`,
- blokuje forwarding `eth0 -> wlan0`,
- nie zmienia dostępu administracyjnego przez Ethernet.

AP isolation rozdziela klientów radiowych między sobą. Dwa węzły KAmod nie powinny bezpośrednio komunikować się na warstwie Wi-Fi.

## 7. Pliki wdrożeniowe

Repozytorium przechowuje bezsekretową, odtwarzalną konfigurację:

```text
deploy/cm5/wifi/dnsmasq/wvc-sensor-service.conf
deploy/cm5/wifi/nftables/wvc-sensor-service.nft
deploy/cm5/wifi/systemd/wvc-sensor-dhcp.service
deploy/cm5/wifi/systemd/wvc-sensor-firewall.service
tools/install_cm5_wifi_service.sh
tools/validate_cm5_wifi_service.sh
```

Na CM5 odpowiadają im:

```text
/etc/dnsmasq.d/wvc-sensor-service.conf
/etc/nftables.d/wvc-sensor-service.nft
/etc/systemd/system/wvc-sensor-dhcp.service
/etc/systemd/system/wvc-sensor-firewall.service
```

Profil NetworkManager jest generowany poleceniami `nmcli`, ponieważ musi zawierać lokalny sekret WPA2.

## 8. Instalacja odtwarzalna

Wymagania:

- aktywne połączenie administracyjne przez `eth0`,
- `NetworkManager`,
- `dnsmasq-base`,
- `nftables`,
- `iw`,
- działający i zarządzany przez NetworkManager interfejs `wlan0`.

Instalacja pakietów:

```bash
sudo apt update
sudo apt install -y dnsmasq-base nftables iw
```

Przygotowanie konfiguracji bez przełączania aktualnego Wi-Fi:

```bash
cd /home/wentylacja/workshop-ventilation-controller
sudo bash tools/install_cm5_wifi_service.sh
```

Skrypt:

- kopiuje pliki systemowe,
- sprawdza składnię `nftables` i `dnsmasq`,
- tworzy lub aktualizuje profil `wvc-sensor-service`,
- prosi interaktywnie o hasło WPA2, gdy nie jest jeszcze zapisane,
- nie ujawnia hasła,
- włącza autostart usług,
- bez `--activate` nie przełącza bieżącego `wlan0`.

Aktywacja jest dozwolona dopiero przy potwierdzonym dostępie przez Ethernet:

```bash
sudo bash tools/install_cm5_wifi_service.sh --activate
```

W trybie `--activate` skrypt wyłącza autoconnect aktualnie aktywnego, innego profilu Wi-Fi na `wlan0`, aktywuje AP, uruchamia zaporę i DHCP, a następnie wykonuje walidację.

## 9. Walidacja automatyczna

Uruchomienie:

```bash
cd /home/wentylacja/workshop-ventilation-controller
sudo bash tools/validate_cm5_wifi_service.sh
```

Skrypt sprawdza co najmniej:

- aktywny profil `wvc-sensor-service`,
- tryb AP,
- SSID, pasmo i kanał,
- AP isolation,
- wyłączony power saving,
- adres `10.55.0.1/24`,
- autostart i aktywność obu usług,
- obecność tabeli `inet wvc_sensor_service`,
- wyłączony forwarding IPv4 i IPv6,
- brak trasy domyślnej przez `wlan0`,
- nasłuch DHCP na UDP/67.

Skrypt nie odczytuje ani nie wypisuje hasła WPA2.

## 10. Walidacja sprzętowa wykonana 2026-08-05

Potwierdzono ręcznie na docelowym CM5:

1. `WVC-SERVICE` jest widoczny jako AP 2,4 GHz na kanale 6.
2. `wlan0` ma adres `10.55.0.1/24`.
3. `wvc-sensor-firewall.service` jest `enabled` i `active (exited)`.
4. `wvc-sensor-dhcp.service` jest `enabled` i `active (running)`.
5. `dnsmasq` nasłuchuje na UDP/67.
6. Telefon testowy uzyskał adres `10.55.0.108` przez pełną sekwencję:

```text
DHCPDISCOVER -> DHCPOFFER -> DHCPREQUEST -> DHCPACK
```

7. Odpowiedź DHCP nie zawierała opcji router ani DNS.
8. Telefon poprawnie zgłaszał brak Internetu.
9. `net.ipv4.ip_forward` i `net.ipv6.conf.all.forwarding` pozostały równe `0`.
10. Trasa domyślna po pełnym reboocie prowadziła wyłącznie przez `eth0`.
11. AP, zapora i DHCP uruchomiły się automatycznie po pełnym reboocie CM5.
12. Dostęp VS Code/SSH przez Ethernet pozostał aktywny.
13. Test funkcjonalny potwierdził, że prywatna sieć nie udostępnia Internetu ani sieci warsztatowej.

Wynik: **CM5 Wi-Fi Service Stage 1 — PASS**.

## 11. Oczekiwany stan operacyjny

```text
eth0:
  rola: administracja CM5 i sieć warsztatowa
  przykład zwalidowanego adresu: 192.168.1.64/24
  default route: tak

wlan0:
  rola: prywatny kanał serwisowy KAmod/SEN55
  adres: 10.55.0.1/24
  default route: nie
  Internet: nie
  dostęp do sieci warsztatowej: nie
  SSH do CM5: nie
  DHCP: tak
  ping do CM5: tak
```

Adres Ethernet `192.168.1.64` wynika z bieżącej dzierżawy w sieci warsztatowej i nie jest kontraktem stałego adresowania repozytorium.

## 12. Kontrola ręczna

```bash
echo "=== SERVICES ==="
systemctl is-enabled wvc-sensor-firewall.service
systemctl is-active wvc-sensor-firewall.service
systemctl is-enabled wvc-sensor-dhcp.service
systemctl is-active wvc-sensor-dhcp.service

echo "=== ACCESS POINT ==="
nmcli -f NAME,TYPE,DEVICE connection show --active
iw dev wlan0 info
ip -br addr show wlan0

echo "=== FIREWALL ==="
sudo nft list table inet wvc_sensor_service

echo "=== ISOLATION ==="
sysctl net.ipv4.ip_forward
sysctl net.ipv6.conf.all.forwarding
ip route

echo "=== DHCP ==="
sudo ss -lunp | grep ':67' || true
sudo cat /var/lib/misc/dnsmasq-wvc.leases
```

## 13. Diagnostyka

Logi DHCP:

```bash
sudo journalctl -u wvc-sensor-dhcp.service --since "-10 minutes" --no-pager
```

Logi NetworkManager:

```bash
sudo journalctl -u NetworkManager --since "-10 minutes" --no-pager
```

Stan profilu AP bez ujawniania PSK:

```bash
nmcli -f \
connection.id,connection.autoconnect,connection.autoconnect-priority,\
802-11-wireless.mode,802-11-wireless.ssid,802-11-wireless.band,\
802-11-wireless.channel,802-11-wireless.ap-isolation,\
802-11-wireless.powersave,802-11-wireless-security.key-mgmt,\
ipv4.method,ipv4.addresses,ipv4.never-default,ipv6.method \
connection show wvc-sensor-service
```

Kontrola długości zapisanego PSK bez wypisywania wartości:

```bash
sudo nmcli --show-secrets \
  -g 802-11-wireless-security.psk \
  connection show wvc-sensor-service |
awk 'length($0) {print "PSK zapisany, liczba znaków:", length($0); found=1}
     END {if (!found) print "BŁĄD: PSK nie został zapisany"}'
```

## 14. Rollback i odzyskanie dostępu

Rollback należy wykonywać lokalnie lub przez działające `eth0`.

Zatrzymanie prywatnego AP:

```bash
sudo systemctl stop wvc-sensor-dhcp.service
sudo systemctl stop wvc-sensor-firewall.service
sudo nmcli connection down wvc-sensor-service
```

Ponowne uruchomienie wcześniejszego profilu klienta Wi-Fi:

```bash
nmcli connection show
sudo nmcli connection modify "<nazwa-poprzedniego-profilu>" connection.autoconnect yes
sudo nmcli connection up "<nazwa-poprzedniego-profilu>"
```

Pełne usunięcie konfiguracji jest operacją serwisową i nie powinno być wykonywane podczas normalnej eksploatacji.

## 15. Niezmienniki dla dalszej implementacji firmware

Podczas dodawania Wi-Fi do firmware KAmod obowiązują następujące reguły:

1. RS-485 Modbus RTU pozostaje aktywny i niezależny od stanu Wi-Fi.
2. Start, reconnect i OTA Wi-Fi nie mogą blokować obsługi Modbus.
3. Heartbeat Wi-Fi nie jest źródłem pomiarów dla automatyki.
4. Brak Wi-Fi nie może oznaczać awarii pomiarowej, jeżeli Modbus działa.
5. Brak Modbus przy działającym Wi-Fi może wzbogacić diagnozę o prawdopodobną awarię magistrali.
6. Żadna komenda Wi-Fi nie może bezpośrednio sterować DAC, wentylatorami ani AERO.
7. Zdalny restart musi być uwierzytelniony i audytowany.
8. OTA musi używać istniejącego układu A/B, walidacji obrazu i rollbacku.
9. Dane uwierzytelniające nie trafiają do kodu źródłowego ani logów.
10. Port w zaporze CM5 otwieramy dopiero po zdefiniowaniu konkretnego protokołu, kierunku ruchu i uwierzytelnienia.

## 16. Następny etap

Następnym etapem nie jest rozszerzanie sieci CM5, lecz zaprojektowanie i wdrożenie kanału serwisowego w firmware dwóch KAmod. Przed implementacją należy:

- sprawdzić aktualny HEAD `main`,
- przeczytać ten dokument, `DUAL_CHANNEL_NODE_COMMUNICATION_PL.md` i dokumentację firmware Stage 2B,
- potwierdzić aktualną strukturę firmware i konfigurację partycji OTA,
- zidentyfikować MAC obu KAmod,
- ustalić protokół heartbeatów i provisioningu,
- zdefiniować uwierzytelnienie,
- przygotować osobny etap i gałąź,
- zachować pełną zgodność istniejącego Modbus RTU.

Nie należy mieszać implementacji kanału serwisowego KAmod z gałęzią AERO BUS ani z Draft PR #9.
