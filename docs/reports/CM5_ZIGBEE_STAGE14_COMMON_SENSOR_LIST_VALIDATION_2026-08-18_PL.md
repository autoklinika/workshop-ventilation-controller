# CM5 Zigbee Stage 14 — walidacja wspólnej listy czujników

Data: 2026-08-18
Gałąź: `agent/zigbee-management-alerts-stage1`

## Cel

Potwierdzenie, że wszystkie czujniki Zigbee są prezentowane przez jedną wspólną listę/inwentarz, a wartości pomiarowe są zbierane, normalizowane i utrzymywane przez `ventilation-core`. GUI pozostaje wyłącznie klientem stanu core.

## Wynik

**PASS**

Walidator:

`sudo bash tools/validate_cm5_zigbee_sensor_list_stage14.sh --allow-hardware-offline`

## Testy automatyczne

- `Ran 279 tests in 0.144s`
- `OK`
- pełny zestaw `unittest`: PASS

## Stan po restarcie core

`ventilation-core sensor list: ready`

Odczytane wiersze wspólnej listy:

- `temp_nawiew`: rola `supply`, temperatura 21.4 °C, bateria 100%, LQI 72, availability `True`
- `temp_wywiew`: rola `extract`, temperatura 21.9 °C, bateria 100%, LQI 174, availability `True`
- `temp_zew`: rola `none`, bieżące wartości pomiarowe jeszcze nieobecne, availability `True`

Potwierdzono:

- retained telemetry NAWIEW/WYWIEW po restarcie core: PASS
- `temp_zew` obecny we wspólnej liście: PASS

## Role

Migracja rejestru ról do wersji 2: PASS.

Potwierdzono obsługę wielu urządzeń z rolą `OTHER/INNE`, przy zachowaniu pojedynczych ról systemowych `supply/NAWIEW` i `extract/WYWIEW`.

## Web API i GUI

- Web API projektuje wspólną listę czujników należącą do core: PASS
- jedna lista inwentarza dla wszystkich czujników: PASS
- rzeczywiste odczyty renderowane z `zigbee.sensor_list`: PASS
- rola `INNE`: PASS
- GUI pozostaje klientem bez interpretacji MQTT/Zigbee2MQTT: PASS

## Bezpieczeństwo walidacji

Walidator nie:

- otwierał parowania,
- usuwał urządzeń,
- zmieniał nazw,
- zmieniał przypisania ról.

Po walidacji trzy znane czujniki pozostały sparowane, a `permit_join` pozostał `false`.

## Usługi

Po walidacji aktywne:

- `ventilation-core.service`
- `wvc-web-ui.service`
- `mosquitto.service`
- `zigbee2mqtt.service`

## Wniosek

Stage 14 został zakończony wynikiem **PASS**. Architektura pozostaje zgodna z założeniem: `ventilation-core` jest właścicielem inwentarza, ról i danych telemetrycznych, a GUI jedynie renderuje autorytatywny stan core w jednej zwartej liście urządzeń.
