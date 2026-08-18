# Zigbee Stage 13 — rozpoznawanie nowego urządzenia i publikowane dane

## Cel

Po poprawnym sparowaniu i zakończeniu interview nowego urządzenia `ventilation-core` na CM5 ma samodzielnie rozpoznać urządzenie oraz przygotować listę danych, które urządzenie publikuje. Web GUI pozostaje wyłącznie klientem: nie interpretuje `bridge/event`, `bridge/devices` ani `definition.exposes` i nie komunikuje się bezpośrednio z MQTT/Zigbee2MQTT.

## Architektura

```text
urządzenie Zigbee
    -> koordynator
    -> Zigbee2MQTT
       - bridge/event
       - bridge/devices
    -> Mosquitto
    -> ventilation-core
       - rozpoznanie interview
       - normalizacja definition.exposes
       - stan pairing
       - ACK wyniku parowania
    -> Web API
    -> GUI (renderowanie tylko stanu z core)
```

## Stan parowania w core

`ZigbeeMqttState.pairing` przechowuje ostatni wynik bieżącego procesu parowania/interview. Dla poprawnie rozpoznanego urządzenia core udostępnia m.in.:

- status interview,
- IEEE,
- friendly name,
- producenta,
- model,
- opis,
- listę `capabilities`,
- stan potwierdzenia przez operatora.

Stan ten jest runtime-state core. Po restarcie core nie jest odtwarzany jako „nowo sparowane urządzenie” z samego retained `bridge/devices`, dzięki czemu stare urządzenia nie generują fałszywego modala.

## Capabilities

Core odczytuje `definition.exposes` otrzymane z Zigbee2MQTT i normalizuje tylko właściwości publikowane przez urządzenie. W Stage 13:

- wymagany jest bit publikowania w polu `access`,
- pozycje `category=config` są pomijane,
- złożone `features` są rozwijane,
- zachowywane są m.in. property, label/name, typ, jednostka, endpoint, opis, zakres i wartości enum.

Lista opisuje **dane publikowane przez urządzenie**, a nie pełną listę elementów możliwych do konfiguracji/sterowania.

## GUI

Po `device_interview` ze statusem `successful` core tworzy wynik rozpoznania. GUI pokazuje systemowy modal:

- `CM5 · VENTILATION-CORE`,
- nazwę urządzenia,
- producenta/model,
- IEEE,
- sekcję `DOSTĘPNE DANE`.

Nie ma sekcji „ostatnio odebrane”. GUI nie parsuje exposes i nie buduje listy capabilities samodzielnie. Wyświetla wyłącznie `zigbee.pairing.capabilities` zwrócone przez core.

Przycisk `OK` wysyła jawny intent `POST /api/v1/zigbee/pairing/ack`; właściwy stan ACK jest zapisywany w runtime-state ventilation-core.

## Inwentarz

Core dołącza znormalizowane `capabilities` także do elementów `zigbee.inventory`. Dzięki temu informacje o danych publikowanych przez już sparowane urządzenia są dostępne z retained `bridge/devices` po restarcie core, ale nie są traktowane jako nowe parowanie.

## Usuwanie śpiącego urządzenia bateryjnego

Stage 13 uzupełnia również istniejący systemowy flow usuwania. Jeśli zwykłe, bezpieczne `device/remove` zwróci błąd charakterystyczny dla braku odpowiedzi śpiącego urządzenia (`mgmtLeaveRsp` timeout), ventilation-core zachowuje oczekujące potwierdzenie i przekazuje operatorowi komunikat:

> Urządzenie nie odpowiedziało. Wybudź je krótkim naciśnięciem przycisku i ponów usuwanie.

Po wybudzeniu operator może ponownie użyć tego samego potwierdzenia. Nie dodajemy `force=true`.

## Niezmienniki bezpieczeństwa

- GUI nie komunikuje się z MQTT ani Zigbee2MQTT.
- GUI nie interpretuje `definition.exposes`.
- Brak generic MQTT publish.
- Brak force-remove.
- Koordynator nadal nie może być usunięty.
- Role `NAWIEW/WYWIEW` są niezależne od rozpoznawania capability.
- Awaria/nieznane urządzenie Zigbee nie wpływa na sterowanie wentylatorami.
