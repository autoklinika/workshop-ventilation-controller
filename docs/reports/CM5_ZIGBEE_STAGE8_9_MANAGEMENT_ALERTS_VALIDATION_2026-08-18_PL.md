# CM5 Zigbee Stage 8/9 — walidacja zarządzania urządzeniami i alertów

Data walidacji: 2026-08-18
Gałąź: `agent/zigbee-management-alerts-stage1`
Tryb stanowiska: sam CM5 + infrastruktura Zigbee; część wykonawcza celowo offline

## Wynik

Stage 8/9 zakończony wynikiem PASS dla:

- integracji zarządzania Zigbee przez `ventilation-core`,
- Web API,
- GUI `Ustawienia -> Zigbee`,
- inwentarza urządzeń,
- bezpiecznej ścieżki `permit_join=0`,
- bazowego systemu alertów Zigbee.

## Testy repozytorium

Pełny zestaw testów zakończył się poprawnie:

```text
Ran 252 tests in 0.146s
OK
full unittest suite: PASS
```

## Stan usług

Po wdrożeniu i walidacji aktywne były:

- `ventilation-core.service`,
- `wvc-web-ui.service`,
- `mosquitto.service`,
- `zigbee2mqtt.service`.

## Stan bezpieczny stanowiska

Część wykonawcza była celowo offline. Potwierdzono:

- tryb standalone CM5,
- programowe setpointy `0 V / 0 V`,
- brak wpływu Zigbee na sterowanie wentylacją.

## Live inventory

Potwierdzono:

```text
mqtt connected: True
bridge online: True
permit_join: false
inventory mapping: PASS
```

Urządzenia:

```text
Coordinator: 0x00124b0038aaf159 type=Coordinator model=None
temp_nawiew: 0xa4c13810e66fffff type=EndDevice model=SNZB-02LD
temp_wywiew: 0xa4c13810bdedffff type=EndDevice model=SNZB-02LD
```

## Bezpieczna ścieżka zarządzania

Przez pełny tor:

```text
GUI/Web API -> ventilation-core -> MQTT -> Zigbee2MQTT
```

potwierdzono bezpieczną operację:

```text
POST /api/v1/zigbee/permit-join seconds=0: PASS
permit_join remains false: PASS
```

Walidator nie otwierał sieci i nie usuwał żadnego urządzenia.

## GUI

Potwierdzono:

```text
settings management controls: PASS
GUI -> Web API -> core boundary: PASS
```

Widok zawiera funkcje dodawania/parowania i usuwania urządzeń przez jawne endpointy Web API, bez bezpośredniego dostępu GUI do MQTT.

## Alerty Zigbee

Zdrowy baseline nie wygenerował fałszywych alertów:

```text
healthy Zigbee baseline has no active Zigbee alerts: PASS
```

W testach jednostkowych pokryto kody:

- `ZIGBEE_MQTT_DISCONNECTED`,
- `ZIGBEE_BRIDGE_OFFLINE`,
- `ZIGBEE_DEVICE_OFFLINE`,
- `ZIGBEE_DEVICE_DATA_STALE`,
- `ZIGBEE_LOW_BATTERY`.

Alerty korzystają z istniejącego `AlertRegistry`, SQLite, ACK i historii.

## Uwaga o pierwszym przebiegu

Pierwszy przebieg walidatora zatrzymał się po restarcie Web UI z `ConnectionRefusedError`, ponieważ `systemd` raportował usługę jako `active` zanim Python zdążył zbindować port HTTP. Nie był to błąd Zigbee ani Web API. Kontynuacyjny walidator poczekał na rzeczywisty listener HTTP i zakończył wszystkie pozostałe testy wynikiem PASS bez restartowania usług.

## Zakres, którego jeszcze nie wykonano fizycznie

Nie wykonano jeszcze praktycznego testu:

1. otwarcia `permit_join` na dodatni czas,
2. dołączenia nowego urządzenia,
3. usunięcia realnego urządzenia z sieci.

Te operacje są zaimplementowane i pokryte testami kontraktu, ale powinny zostać jeszcze sprawdzone na rzeczywistym urządzeniu przed funkcjonalnym zamknięciem Stage 8.

## Decyzja

Warstwa zarządzania oraz alerty Zigbee są poprawnie wdrożone i zwalidowane w bezpiecznym baseline. Następny krok: kontrolowany praktyczny test dodania i usunięcia jednego urządzenia Zigbee. `main` pozostaje nietknięty.
