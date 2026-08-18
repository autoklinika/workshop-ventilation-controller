# Zigbee Stage 4 — integracja MQTT z ventilation-core

## Cel

Stage 4 przenosi odczyt dwóch sparowanych czujników SONOFF SNZB-02LD do
`ventilation-core`. GUI ani inne klienty nie komunikują się bezpośrednio z
Zigbee2MQTT.

Przepływ danych:

```text
SNZB-02LD
  -> GW90-POE-Ti / CC2652P
  -> Zigbee2MQTT
  -> Mosquitto 127.0.0.1:1883
  -> ventilation-core
  -> CoreState / API
```

## Urządzenia produkcyjne tego pilota

- `supply`: `temp_nawiew`, IEEE `0xa4c13810e66fffff`
- `extract`: `temp_wywiew`, IEEE `0xa4c13810bdedffff`

Core subskrybuje wyłącznie ich topiki danych i availability:

- `zigbee2mqtt/temp_nawiew`
- `zigbee2mqtt/temp_nawiew/availability`
- `zigbee2mqtt/temp_wywiew`
- `zigbee2mqtt/temp_wywiew/availability`

## Dane wystawiane przez CoreState

`state.zigbee` zawiera stan połączenia z lokalnym brokerem oraz dla każdego
czujnika:

- rolę i `friendly_name`,
- IEEE i topic,
- temperaturę w °C,
- baterię w %,
- `linkquality`,
- `last_seen`,
- czas ostatniej wiadomości odebranej przez core,
- stan availability,
- liczniki wiadomości i błędów parsowania.

Pola nieobecne w komunikacie MQTT nie kasują ostatniej poprawnej wartości.

## Zasady bezpieczeństwa

Stage 4 jest read-only. Nie otwiera `permit_join`, nie steruje urządzeniami
Zigbee i nie zmienia logiki wentylatorów.

Awaria Mosquitto, Zigbee2MQTT lub klienta MQTT nie może zatrzymać istniejącego
sterowania wentylacją. Stan błędu jest raportowany w `state.zigbee`; alerty
Zigbee pozostają poza zakresem tego etapu.

## Wdrożenie na CM5

Po synchronizacji gałęzi:

```bash
sudo bash tools/install_cm5_zigbee_core_stage4.sh
```

Skrypt przed restartem core wymaga:

- aktywnego `ventilation-core`, Mosquitto i Zigbee2MQTT,
- `STOP` i 0 V / 0 V,
- potwierdzonego stanu wyjść,
- `permit_join=false`.

Następnie instaluje systemowy `python3-paho-mqtt`, wykonuje test Stage 4,
instaluje unit `ventilation-core.service`, restartuje core i sprawdza połączenie
MQTT oraz mapowanie obu czujników.
