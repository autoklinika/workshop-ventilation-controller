# CM5 Zigbee Stage 6 — walidacja GUI Ustawienia → Zigbee

Data walidacji: 2026-08-18
Gałąź: `agent/zigbee-stage1`
Tryb stanowiska: sam CM5 i infrastruktura Zigbee; część wykonawcza celowo offline

## Wynik

Stage 6 zakończony wynikiem PASS.

Potwierdzono:

- `ventilation-core.service` aktywny,
- `wvc-web-ui.service` aktywny,
- `mosquitto.service` aktywny,
- `zigbee2mqtt.service` aktywny,
- Web V2 działa na porcie `18091`,
- `GET /settings` działa,
- `zigbee-settings.js` i `zigbee-settings.css` są poprawnie serwowane,
- GUI czyta wyłącznie `GET /api/v1/zigbee`,
- oba sparowane czujniki są widoczne pod rolami semantycznymi,
- brak błędów parsowania danych Zigbee,
- `ventilation-core` nie został zrestartowany podczas walidacji.

## Dane z walidacji

### Nawiew

- rola: `supply`
- friendly name: `temp_nawiew`
- temperatura: `25.4 °C`
- bateria: `100 %`
- linkquality: `127`

### Wywiew

- rola: `extract`
- friendly name: `temp_wywiew`
- temperatura: `25.3 °C`
- bateria: `100 %`
- linkquality: `98`

## Kontrola restartu core

Przed walidacją:

```text
ventilation-core PID before: 12717
```

Po walidacji:

```text
ventilation-core PID after: 12717
ventilation-core untouched: PASS
```

## Zakres bezpieczeństwa

Stage 6 pozostaje tylko do odczytu. Nie dodano funkcji:

- `permit_join`,
- parowania,
- usuwania urządzeń,
- zmiany nazw urządzeń,
- sterowania Zigbee,
- bezpośredniej komunikacji GUI z MQTT,
- zmian alertów,
- zmian sterowania wentylacją.

## Decyzja

Warstwa:

```text
Zigbee2MQTT -> Mosquitto -> ventilation-core -> Web API -> Ustawienia/Zigbee
```

jest zwalidowana. Następny krok to końcowa walidacja regresyjna całej gałęzi Zigbee bez dodawania nowych funkcji.
