# Control Engine V1 Stage2 — walidacja CM5 realnych wejść SEN55 + Zigbee

Data: 2026-08-28
Repozytorium: `autoklinika/workshop-ventilation-controller`
Gałąź: `agent/automation-v1-control-engine`
Walidowany SHA: `8147698b8a88514c7e2f166bfa546f2eda30ab08`
Produkcja `main`: `7628c407cfc9c0ea72d262566759ea2d4598fec8`

## Wynik

**PASS** — Control Engine V1 Stage2 poprawnie zmapował rzeczywiste wejścia SEN55 + Zigbee do SHADOW, przy zachowaniu pełnego braku aktuacji.

## Zweryfikowany tor

- DAC / local hardware ready,
- SEN55 Modbus address 1,
- SEN55 Modbus address 2,
- AERO / rekuperator,
- Zigbee2MQTT / MQTT bridge,
- Zigbee rola `supply`,
- Zigbee rola `extract`,
- Control Engine SHADOW.

## Wynik danych podczas testu

SEN55 address 1:
- PM1.0: 10.1 ug/m3
- PM2.5: 10.8 ug/m3
- PM4.0: 10.9 ug/m3
- PM10: 11.0 ug/m3
- VOC index: 157
- NOx index: 1
- temperatura: 25.65 C
- wilgotność: 34.92 %

SEN55 address 2:
- PM1.0: 11.3 ug/m3
- PM2.5: 11.8 ug/m3
- PM4.0: 11.8 ug/m3
- PM10: 11.8 ug/m3
- VOC index: 158
- NOx index: 1
- temperatura: 26.06 C
- wilgotność: 34.69 %

Zigbee:
- supply: 24.4 C
- extract: 24.1 C
- supply timestamp: `2026-08-28T08:25:57.600Z`
- supply age: 531.344039 s
- freshness: `fresh`
- reason: `OK`

Control Engine SHADOW:
- status: `TUNING_REQUIRED`
- zone 1 AQ level: `BOOST`
- zone 1 driver: `VOC`
- zone 2 AQ level: `BOOST`
- zone 2 driver: `VOC`
- `delta_t`: 1.25 C (`25.65 - 24.4`)

**Uwaga:** wartości środowiskowe pochodzą z LAB i nie służą do strojenia progów lub wydajności produkcyjnej. Test potwierdza wyłącznie poprawność toru danych, freshness, mapowania i logiki SHADOW.

## Bezpieczeństwo

Potwierdzono:
- local EC supply = 0 V,
- local EC extract = 0 V,
- brak obserwowanego ruchu wentylatorów,
- `actuation_supported=false`,
- brak fizycznej aktuacji Control Engine,
- RTC bez zmian,
- `wvc-host-power` bez wywołania,
- 12 V domain pozostała ON,
- CM5 nie wykonał reboot ani poweroff,
- `boot_id` pozostał `2af4e8dd-65e8-402b-8ddc-e3cab2a1cf71`,
- host-power PID pozostał `709`,
- po teście produkcyjny core został przywrócony do `main`.

PID-y testu:
- main before: 37907
- branch: 50566
- main after: 50806

## Istotna poprawka wykryta podczas Stage2

W poprzedniej próbie fizycznej wykryto niespójność pomiędzy `CoreState.zigbee` i `shadow_automation`: SHADOW był liczony przed dołączeniem aktualnego snapshotu Zigbee, a końcowy status zawierał już nowszy snapshot. Powodowało to możliwość wystąpienia dwóch różnych obrazów Zigbee w jednym statusie.

Naprawa w SHA `8147698b8a88514c7e2f166bfa546f2eda30ab08` wymusza kolejność:

`CoreState -> Alerty -> jeden snapshot Zigbee -> SHADOW z tego samego snapshotu -> status`

Dodano regresję wymuszającą pojedynczy odczyt monitora Zigbee i identyczny snapshot dla `CoreState.zigbee` oraz Control Engine.

## Decyzja po Stage2

Stage2 zostaje zamknięty jako **PASS**.

Następny etap: deterministyczny Scenario/Replay Engine do walidacji przejść Control Engine na kontrolowanych danych syntetycznych. W LAB nie należy stroić polityki na aktualnych odczytach środowiskowych.
