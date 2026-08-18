# Zigbee Stage 5 — dedykowane API Web dla stanu Zigbee

## Cel

Stage 5 dodaje w warstwie Web V2 osobny, tylko-do-odczytu endpoint dla danych Zigbee pochodzących z `ventilation-core`.

Przepływ pozostaje zgodny z architekturą:

```text
SNZB-02LD
  -> Zigbee2MQTT
  -> Mosquitto
  -> ventilation-core
  -> Web API
  -> później GUI Ustawienia -> Zigbee
```

Przeglądarka nie komunikuje się z MQTT ani Zigbee2MQTT bezpośrednio.

## Endpoint

```text
GET /api/v1/zigbee
```

Odpowiedź sukcesu:

```json
{
  "ok": true,
  "zigbee": {
    "broker_host": "127.0.0.1",
    "broker_port": 1883,
    "base_topic": "zigbee2mqtt",
    "running": true,
    "connected": true,
    "devices": []
  }
}
```

Pole `zigbee` jest bezpośrednią projekcją autorytatywnego `state.zigbee` z `ventilation-core`. Web API nie utrzymuje własnej kopii stanu urządzeń.

Jeżeli core odpowiada poprawnie, ale nie udostępnia stanu Zigbee, endpoint zwraca HTTP 503 z `ok=false`.

## Bezpieczeństwo i zakres

Stage 5 nie dodaje żadnego endpointu zapisu dla Zigbee. W szczególności nie udostępnia:

- `permit_join`,
- parowania,
- usuwania urządzeń,
- zmiany `friendly_name`,
- sterowania urządzeniami,
- zmian konfiguracji Zigbee2MQTT.

Nie zmienia również systemu alertów, harmonogramów ani logiki sterowania wentylacją.

## Walidacja CM5

Po synchronizacji gałęzi:

```bash
sudo bash tools/validate_cm5_zigbee_web_stage5.sh
```

Walidator:

1. uruchamia test kontraktu Stage 5,
2. restartuje tylko `wvc-web-ui.service`,
3. sprawdza `GET /api/v1/zigbee`,
4. weryfikuje mapowanie `temp_nawiew` i `temp_wywiew`,
5. porównuje dane z `GET /api/v1/state`, aby potwierdzić brak drugiego źródła prawdy.

`ventilation-core` nie jest restartowany w tym etapie.

## Następny etap

Po pozytywnej walidacji Stage 5 można zbudować widok `Ustawienia -> Zigbee`, który będzie korzystał wyłącznie z `/api/v1/zigbee`.
