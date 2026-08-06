# KAmod Service OTA Stage 1 — incydent pierwszego transferu

Data: 2026-08-06

## 1. Zakres testu

Pierwszy rzeczywisty transfer OTA wykonano wyłącznie na:

```text
node_id: sensor-node-1
adres: 10.55.0.106
wersja źródłowa: 0.5.0-stage1
partycja źródłowa: ota_0
wersja docelowa: 0.5.1-stage1
oczekiwana partycja docelowa: ota_1
```

Obraz:

```text
rozmiar: 972848 B
SHA-256: 91f6dd48a6a9c1755f4f7b4c98af9fe36399ea623102a56fd4e594f9391c911c
```

Stan wejściowy był prawidłowy:

- endpoint `WVC-OTA1` dostępny,
- obraz źródłowy `valid`, `pending=false`, `state=idle`,
- oba slave Modbus online i usable,
- `worker_alive=true`,
- `worker_restarts=0`,
- `consecutive_failures=0` dla obu slave.

## 2. Wynik pierwszej próby

Operacja CM5:

```text
operation_id: 1786030678-f2fdd438
```

Zaobserwowany przebieg:

```text
queued
uploading: 245760 / 972848 B
lokalne bytes_sent: 972848 / 972848 B
terminalny stan klienta: uncertain
```

Komunikat:

```text
OTA image body was sent completely but the final response was lost;
operation state is uncertain and must be verified with ota-status
```

Po operacji węzeł raportował:

```text
firmware: 0.5.0-stage1
partition: ota_0
pending: false
image_state: valid
state: idle
```

Obraz `0.5.1-stage1` nie został przełączony. Nie był potrzebny rollback ani flash USB.

## 3. Wniosek bezpieczeństwa

Mechanizm fail-safe zachował działający firmware źródłowy. Brak końcowej odpowiedzi HTTP nie spowodował:

- zmiany aktywnej partycji,
- utraty konfiguracji NVS,
- wpływu na `sensor-node-2`,
- restartu `ventilation-core`,
- trwałej niedostępności Modbus.

Pierwsza próba jest FAIL dla transferu, ale PASS dla zachowania bezpieczeństwa.

## 4. Przyczyna programowa

Klient CM5 miał domyślny timeout transferu równy 20 s. Timeout obejmował przesłanie obrazu, zapis flash po stronie ESP32, walidację obrazu i oczekiwanie na końcową odpowiedź HTTP.

Dodatkowo `wvc-servicectl` podczas aktywnego transferu cyklicznie wywoływał `ota-status`, a Service Agent próbował wtedy otworzyć dodatkowe połączenie HTTP do węzła. Serwer HTTP ESP32 wykonuje handler uploadu w swoim zadaniu i nie może w tym czasie obsłużyć statusu, dlatego dodatkowe połączenia kończyły się timeoutem i tworzyły niepotrzebną konkurencję o zasoby sieciowe.

Lokalne `bytes_sent=972848` potwierdza zapis do bufora TCP po stronie CM5, ale nie stanowi dowodu, że ESP32 odebrał i zatwierdził wszystkie bajty przed zamknięciem połączenia.

## 5. Poprawka

Checkpoint poprawki:

```text
branch: agent/kamod-service-ota-stage1
```

Zmiany:

- timeout transferu i końcowego commit-response zwiększony z 20 s do 180 s,
- status aktywnej operacji nie otwiera drugiego połączenia HTTP do ESP32,
- przed transferem zapisywana jest partycja źródłowa i wyznaczana oczekiwana partycja docelowa,
- utrata odpowiedzi po wysłaniu pełnego body uruchamia reconciliation zamiast natychmiastowego terminalnego `uncertain`,
- reconciliation rozpoznaje sukces, rollback albo brak commitowania obrazu,
- okno walidacji po transferze zwiększone do 180 s,
- dodane testy timeoutu, izolacji statusu podczas uploadu i reconciliation po utracie odpowiedzi.

## 6. Kolejna próba

Nie flashować KAmod przez USB. Po przejściu CI:

1. zaktualizować gałąź na CM5,
2. ponownie uruchomić `install_cm5_service_agent.sh`,
3. przejść `validate_cm5_service_agent.sh`,
4. potwierdzić `0.5.0-stage1 / ota_0 / valid / idle`,
5. ponowić ten sam obraz `0.5.1-stage1`,
6. nie aktualizować `sensor-node-2`.

PR #14 pozostaje Draft. Nie wykonywać merge ani Ready for Review bez wyraźnego polecenia użytkownika.
