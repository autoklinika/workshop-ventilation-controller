# Zigbee Stage 8/9 — zarządzanie urządzeniami i alerty

## Zakres

Ta gałąź rozwija zwalidowany Stage 7 bez zmiany podstawowej architektury:

```text
GUI
  -> Web API
  -> ventilation-core
  -> MQTT
  -> Zigbee2MQTT
  -> koordynator / urządzenia
```

Przeglądarka nadal nie publikuje bezpośrednio do MQTT i nie otrzymuje ogólnego
proxy komend Zigbee2MQTT.

## Stage 8 — zarządzanie urządzeniami

`ventilation-core` subskrybuje dodatkowo retained/state topics Zigbee2MQTT:

- `bridge/info`,
- `bridge/state`,
- `bridge/devices`,
- `bridge/event`,
- `bridge/response/#`.

Do `state.zigbee` dochodzą:

- `bridge_online`,
- `permit_join`,
- `permit_join_end`,
- `inventory_updated_at`,
- `last_event`,
- `inventory`.

Inwentarz zawiera m.in. IEEE, `friendly_name`, typ urządzenia, producenta, model,
stan interview i źródło zasilania.

### Operacje zapisu

Udostępnione są tylko dwie jawne operacje:

```text
POST /api/v1/zigbee/permit-join
POST /api/v1/zigbee/remove
```

Pierwsza przyjmuje `{"seconds": 0..254}`. Wartość `0` zamyka parowanie.

Druga przyjmuje `{"device_id": "IEEE lub friendly_name"}` i wykonuje zwykłe
`device/remove`.

Nie ma:

- ogólnego publish MQTT,
- sterowania urządzeniami,
- `force=true`,
- usuwania koordynatora.

`force remove` jest celowo pominięty, ponieważ usuwa urządzenie tylko z bazy
Zigbee2MQTT; urządzenie może nadal posiadać klucz sieci. Jeżeli zwykłe usunięcie
śpiącego urządzenia bateryjnego się nie powiedzie, operator powinien je wybudzić
i ponowić operację.

### GUI

`Ustawienia -> Zigbee` pokazuje:

- MQTT i stan bridge,
- stan/timer permit join,
- dwa semantyczne kanały temperatury używane przez core,
- pełny inwentarz Zigbee2MQTT,
- przycisk `DODAJ URZĄDZENIE · 120 S`,
- przycisk `ZAMKNIJ PAROWANIE`,
- `USUŃ` przy urządzeniach innych niż koordynator.

Dodanie oznacza otwarcie sieci na ograniczony czas. Fizyczne urządzenie nadal
musi zostać przełączone w swój tryb parowania.

## Stage 9 — alerty Zigbee w core

Alerty korzystają z istniejącego `AlertRegistry`, SQLite, ACK i historii.
Nie powstaje drugi system alertów.

Dodane kody:

- `ZIGBEE_MQTT_DISCONNECTED`,
- `ZIGBEE_BRIDGE_OFFLINE`,
- `ZIGBEE_DEVICE_OFFLINE`,
- `ZIGBEE_DEVICE_DATA_STALE`,
- `ZIGBEE_LOW_BATTERY`.

Zasady bieżącego etapu:

- wszystkie mają poziom `WARNING`,
- `DEVICE_OFFLINE` pojawia się przy jawnej `availability=false` albo gdy
  wymagany semantyczny czujnik znika z retained `bridge/devices`,
- `DATA_STALE` wymaga co najmniej jednej wcześniejszej wiadomości i domyślnie
  progu 4 godzin,
- `LOW_BATTERY` ma domyślny próg 20%,
- brak publikowanego `availability` sam w sobie nie jest błędem,
- alerty Zigbee nie blokują sterowania wentylacją.

Pełny Alert V2 z przypomnieniami po ACK, eskalacją i stanem
`ACTIVE / ACKNOWLEDGED / RESOLVED` pozostaje osobnym późniejszym etapem.

## Walidacja na obecnym stanowisku

Na stanowisku z samym CM5 i odłączoną częścią wykonawczą:

```bash
sudo bash tools/validate_cm5_zigbee_management_alerts_stage9.sh --allow-hardware-offline
```

Walidator:

1. sprawdza bezpieczne programowe `0 V / 0 V`,
2. uruchamia pełny zestaw testów repo,
3. restartuje core i Web GUI, aby załadować nowy kod,
4. czeka na MQTT, `bridge/state` i retained `bridge/devices`,
5. potwierdza koordynator i oba SNZB-02LD,
6. wykonuje wyłącznie bezpieczny zapis `permit_join=0`,
7. nie otwiera sieci i nie usuwa żadnego urządzenia,
8. sprawdza GUI,
9. potwierdza brak fałszywych aktywnych alertów Zigbee w zdrowym baseline.

Gałąź bazowa Stage 7 pozostaje zachowana. `main` nie jest modyfikowany.
