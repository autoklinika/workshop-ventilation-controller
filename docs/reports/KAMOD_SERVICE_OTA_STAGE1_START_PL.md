# KAmod Service OTA Stage 1 — start implementacji

Data: 2026-08-06

## 1. Repozytorium i baza

```text
repo:   autoklinika/workshop-ventilation-controller
branch: agent/kamod-service-ota-stage1
base:   agent/cm5-service-agent-stage1
commit: 1934c3b20c34487bebaac74ba2d1c5d81891722f
```

Gałąź jest stacked nad Draft PR #12. Draft PR #11 dostarcza firmware Service Wi-Fi, a PR #12 dostarcza CM5 Service Agent. Diagnostyczny Draft PR #13 nie jest częścią OTA Stage 1.

Nie wykonywać merge ani nie oznaczać PR jako Ready for Review bez wyraźnego polecenia użytkownika.

## 2. Przyjęty model odpowiedzialności

```text
heartbeat Wi-Fi: best effort
service diagnostics: na żądanie, głównie po błędzie RS-485
OTA: jawna operacja serwisowa z retry, A/B i rollbackiem
RS-485 Modbus RTU: jedyny kanał krytyczny
```

Okresowe braki pojedynczych heartbeat UDP nie są awarią wentylacji i nie blokują implementacji OTA. Kryterium jakości Wi-Fi dla OTA będzie oparte na bezpiecznym zachowaniu przy przerwaniu transferu, ponowieniu operacji i rollbacku, a nie na bezbłędnym 30-minutowym strumieniu datagramów.

## 3. Cel Stage 1

Zaimplementować minimalny, ręcznie uruchamiany kanał OTA dla pojedynczego węzła KAmod:

- operator wskazuje `node_id` i plik aplikacji `.bin` na CM5,
- CM5 wykonuje preflight węzła,
- CM5 uwierzytelnia operację kluczem HMAC przypisanym do węzła,
- firmware zapisuje obraz do nieaktywnej partycji OTA,
- obraz jest weryfikowany przed zmianą partycji startowej,
- urządzenie uruchamia nową partycję,
- nowy obraz zostaje potwierdzony dopiero po przejściu testu zdrowia,
- brak potwierdzenia powoduje rollback do poprzedniej działającej wersji.

Aktualizacja zawsze dotyczy jednego węzła. Równoległe OTA dwóch KAmod jest poza Stage 1.

## 4. Kierunek i protokół transportu

CM5 inicjuje połączenie TCP/HTTP do węzła KAmod w prywatnej sieci `WVC-SERVICE`.

Firmware udostępnia minimalny serwer na dedykowanym porcie serwisowym. Planowany kontrakt:

```text
GET  /v1/ota/challenge
POST /v1/ota/image
GET  /v1/ota/status
```

### Challenge

Węzeł generuje losowy, jednorazowy nonce związany z aktualnym `boot_id`. Challenge ma krótki czas ważności i zostaje unieważniony po pierwszej próbie użycia.

### Autoryzacja

CM5 oblicza SHA-256 całego obrazu i HMAC-SHA256 nad kanonicznym komunikatem:

```text
WVC-OTA1\n
node_id\n
boot_id\n
nonce\n
image_size\n
image_sha256\n
```

Żądanie zawiera co najmniej:

```text
X-WVC-Node-ID
X-WVC-Boot-ID
X-WVC-Nonce
X-WVC-Image-Size
X-WVC-Image-SHA256
X-WVC-Authorization
Content-Type: application/octet-stream
```

Firmware przed zapisem sprawdza:

- zgodność `node_id`,
- zgodność aktualnego `boot_id`,
- ważność i jednorazowość nonce,
- HMAC w porównaniu constant-time,
- deklarowany rozmiar obrazu,
- dostępność nieaktywnej partycji,
- brak innej operacji OTA,
- brak stanu `ESP_OTA_IMG_PENDING_VERIFY` wymagającego wcześniejszego rozstrzygnięcia.

Warstwa Wi-Fi pozostaje otwarta, ale modyfikacja firmware wymaga tajnego klucza HMAC per node. Poufność obrazu nie jest celem Stage 1; integralność i autoryzacja są wymagane.

## 5. Zapis i aktywacja obrazu

Firmware korzysta z natywnych operacji ESP-IDF:

```text
esp_ota_get_next_update_partition
esp_ota_begin
esp_ota_write
esp_ota_end
esp_ota_set_boot_partition
```

Dane są zapisywane strumieniowo. Równolegle liczony jest SHA-256 odebranej zawartości.

Przy każdym błędzie lub niepełnym body:

- wykonywane jest `esp_ota_abort`,
- partycja startowa nie jest zmieniana,
- działająca aplikacja pozostaje aktywna,
- operator otrzymuje błąd umożliwiający ponowienie od początku.

Po pełnym zapisie:

1. `esp_ota_end` sprawdza poprawność obrazu aplikacji,
2. obliczony SHA-256 musi być zgodny z podpisanymi metadanymi,
3. dopiero wtedy wywoływane jest `esp_ota_set_boot_partition`,
4. odpowiedź HTTP potwierdza przyjęcie obrazu,
5. firmware wykonuje kontrolowany restart.

Stage 1 ponawia całą operację od początku. Wznawianie transferu od offsetu jest poza zakresem.

## 6. Test zdrowia i rollback

Partycje `ota_0` i `ota_1`, `otadata` oraz `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y` są już obecne.

Dotychczasowy test zdrowia zostanie zaostrzony. Nowy obraz może zostać potwierdzony dopiero, gdy przez wymagany czas spełnione są wszystkie warunki:

- GPIO gotowe,
- I2C gotowe,
- RS-485 gotowe,
- monitor Modbus gotowy,
- SEN55 online,
- odebrano co najmniej jeden prawidłowy pomiar,
- pomiar nie jest stale,
- brak fatalnego błędu platformy.

Samo uruchomienie magistrali I2C i UART nie wystarcza do potwierdzenia obrazu.

Niepotwierdzony obraz pozostaje `ESP_OTA_IMG_PENDING_VERIFY`. Restart, watchdog lub błąd testu zdrowia ma prowadzić do uruchomienia poprzedniej działającej partycji.

## 7. CM5 Service Agent

Service Agent otrzyma jawne operacje lokalne:

```text
wvc-servicectl ota-status NODE_ID
wvc-servicectl ota-install NODE_ID IMAGE.bin
```

W Stage 1:

- polecenie jest dostępne tylko przez lokalny Unix socket,
- agent pobiera klucz z istniejącego chronionego rejestru,
- plik jest sprawdzany przed połączeniem z węzłem,
- wymagany jest aktualny adres IP węzła,
- heartbeat offline nie blokuje bezwarunkowo OTA; agent może wykonać bezpośredni preflight HTTP,
- utrata TCP powoduje abort lub timeout oraz kontrolowane ponowienie,
- agent nie restartuje `ventilation-core`,
- agent nie zmienia SENSOR BUS, DAC ani AERO BUS.

Automatyczne OTA na podstawie błędu RS-485 jest zabronione. Brak Modbus może jedynie zasugerować operatorowi diagnostykę.

## 8. Telemetria

Heartbeat i lokalne API mają raportować co najmniej:

```text
ota_partition
ota_pending
ota_state
ota_last_result
ota_last_error
ota_bytes_written
ota_expected_bytes
ota_image_sha256
ota_target_version
```

Pola postępu są diagnostyczne i nie sterują wentylacją.

## 9. Kryteria walidacji sprzętowej

Stage 1 nie jest zakończony bez testów na fizycznym KAmod:

1. poprawna aktualizacja `ota_0 -> ota_1`,
2. kolejna poprawna aktualizacja `ota_1 -> ota_0`,
3. przerwanie TCP w połowie transferu — stary firmware nadal działa,
4. błędny HMAC — brak zapisu i brak restartu,
5. błędny SHA-256 — brak aktywacji obrazu,
6. niepełny body — `esp_ota_abort`,
7. wymuszony restart podczas pierwszego bootu bez potwierdzenia — rollback,
8. prawidłowy boot, SEN55 i Modbus — potwierdzenie po teście zdrowia,
9. brak nowych trwałych błędów SENSOR BUS podczas pracy po aktualizacji,
10. aktualizacja obu węzłów kolejno, nigdy równolegle.

## 10. Poza zakresem Stage 1

- GUI,
- MQTT i Home Assistant,
- OTA równoległe,
- automatyczne aktualizacje,
- harmonogram aktualizacji,
- resume od offsetu,
- zdalne OTA przez Internet,
- zdalny provisioning,
- Secure Boot i flash encryption,
- traktowanie Wi-Fi jako kanału produkcyjnego.
