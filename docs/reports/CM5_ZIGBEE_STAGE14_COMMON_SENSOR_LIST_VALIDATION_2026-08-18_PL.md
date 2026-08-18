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

## Praktyczny test retained telemetry dla roli INNE

Po przypisaniu `temp_zew` do roli `other/INNE` i odebraniu rzeczywistego raportu czujnika wykonano osobny restart `ventilation-core` bez poruszania, nagrzewania ani wymuszania kolejnego raportu urządzenia.

Stan `temp_zew` przed restartem:

- rola: `other`
- temperatura: `25.35 °C`
- wilgotność: `49.3 %`
- bateria: `100 %`
- napięcie: brak wartości w ostatnim payloadzie
- LQI: `0`
- availability: `True`
- `last_seen`: `2026-08-18T10:08:31.965Z`
- `last_message_at`: `2026-08-18T10:08:31.966805+00:00`
- licznik wiadomości procesu core: `13`

Stan po restarcie `ventilation-core`:

- temperatura: `25.35 °C`
- wilgotność: `49.3 %`
- bateria: `100 %`
- availability: `True`
- `last_seen`: **bez zmiany**, nadal `2026-08-18T10:08:31.965Z`
- `last_message_at`: `2026-08-18T10:12:53.455961+00:00`
- licznik wiadomości nowego procesu core: `1`

Niezmienione `last_seen` przy jednoczesnym odtworzeniu wartości po restarcie i nowym `last_message_at` potwierdza odczyt retained payloadu przez nowy proces core, a nie nowy pomiar urządzenia.

**Retained telemetry dla urządzeń `INNE`: PASS.**

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

Po walidacji oraz po dodatkowym teście restartu aktywne:

- `ventilation-core.service`
- `wvc-web-ui.service`
- `mosquitto.service`
- `zigbee2mqtt.service`

## Wniosek

Stage 14 został zakończony wynikiem **PASS**. Architektura pozostaje zgodna z założeniem: `ventilation-core` jest właścicielem inwentarza, ról i danych telemetrycznych, a GUI jedynie renderuje autorytatywny stan core w jednej zwartej liście urządzeń. Dodatkowo praktycznie potwierdzono retained telemetry po restarcie także dla wielokrotnej roli `INNE`.