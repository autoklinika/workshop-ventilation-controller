# CM5 Zigbee Stage 5 — walidacja Web API

Data walidacji: 2026-08-18
Gałąź: `agent/zigbee-stage1`

## Wynik

Stage 5 zakończony wynikiem PASS.

Potwierdzono:

- `ventilation-core.service` aktywny,
- `wvc-web-ui.service` aktywny,
- `mosquitto.service` aktywny,
- `zigbee2mqtt.service` aktywny,
- Web API działa na porcie `18091`,
- `GET /api/v1/zigbee` zwraca stan Zigbee z `ventilation-core`,
- dedykowany endpoint jest identyczny z `state.zigbee` z `GET /api/v1/state`,
- brak endpointów zapisu Zigbee,
- brak zmian w alertach i sterowaniu wentylacją.

## Dane z walidacji

### Nawiew

- rola: `supply`
- friendly name: `temp_nawiew`
- temperatura: `28.4 °C`
- bateria: `100 %`
- linkquality: `91`
- messages: `5`
- parse_errors: `0`

### Wywiew

- rola: `extract`
- friendly name: `temp_wywiew`
- temperatura: `28.3 °C`
- bateria: `100 %`
- linkquality: `87`
- messages: `6`
- parse_errors: `0`

## Kontrola źródła prawdy

Walidator potwierdził:

```text
GET /api/v1/zigbee == GET /api/v1/state -> state.zigbee
```

Wynik:

```text
dedicated endpoint == state.zigbee: PASS
```

Oznacza to, że Web API nie utrzymuje osobnej kopii stanu Zigbee. Jedynym źródłem prawdy pozostaje `ventilation-core`.

## Decyzja

Stage 5 jest zamknięty. Następny etap może udostępnić w Web V2 widok `Ustawienia -> Zigbee`, korzystający wyłącznie z `GET /api/v1/zigbee`.
