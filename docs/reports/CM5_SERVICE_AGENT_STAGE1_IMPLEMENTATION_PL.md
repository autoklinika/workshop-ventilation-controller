# CM5 Service Agent Stage 1 — implementacja

Data rozpoczęcia: 2026-08-06

Repozytorium: `autoklinika/workshop-ventilation-controller`

Gałąź:

```text
agent/cm5-service-agent-stage1
```

Baza:

```text
5e6c45804ec001090401c80faf89620c7d6004a3
```

## 1. Cel

Zastąpić wąski odbiornik heartbeat docelową usługą systemową płaszczyzny serwisowej CM5, bez mieszania jej z produkcyjnym sterowaniem wentylacją.

Nowa usługa:

```text
wvc-service-agent.service
```

pozostaje niezależna od:

- `ventilation-core.service`,
- SENSOR BUS Modbus RTU,
- AERO BUS,
- DAC DFR0971,
- logiki trybów i nastaw wentylatorów.

## 2. Architektura Stage 1

```text
KAmod #1 / KAmod #2
        |
        | UDP/45551, HMAC-SHA256, boot_id + seq
        v
wvc-service-agent.service
        |-- odbiór i uwierzytelnianie heartbeat
        |-- ochrona replay
        |-- nadzór online/offline
        |-- diagnostyka AP/DHCP/firewalla
        |-- normalizowany stan węzłów
        `-- lokalne API Unix socket
                    |
                    v
/run/wvc-service-agent/service-agent.sock
                    |
                    v
              wvc-servicectl
```

Produkcyny kanał pomiarowy pozostaje bez zmian:

```text
CM5 -> /dev/ttyAMA0 -> DFR0845 -> Modbus RTU -> slave 1 i 2
```

Heartbeat nie zastępuje Modbus RTU i nie jest źródłem pomiarów SEN55 dla sterowania.

## 3. Zachowane mechanizmy bezpieczeństwa

Agent wykorzystuje istniejący, zwalidowany kod:

- rejestr kluczy HMAC per node,
- allowlistę `node_id` i `key_id`,
- opcjonalne pinowanie MAC,
- walidację źródła `10.55.0.0/24`,
- HMAC-SHA256,
- `boot_id + seq`,
- trwałą ochronę replay,
- próg offline 35 s,
- atomowy zapis snapshotów runtime.

Trwały stan replay pozostaje w:

```text
/var/lib/wvc-service-heartbeat
```

Dzięki temu przejście z receivera do agenta nie zeruje historii zaakceptowanych sesji.

Klucze pozostają w:

```text
/etc/wvc-service-heartbeat/keys.json
```

Proces `ventilation-core` nie otrzymuje dostępu do kluczy HMAC.

## 4. Lokalne API

Socket:

```text
/run/wvc-service-agent/service-agent.sock
```

Uprawnienia:

```text
0660
```

Komendy:

```bash
wvc-servicectl status
wvc-servicectl nodes
wvc-servicectl network
```

API jest lokalne i read-only. Stage 1 nie zawiera poleceń kierowanych do KAmod.

## 5. Model stanu

Agent publikuje osobno:

### Stan procesu

- gotowość agenta,
- czas startu,
- adres UDP,
- ścieżkę socketu,
- liczbę zarejestrowanych i aktywnych węzłów.

### Stan sieci serwisowej

- aktywny profil AP `wvc-sensor-service`,
- stan interfejsu `wlan0`,
- obecność `10.55.0.1`,
- stan `wvc-sensor-dhcp.service`,
- stan `wvc-sensor-firewall.service`.

### Stan węzła

- `node_id`, `key_id`, online/offline,
- adres źródłowy i MAC,
- firmware, uptime i RSSI,
- stan SEN55 i wiek pomiaru,
- gotowość RS-485,
- adres Modbus i pasywne liczniki zapytań,
- stan partycji OTA wyłącznie diagnostycznie,
- pełny uwierzytelniony heartbeat do diagnostyki lokalnej.

## 6. Jednostka systemd

Nowa jednostka:

```text
deploy/systemd/wvc-service-agent.service
```

Najważniejsze właściwości:

- `Wants`, ale brak zależności od `ventilation-core`,
- konflikt z legacy `wvc-service-heartbeat.service`, aby dwa procesy nie zajęły UDP/45551,
- `NoNewPrivileges=true`,
- `ProtectSystem=strict`,
- `ProtectHome=read-only`,
- `RestrictAddressFamilies=AF_INET AF_UNIX`,
- prywatny katalog runtime,
- automatyczny restart po nieoczekiwanym zakończeniu.

Awaria agenta lub Wi-Fi nie może zatrzymać `ventilation-core`.

## 7. Instalacja na CM5

Po pobraniu gałęzi:

```bash
cd /home/wentylacja/workshop-ventilation-controller
sudo bash tools/install_cm5_service_agent.sh \
  /home/wentylacja/heartbeat-keys.json
```

Installer:

1. sprawdza rejestr kluczy,
2. instaluje klucze z prawami `0600`,
3. instaluje jednostkę systemd i regułę nftables,
4. instaluje `/usr/local/bin/wvc-servicectl`,
5. zatrzymuje i wyłącza legacy receiver,
6. uruchamia `wvc-service-agent.service`,
7. nie restartuje i nie zatrzymuje `ventilation-core`.

## 8. Walidacja

```bash
sudo bash tools/validate_cm5_service_agent.sh
wvc-servicectl status
wvc-servicectl nodes
wvc-servicectl network
```

Kryteria pierwszego uruchomienia:

- `wvc-service-agent.service` active,
- legacy receiver inactive,
- UDP `10.55.0.1:45551` zajęty przez agent,
- socket Unix istnieje i ma `0660`,
- AP, DHCP i firewall raportują stan,
- oba KAmod pojawiają się w `nodes`,
- utrata heartbeat jednego węzła nie wpływa na drugi,
- restart agenta nie wpływa na Modbus RTU ani DAC,
- brak nowych portów TCP od strony `wlan0`.

## 9. Zakres świadomie odłożony

Stage 1 nie dodaje:

- integracji stanu agenta z `CoreState`,
- GUI,
- MQTT,
- OTA,
- zdalnego restartu,
- zdalnego provisioningu,
- konfiguracji Wi-Fi przez API,
- sterowania wentylacją przez Wi-Fi,
- przesyłania produkcyjnych pomiarów SEN55 przez Wi-Fi.

Integracja tylko do odczytu z `ventilation-core` będzie osobnym checkpointem po walidacji fizycznej usługi systemowej.

## 10. Stan repozytorium

Nie wykonywać merge ani oznaczenia Ready for Review bez wyraźnego polecenia użytkownika. PR #9 AERO BUS oraz PR #11 pozostają bez zmian.
