# CM5 Zigbee Stage 13 — walidacja rozpoznawania urządzeń i capabilities

Data: 2026-08-18

Gałąź: `agent/zigbee-management-alerts-stage1`

## Wynik

Stage 13 baseline: **PASS**

## Potwierdzone elementy

- pełny zestaw testów: `Ran 276 tests ... OK`,
- po restarcie `ventilation-core` inwentarz Zigbee został poprawnie odtworzony,
- `temp_nawiew` (`0xa4c13810e66fffff`, SNZB-02LD) został rozpoznany przez core z capabilities: `battery`, `linkquality`, `temperature`,
- `temp_wywiew` (`0xa4c13810bdedffff`, SNZB-02LD) został rozpoznany przez core z capabilities: `battery`, `linkquality`, `temperature`,
- retained `bridge/devices` po restarcie nie tworzy fałszywego stanu „nowo sparowane urządzenie”,
- Web API jest wyłącznie projekcją stanu `ventilation-core`,
- GUI renderuje dane parowania i capabilities wyłącznie ze stanu core,
- GUI nie interpretuje MQTT/Zigbee2MQTT bezpośrednio,
- w modalu nowo sparowanego urządzenia nie ma sekcji „ostatnio odebrane”; prezentowane są wyłącznie capabilities rozpoznane przez core,
- wszystkie cztery usługi końcowo pozostały aktywne:
  - `ventilation-core.service`,
  - `wvc-web-ui.service`,
  - `mosquitto.service`,
  - `zigbee2mqtt.service`,
- walidator nie otwierał parowania, nie usuwał ani nie zmieniał nazw urządzeń i nie modyfikował ról systemowych.

## Wniosek

Stage 13 potwierdza architekturę, w której `ventilation-core` jest właścicielem rozpoznawania nowo sparowanych urządzeń i normalizacji ich publikowanych capabilities. GUI pozostaje wyłącznie klientem i nie zawiera własnej logiki Zigbee/MQTT. Następnym krokiem jest jeden kontrolowany test realnego parowania, aby sprawdzić modal nowo rozpoznanego urządzenia na żywym zdarzeniu `device_interview`.
