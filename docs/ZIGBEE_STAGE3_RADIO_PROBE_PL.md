# Zigbee — Stage 3: kontrolowany start koordynatora

## Cel

Stage 3 po raz pierwszy uruchamia radio Zigbee, ale nadal nie otwiera parowania urządzeń. Jego zadaniem jest potwierdzenie, że Zigbee2MQTT potrafi poprawnie uruchomić podłączony koordynator oraz odczytać jego typ, adres IEEE, firmware/meta i parametry utworzonej sieci.

## Dlaczego nie wpisujemy jeszcze `serial.adapter`

Na USB potwierdzono mostek Silicon Labs CP2102N, ale sam mostek nie jest jednoznaczną identyfikacją układu radiowego. W pierwszym uruchomieniu podajemy więc stabilną ścieżkę `serial.port`, a pole `serial.adapter` pozostawiamy nieustawione. Zigbee2MQTT/zigbee-herdsman wykonuje własne wykrywanie adaptera.

Jeżeli wykrywanie się nie powiedzie, skrypt zatrzymuje i wyłącza `zigbee2mqtt.service`, pokazuje pełny fragment logu i nie zgaduje sterownika. Na podstawie tego wyniku ustawimy jawnie właściwy sterownik (`zstack`, `ember` itd.).

## Konfiguracja kontrolna

Plik źródłowy:

```text
deploy/cm5/zigbee/zigbee2mqtt/configuration.probe.yaml
```

Najważniejsze właściwości:

- format konfiguracji Zigbee2MQTT: version 5,
- MQTT: `mqtt://127.0.0.1:1883`,
- frontend Zigbee2MQTT: wyłączony,
- Home Assistant discovery: wyłączone,
- port USB: stała ścieżka `/dev/serial/by-id/...`,
- `serial.adapter`: celowo pominięty na czas probe,
- availability: włączone,
- `last_seen`: ISO-8601,
- logowanie: tylko console/journal, bez osobnych plików na eMMC,
- network key, PAN ID i extended PAN ID: generowane przy pierwszym poprawnym starcie.

## Ochrona istniejącego stanu

`tools/start_cm5_zigbee_radio_probe.sh` jest inicjalizatorem jednorazowym. Odmawia nadpisania istniejącego `configuration.yaml`, `database.db` lub `coordinator_backup.json`. Jest to celowe: po udanym starcie wartości `GENERATE` stają się trwałą konfiguracją sieci i nie wolno ich przypadkowo wygenerować ponownie.

W przypadku nieudanego probe usługa Zigbee2MQTT jest automatycznie zatrzymywana i wyłączana, aby nie pozostawić pętli restartów.

## Uruchomienie

Po synchronizacji gałęzi:

```bash
sudo bash tools/start_cm5_zigbee_radio_probe.sh
```

Skrypt czeka na `zigbee2mqtt/bridge/state`, następnie pobiera `zigbee2mqtt/bridge/info` i drukuje podsumowanie koordynatora. Jeżeli `permit_join` byłby niespodziewanie aktywny, test kończy się błędem bezpieczeństwa.

## Warunek PASS

Stage 3 uznajemy za zaliczony tylko wtedy, gdy:

1. `zigbee2mqtt/bridge/state` osiągnie `online`,
2. `bridge/info` jest poprawnym JSON-em,
3. koordynator zostanie rozpoznany,
4. `permit_join` nie jest aktywne,
5. `ventilation-core`, `wvc-web-ui`, Mosquitto i Zigbee2MQTT pozostają aktywne.

Po PASS nadal **nie parujemy urządzeń**. Następny etap ustali finalny jawny typ adaptera, kanał/politykę sieci oraz dopiero potem wykona kontrolowane parowanie pierwszego czujnika.
