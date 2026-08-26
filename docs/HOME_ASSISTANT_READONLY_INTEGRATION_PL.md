# Home Assistant — integracja WVC tylko do odczytu

## Status

Projektowana integracja Home Assistant ma charakter wyłącznie obserwacyjny. Home Assistant nie jest elementem sterowania Workshop Ventilation Controller i nie może zmieniać stanu instalacji ani wykonywać operacji operatorskich.

Status na 2026-08-26: warstwa `wvc-ha-api` została zwalidowana programowo w CI oraz fizycznie na rzeczywistym CM5 w odseparowanym worktree, bez zmiany produkcyjnego `main`.

## Twardy niezmiennik architektury

```text
ventilation-core / AlertV2
        |
        | lokalny odczyt
        v
    wvc-ha-api
        |
        | HTTP GET only
        v
 Home Assistant
        |
        +--> dashboard
        +--> historia po stronie HA
        +--> powiadomienia
```

Nie istnieje obsługiwana ścieżka:

```text
Home Assistant --> sterowanie WVC
```

W szczególności HA nie może:

- ustawiać napięć wentylatorów,
- zmieniać trybu pracy,
- sterować AERO,
- wykonywać STOP,
- wykonywać ACK alertów,
- zmieniać harmonogramu,
- parować/usuwać/konfigurować Zigbee,
- sterować zasilaniem CM5/HMI,
- wywoływać dowolnych/genericznych komend `ventilation-core`.

## Dedykowana usługa

`wvc-ha-api.service` działa niezależnie od WebGUI i domyślnie słucha na porcie `8082`.

Obsługiwane endpointy:

```text
GET /api/ha/v1/health
GET /api/ha/v1/state
GET /api/ha/v1/snapshot
GET /api/ha/v1/alerts
```

`/snapshot` jest stabilną, uproszczoną projekcją bieżącego `status` z `ventilation-core`. Nie zawiera własnej logiki diagnostycznej ani sterującej. Alerty i ich klasyfikacja pozostają własnością `ventilation-core` / AlertV2.

Wszystkie metody inne niż `GET` są odrzucane `405 Method Not Allowed`. Nieznane trasy sterujące nie są proxyowane do core i zwracają `404 Not Found`.

## Kontrakt snapshot v1

Odpowiedź zawiera między innymi:

- `schema_version = 1`,
- `read_only = true`,
- tryb i gotowość hardware,
- aktualne setpointy jako dane obserwacyjne,
- SENSOR BUS i pomiary SEN55 według adresu Modbus,
- TACHO SUPPLY/EXTRACT,
- stan AERO,
- stan Zigbee,
- bieżący zestaw aktywnych alertów AlertV2,
- `active_ids`, `active_weight`, `hmi_color`, `policy_version`,
- `control_policy_applied` przekazane z AlertV2 jako informacja diagnostyczna.

`active_ids` pozwala Home Assistantowi wykrywać zmianę zestawu aktywnych alertów bez reagowania na sam wzrost licznika `occurrences` trwającej awarii.

## Walidacja na rzeczywistym CM5 — 2026-08-26

Test wykonano z odseparowanego worktree `wvc-ha-readonly-test`, podczas gdy produkcyjny checkout pozostał na:

```text
branch: main
HEAD: d8ed6761882faba5e79f0c1d0d4133a769db508a
```

Zweryfikowano:

- 11/11 dedykowanych testów HA PASS na CM5,
- `GET /api/ha/v1/snapshot` -> `200 OK`,
- snapshot zawierał rzeczywiste dane obu SEN55, TACHO, AERO, Zigbee i AlertV2,
- `read_only = true`,
- `schema_version = 1`,
- `POST /api/ha/v1/snapshot` -> `405 Method Not Allowed`,
- nagłówek `Allow: GET`,
- wcześniejsze testy `PUT`, `PATCH`, `DELETE` również -> `405`,
- nieznana trasa sterująca `/api/ha/v1/manual/fans` -> `404`,
- po testach `ventilation-core` pozostał zdrowy i nie wykonał żadnej komendy sterującej z warstwy HA.

Podczas testu AERO było fizycznie odłączone, dlatego aktywny `AERO_BUS_UNAVAILABLE` był oczekiwanym stanem diagnostycznym i potwierdził, że AlertV2 jest poprawnie przenoszony do `/snapshot`.

## Home Assistant

Przykład konfiguracji znajduje się w:

```text
deploy/home-assistant/wvc-readonly-rest.yaml.example
```

Konfiguracja HA ma używać wyłącznie `GET` do `/api/ha/v1/snapshot`. Nie należy dodawać dla WVC `rest_command`, switchy, buttonów, number/select ani innych encji wykonujących zapis.

Przykład korzysta z jednego współdzielonego odczytu REST i tworzy z niego wiele encji. Dodatkowe encje `WVC Alarm Active` i `WVC Critical Alert` są jedynie projekcjami gotowego wyniku AlertV2 (`active_count`, `active_weight`); Home Assistant nie implementuje własnych progów ani reguł wykrywania awarii WVC.

## Izolacja sieciowa

Po wdrożeniu docelowym zalecana jest dodatkowa reguła firewall:

```text
GlobalNAS / Home Assistant -> CM5:8082  ALLOW
GlobalNAS / Home Assistant -> sterujące API WebGUI  DENY
```

Dzięki temu brak możliwości sterowania jest wymuszony jednocześnie przez:

1. osobną usługę HTTP,
2. implementację GET-only,
3. allowlistę komend core (`status`, `alerts`),
4. brak ogólnego proxy komend,
5. docelowo także izolację sieciową.

Awaria lub kompromitacja Home Assistant, NAS albo połączenia LAN nie może wpływać na autonomiczne działanie `ventilation-core`.
