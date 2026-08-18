# Zigbee — Stage 2: instalacja stosu na CM5

## Wynik preflight

Preflight na CM5 zakończył się poprawnie:

- Debian 13 (trixie), aarch64,
- 4 GB RAM, około 21 GB wolnego miejsca,
- koordynator USB dostępny przez stabilną ścieżkę `/dev/serial/by-id/...`,
- `/dev/ttyUSB0` należy do grupy `dialout`,
- użytkownik `wentylacja` należy do `dialout`,
- port szeregowy nie jest zajęty,
- `ventilation-core.service` i `wvc-web-ui.service` są aktywne,
- port Web GUI 18091 pozostaje aktywny,
- Mosquitto, Node.js i Zigbee2MQTT nie były wcześniej zainstalowane.

## Wersje przypięte dla Stage 2

- Zigbee2MQTT: `2.13.0`
- Node.js: `24.x`
- pnpm: `10.18.3`
- Mosquitto: pakiet z repozytorium Debian 13

Zigbee2MQTT 2.13.0 nie obsługuje już Node.js 20. Dlatego nie używamy pakietu Node.js 20 z Debian 13 i instalujemy Node.js 24 z repozytorium NodeSource.

## Zasada Stage 2

Stage 2 instaluje tylko wymagane oprogramowanie i lokalny broker. **Nie uruchamia jeszcze sieci Zigbee.**

Po instalacji:

- Mosquitto działa wyłącznie na `127.0.0.1:1883`,
- wykonywany jest lokalny test publish/subscribe MQTT,
- Zigbee2MQTT jest zainstalowany w `/opt/zigbee2mqtt`,
- dane Zigbee2MQTT będą przechowywane w `/var/lib/zigbee2mqtt`,
- jednostka `zigbee2mqtt.service` jest zainstalowana, ale wyłączona,
- jednostka ma `ConditionPathExists=/var/lib/zigbee2mqtt/configuration.yaml`,
- `configuration.yaml` nie jest tworzony w Stage 2.

Dzięki temu przypadkowe uruchomienie usługi nie utworzy sieci Zigbee przed kontrolowanym testem adaptera i wyborem ustawień sieci.

## Instalacja

Po zsynchronizowaniu gałęzi:

```bash
sudo bash tools/install_cm5_zigbee_stack.sh
```

Skrypt przed instalacją wymaga aktywnych usług `ventilation-core.service` i `wvc-web-ui.service`. Po instalacji ponownie raportuje ich niezależny stan przez standardowe narzędzia systemowe.

## Następny etap

Stage 3 utworzy minimalną, kontrolowaną konfigurację Zigbee2MQTT, potwierdzi typ radia/firmware koordynatora i dopiero wtedy uruchomi koordynator. Parowanie urządzeń pozostanie zamknięte do osobnego testu.
