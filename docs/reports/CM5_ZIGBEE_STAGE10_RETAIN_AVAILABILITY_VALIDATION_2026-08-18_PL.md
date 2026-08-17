# CM5 Zigbee Stage 10 — walidacja retained telemetry i availability

Data walidacji: 2026-08-18
Gałąź: `agent/zigbee-management-alerts-stage1`
Tryb stanowiska: sam CM5 + infrastruktura Zigbee; część wykonawcza celowo offline

## Wynik

Stage 10 zakończony wynikiem PASS.

Potwierdzono:

- pełny zestaw 257 testów: PASS,
- `permit_join=false`,
- koordynator ZStack3x0,
- `retain=true` dla `temp_nawiew`,
- `retain=true` dla `temp_wywiew`,
- `availability.enabled=true`,
- wymagany restart Zigbee2MQTT wykonany poprawnie,
- retained availability dla obu czujników,
- availability obu czujników = online,
- retained telemetry odtwarza temperaturę i baterię po restarcie `ventilation-core`,
- `ZIGBEE_DEVICE_DATA_STALE` korzysta z `last_seen` urządzenia z fallbackiem do `last_message_at`,
- wszystkie usługi pozostały aktywne.

## Wynik live po restarcie core

```text
supply: temp_nawiew availability=True temp=25.3 battery=100.0 last_seen=2026-08-17T22:51:56.575Z messages=1 retained_restore=PASS
extract: temp_wywiew availability=True temp=25.1 battery=100.0 last_seen=2026-08-17T22:59:07.719Z messages=1 retained_restore=PASS
stale-age source: device last_seen (fallback last_message_at)
```

## Stan usług

```text
ventilation-core.service     active
wvc-web-ui.service           active
mosquitto.service            active
zigbee2mqtt.service          active
```

## Bezpieczeństwo

Walidacja nie otwierała parowania i nie usuwała urządzeń. Programowe setpointy pozostawały `0 V / 0 V` przy celowo odłączonej części wykonawczej.

## Decyzja

Fundament stanu urządzeń Zigbee po restarcie jest zamknięty jako poprawny. Następny etap: zarządzanie nazwą urządzenia i przypisaniem roli systemowej (`NAWIEW`, `WYWIEW`, brak roli), a następnie praktyczny test usunięcia i ponownego sparowania jednego urządzenia.
