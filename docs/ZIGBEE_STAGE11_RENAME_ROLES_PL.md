# Zigbee Stage 11 — nazwy i role systemowe

## Cel

Stage 11 domyka zarządzanie urządzeniami Zigbee w `ventilation-core` i Web V2.

Dostępne operacje:

- zmiana `friendly_name` urządzenia,
- przypisanie roli `NAWIEW`,
- przypisanie roli `WYWIEW`,
- ustawienie `BEZ ROLI`.

Architektura pozostaje:

```text
GUI
  -> Web API
  -> ventilation-core
  -> MQTT
  -> Zigbee2MQTT
```

Nie ma bezpośredniego MQTT z przeglądarki ani ogólnego proxy publish.

## Trwały rejestr ról

Role nie są już zależne wyłącznie od argumentów systemd. Core posiada mały rejestr:

```text
/var/lib/workshop-ventilation/zigbee-roles.json
```

Pierwsze uruchomienie Stage 11 seeduje go z dotychczasowej konfiguracji:

- `supply` -> `temp_nawiew` / `0xa4c13810e66fffff`,
- `extract` -> `temp_wywiew` / `0xa4c13810bdedffff`.

Późniejsze zmiany z GUI są zapisywane atomowo przez core i przetrwają restart usługi.

## Rename

Web API:

```text
POST /api/v1/zigbee/rename
```

Przykład:

```json
{"device_id":"0xa4c13810e66fffff","new_name":"temp_nawiew_1"}
```

Core korzysta z oficjalnego requestu Zigbee2MQTT:

```text
zigbee2mqtt/bridge/request/device/rename
```

z payloadem `from`/`to`.

Jeżeli urządzenie ma rolę systemową, core aktualizuje także zapisany `friendly_name`, topic telemetryczny i subskrypcję MQTT bez restartu core.

Nazwy akceptowane przez GUI/core w tym wdrożeniu są celowo ograniczone do 1..64 znaków ASCII: litery, cyfry, `.`, `_`, `-`. Eliminuje to ukośniki i wildcardy MQTT z nazw używanych jako topic.

## Role

Web API:

```text
POST /api/v1/zigbee/role
```

Payload:

```json
{"device_id":"0xa4c13810e66fffff","role":"supply"}
```

Dozwolone role:

- `supply` = `NAWIEW`,
- `extract` = `WYWIEW`,
- `null` = `BEZ ROLI`.

Jedna rola może wskazywać tylko jedno urządzenie. Jeśli rola jest zajęta przez inne urządzenie, core odrzuca zmianę i wymaga najpierw ustawienia poprzedniego urządzenia na `BEZ ROLI`. Dzięki temu przypadkowa zmiana w GUI nie podmienia aktywnego czujnika kanału.

Przy przypisaniu roli core ponownie wymusza dla urządzenia:

```text
retain=true
```

przez `bridge/request/device/options`, aby zachować właściwości Stage 10.

## Usuwanie

Po poprawnym `device/remove` core automatycznie zwalnia rolę przypisaną do usuniętego IEEE. W GUI odpowiednia karta systemowa pozostaje jako:

```text
NIEPRZYPISANE
```

Dzięki temu usunięcie czujnika nie pozostawia starego IEEE/friendly_name jako aktywnej konfiguracji systemowej.

## GUI

W `Ustawienia -> Zigbee`, przy każdym urządzeniu innym niż koordynator, dostępne są:

- pole nazwy i `ZMIEŃ NAZWĘ`,
- lista `BEZ ROLI / NAWIEW / WYWIEW`,
- `USUŃ`.

Sekcja `ROLE SYSTEMOWE` zawsze pokazuje dwa miejsca: `NAWIEW` i `WYWIEW`. Jeżeli rola nie ma urządzenia, wyświetlany jest jawny placeholder `NIEPRZYPISANE`.

## Walidacja

Na stanowisku z samym CM5:

```bash
sudo bash tools/validate_cm5_zigbee_stage11_roles.sh --allow-hardware-offline
```

Walidator nie zmienia nazw i nie zwalnia żadnej roli. Sprawdza pełne testy repo, seed rejestru, live API/GUI, bezpieczny no-op rename bieżącej nazwy, ponowne przypisanie tej samej roli oraz restart core z odtworzeniem mapowania z pliku.
