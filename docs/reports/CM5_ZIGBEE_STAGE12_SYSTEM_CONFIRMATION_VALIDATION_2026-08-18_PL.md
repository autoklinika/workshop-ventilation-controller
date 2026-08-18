# CM5 Zigbee Stage 12 — walidacja potwierdzeń systemowych usuwania urządzeń

Data: 2026-08-18

Gałąź: `agent/zigbee-management-alerts-stage1`

## Wynik

Stage 12: **PASS**

## Potwierdzone elementy

- pełny zestaw testów: `Ran 268 tests ... OK`,
- `ventilation-core` po restarcie odzyskał gotowy stan Zigbee,
- Web V2 wystartował poprawnie na `http://127.0.0.1:18091`,
- oba realne czujniki były obecne w inwentarzu przed testem,
- kliknięcie ścieżki `USUŃ` tworzyło po stronie `ventilation-core` na CM5 oczekujące potwierdzenie zamiast natychmiastowego `device/remove`,
- utworzone potwierdzenie miało identyfikator `554e910167304d59ab4a65db54faf203`,
- to samo potwierdzenie było możliwe do ponownego odczytu z `ventilation-core`,
- samo utworzenie potwierdzenia nie usunęło `temp_nawiew`,
- rola `NAWIEW` pozostała bez zmian przed decyzją operatora,
- anulowanie przez core zadziałało poprawnie,
- po anulowaniu oczekujące potwierdzenie zostało usunięte,
- oba czujniki pozostały sparowane po teście,
- przeglądarkowy `window.confirm()` został usunięty,
- GUI korzysta z kontraktu systemowego potwierdzenia CM5,
- wszystkie usługi końcowo pozostały aktywne:
  - `ventilation-core.service`,
  - `wvc-web-ui.service`,
  - `mosquitto.service`,
  - `zigbee2mqtt.service`.

## Wniosek

Operacja destrukcyjnego usunięcia urządzenia Zigbee jest teraz potwierdzana przez mechanizm zarządzany przez `ventilation-core` na CM5. Przeglądarka jedynie wyświetla stan potwierdzenia i przesyła decyzję operatora. Test walidacyjny wykonał wyłącznie utworzenie oraz anulowanie potwierdzenia; nie otwierał parowania i nie usuwał żadnego urządzenia.
